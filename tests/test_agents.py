"""Tests for external coding agent invocation and quota failover."""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from healthvideo.agents import (
    AGY,
    CODEX,
    AgentCli,
    AllAgentsExhausted,
    QuotaBook,
    argv_for,
    cancel_running_job,
    invoke,
    invoke_with_failover,
    parse_reset,
)
from healthvideo.company import CRITIC_OF, ModelSlot
from healthvideo.process import process_token

NOW = datetime(2026, 11, 8, 18, 0, tzinfo=timezone(timedelta(hours=7)))
CODEX_SLOT = ModelSlot(cli="codex", model="gpt-6-astra")
AGY_SLOT = ModelSlot(cli="agy", model="claude-opus-5-5-high")


@pytest.fixture(autouse=True)
def isolated_executables(monkeypatch):
    monkeypatch.setattr('healthvideo.process.shutil.which', lambda command: None)


def test_quota_reason_uses_latest_diagnostic_after_echoed_instructions():
    from healthvideo.agents import _quota_reason

    diagnostic = "You've hit your weekly limit · resets 5pm (Asia/Ho_Chi_Minh)"
    assert _quota_reason('Giữ fallback khi hết quota.\n' + diagnostic) == diagnostic


@pytest.mark.parametrize(('step', 'seconds'), [('coordinator', 120), ('coordinator_senior', 300)])
def test_coordinator_invocations_use_their_role_deadline(tmp_path, step, seconds):
    observed = []

    def runner(argv, **kwargs):
        observed.append(kwargs['timeout'])
        return _completed()

    invoke_with_failover([CODEX_SLOT], 'fixture', cwd=tmp_path, log_dir=tmp_path / 'logs',
                         role=step, slug='chung', step=step, runner=runner, now=lambda: NOW)
    assert observed == [seconds]


def _failover(tmp_path: Path, slots: Any, runner: Any, **kwargs: Any):
    return invoke_with_failover(
        slots,
        "prompt",
        cwd=tmp_path,
        log_dir=tmp_path / "logs",
        role="writer",
        slug="gout",
        step="draft",
        runner=runner,
        now=lambda: NOW,
        **kwargs,
    )


def _completed(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


@pytest.mark.parametrize('error,kind', [
    (subprocess.TimeoutExpired('codex', 2, output=b'partial output'), 'transient'),
    (PermissionError('permission denied'), 'configuration'),
    (FileNotFoundError('missing'), 'configuration'),
    (RuntimeError('unexpected runner failure'), 'agent_error'),
])
def test_failure_is_logged_classified_and_activity_terminated(tmp_path, error, kind):
    def runner(*args, **kwargs):
        raise error

    result = _failover(tmp_path, [CODEX_SLOT], runner)
    assert not result.ok and result.failure_kind == kind
    assert type(error).__name__ in result.log_path.read_text(encoding='utf-8')
    if isinstance(error, subprocess.TimeoutExpired):
        assert 'partial output' in result.log_path.read_text(encoding='utf-8')
    assert not (tmp_path / 'logs/.agent-running').exists()
    rows = [json.loads(line) for line in
            (tmp_path / 'topics/logs/activity.jsonl').read_text().splitlines()]
    assert [row['event'] for row in rows] == ['start', 'end']
    assert rows[1]['ok'] is False
    assert rows[0]['job_id'] == rows[1]['job_id']
    assert rows[0]['process_token'] == rows[1]['process_token']
    assert rows[0]['process_token']


def test_running_marker_keeps_legacy_lines_and_adds_identity(tmp_path):
    def runner(*args, **kwargs):
        lines = (tmp_path / 'logs/.agent-running').read_text().splitlines()
        assert lines[0] == 'codex'
        datetime.fromisoformat(lines[1])
        identity = json.loads(lines[2])
        assert identity['pid'] > 0 and identity['process_token'] and identity['job_id']
        assert kwargs['timeout'] > 0
        return _completed()

    assert _failover(tmp_path, [CODEX_SLOT], runner).ok


@pytest.mark.parametrize('locked_attempts', [2, 5])
def test_windows_marker_lock_does_not_discard_agent_output(tmp_path, monkeypatch, locked_attempts):
    original_unlink = Path.unlink
    attempts = 0

    def unlink(path, *args, **kwargs):
        nonlocal attempts
        if path.name == '.agent-running':
            attempts += 1
            if attempts <= locked_attempts:
                error = PermissionError('sharing violation')
                error.winerror = 32
                raise error
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'unlink', unlink)
    monkeypatch.setattr('healthvideo.agents.sleep', lambda _: None)
    result = _failover(tmp_path, [CODEX_SLOT], lambda *args, **kwargs: _completed(stdout='review saved'))
    assert result.ok
    assert result.log_path.read_text(encoding='utf-8') == 'review saved'
    assert attempts == min(locked_attempts + 1, 5)
    assert (tmp_path / 'logs/.agent-running').exists() == (locked_attempts == 5)


def test_interrupt_still_emits_terminal_activity_and_propagates(tmp_path):
    def runner(*args, **kwargs):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        _failover(tmp_path, [CODEX_SLOT], runner)
    rows = [json.loads(line) for line in
            (tmp_path / 'topics/logs/activity.jsonl').read_text().splitlines()]
    assert [row['event'] for row in rows] == ['start', 'end']
    assert rows[1]['ok'] is False
    assert not (tmp_path / 'logs/.agent-running').exists()


@pytest.mark.parametrize(
    'message,kind',
    [
        ('connection reset by peer', 'transient'),
        ('permission denied', 'configuration'),
        ('unexpected failure', 'agent_error'),
        ('', 'transient'),
        ('   \n', 'transient'),
    ],
)
def test_failed_agent_output_classification(tmp_path, message, kind):
    result = _failover(tmp_path, [CODEX_SLOT], lambda *a, **kw: _completed(1, stderr=message))
    assert result.failure_kind == kind


@pytest.mark.parametrize(('step', 'expected'), [('chat', 120), ('chat_deep', 300),
    ('posts', 600), ('feedback_inbox', 300), ('script_review', 900),
    ('research', 1800), ('draft', 1800), ('unknown', 900)])
def test_deadline_is_bounded_for_the_assigned_step(tmp_path, step, expected):
    def runner(*args, **kwargs):
        assert kwargs['timeout'] == expected
        return _completed()

    result = invoke_with_failover([CODEX_SLOT], 'prompt', cwd=tmp_path,
                                  log_dir=tmp_path / 'logs', role='writer', slug='gout',
                                  step=step, runner=runner)
    assert result.ok


def test_transient_failover_is_bounded_and_returns_last_failure(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv[0])
        raise subprocess.TimeoutExpired(argv, kwargs['timeout'], output='network timeout')

    result = _failover(tmp_path, [CODEX_SLOT, AGY_SLOT], runner, timeout=.01)
    assert result.failure_kind == 'transient'
    assert calls == ['codex', 'agy']
    assert not QuotaBook(tmp_path / 'cache/agent-quota.yaml').snapshot(NOW)


def test_quota_switches_to_next_agent(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        if argv[0] == "codex":
            return _completed(returncode=1, stderr="Error: Usage limit reached for today")
        return _completed(returncode=0, stdout="Done by agy")

    result = _failover(tmp_path, (CODEX_SLOT, AGY_SLOT), fake_runner)

    assert result.ok is True
    assert result.agent == "agy"
    assert result.model == "claude-opus-5-5-high"
    assert result.quota_exhausted is False
    assert [call[0] for call in calls] == ["codex", "agy"]


def test_non_quota_failure_does_not_switch(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        return _completed(returncode=1, stderr="SyntaxError: invalid input")

    result = _failover(tmp_path, (CODEX_SLOT, AGY_SLOT), fake_runner)

    assert result.ok is False
    assert result.agent == "codex"
    assert result.quota_exhausted is False
    assert len(calls) == 1


def test_all_exhausted_raises(tmp_path: Path) -> None:
    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if argv[0] == "codex":
            return _completed(returncode=1, stderr="HTTP 429 Too Many Requests")
        return _completed(returncode=1, stdout="RESOURCE_EXHAUSTED: quota exceeded")

    with pytest.raises(AllAgentsExhausted) as exc_info:
        _failover(tmp_path, (CODEX_SLOT, AGY_SLOT), fake_runner)

    assert exc_info.value.earliest_return == NOW + timedelta(hours=5)


def test_prompt_sent_via_stdin_for_codex(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return _completed(returncode=0, stdout="ok")

    codex = CODEX
    prompt = "Tóm tắt bằng chứng y khoa"
    invoke(codex, prompt, cwd=tmp_path, log_dir=tmp_path / "logs", runner=fake_runner)

    assert captured["argv"] == list(codex.argv)
    assert captured["kwargs"]["input"].startswith(prompt + '\n')
    assert captured["kwargs"]["encoding"] == "utf-8"
    assert captured["kwargs"]["text"] is True


def test_prompt_substituted_for_agy(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return _completed(returncode=0, stdout="ok")

    agy = AGY
    prompt = "Viết kịch bản giai đoạn 2"
    invoke(agy, prompt, cwd=tmp_path, log_dir=tmp_path / "logs", runner=fake_runner)

    assert "{prompt}" not in captured["argv"]
    assert captured["argv"][captured["argv"].index("-p") + 1].startswith(prompt + '\n')
    assert captured["kwargs"]["input"] is None


def test_agy_runs_headless_without_permission_prompts() -> None:
    assert "--dangerously-skip-permissions" in AGY.argv


def test_permission_auto_denied_is_failure_not_quota(tmp_path: Path) -> None:
    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _completed(
            returncode=0,
            stdout='jetski: no output produced - a tool required the "command" '
            "permission that headless mode cannot prompt for, so it was auto-denied.",
        )

    result = invoke(
        AGY,
        "prompt",
        cwd=tmp_path,
        log_dir=tmp_path / "logs",
        runner=fake_runner,
    )

    assert result.ok is False
    assert result.quota_exhausted is False


def test_env_has_no_pin_material(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEALTHVIDEO_APPROVER_PIN", "x")
    monkeypatch.setenv("lower_pin_var", "secret")
    captured_env: dict[str, str] = {}

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured_env.update(kwargs["env"])
        return _completed(returncode=0)

    invoke(
        CODEX,
        "prompt",
        cwd=tmp_path,
        log_dir=tmp_path / "logs",
        runner=fake_runner,
    )

    assert not any("pin" in key.lower() for key in captured_env)


def test_success_returns_first_agent_result(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv[0])
        return _completed(returncode=0, stdout="completed on first try")

    result = _failover(tmp_path, (CODEX_SLOT, AGY_SLOT), fake_runner)

    assert result.ok is True
    assert result.agent == "codex"
    assert result.quota_exhausted is False
    assert calls == ["codex"]


def test_missing_executable_is_not_quota(tmp_path: Path) -> None:
    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(2, "No such file or directory", argv[0])

    agent = AgentCli("missing-cli", ("missing-cli", "{prompt}"), False)
    result = invoke(
        agent,
        "prompt",
        cwd=tmp_path,
        log_dir=tmp_path / "logs",
        runner=fake_runner,
    )

    assert result.ok is False
    assert result.quota_exhausted is False
    assert result.log_path.is_file()
    assert "missing-cli" in result.log_path.read_text(encoding="utf-8")


def test_log_written_utf8(tmp_path: Path) -> None:
    vietnamese_stdout = "Đã kiểm tra huyết áp tâm thu và đường huyết lúc đói.\n"
    vietnamese_stderr = "Cảnh báo: cần đối chiếu thêm nguồn PubMed.\n"

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _completed(
            returncode=0,
            stdout=vietnamese_stdout,
            stderr=vietnamese_stderr,
        )

    result = invoke(
        CODEX,
        "prompt",
        cwd=tmp_path,
        log_dir=tmp_path / "logs",
        runner=fake_runner,
    )

    assert result.log_path.is_file()
    assert result.log_path.name.endswith("-codex.log")
    content = result.log_path.read_text(encoding="utf-8")
    assert content == vietnamese_stdout + vietnamese_stderr


def test_argv_for_each_cli_injects_model():
    for slot in (CODEX_SLOT, AGY_SLOT, ModelSlot(cli='claude', model='claude-opus-5-5')):
        cli, argv = argv_for(slot)
        assert cli.name == slot.cli
        flag = '-m' if slot.cli == 'codex' else '--model'
        assert argv[argv.index(flag) + 1] == slot.model
        if slot.cli == 'codex':
            assert argv.index('-m') < argv.index('-')


def test_claude_runs_with_a_tool_allowlist_not_a_permission_bypass():
    from healthvideo.agents import CLAUDE
    assert CLAUDE.prompt_via_stdin
    assert '--allowedTools' in CLAUDE.argv
    assert not any('dangerously' in token for token in CLAUDE.argv)


def test_factory_uses_moderate_models_and_critics_away_from_the_author():
    from healthvideo.workflows.factory_deps import default_run_deps
    company = default_run_deps(Path('.')).company
    for role in company.roles:
        assert company.chain(role)[0].cli in {'agy', 'codex', 'claude'}, role
    for step in ('research', 'draft', 'revise_medical', 'chat_deep'):
        assert company.chain(company.role_for_step(step).id)[0].model_identity == ('agy', 'claude-sonnet-5-5-medium'), step  # TEMP codex quota
    for step in ('storyboard_design', 'repair'):
        assert company.chain(company.role_for_step(step).id)[0].model_identity == ('agy', 'gemini-4-neon-medium'), step
    for step in ('visual_review', 'product_review'):
        assert company.chain(company.role_for_step(step).id)[0].model_identity == ('claude', 'claude-sonnet-5-5'), step
    for role in ('coordinator', 'scout', 'copywriter', 'feedback_analyst', 'researcher',
                 'editor', 'shorts_producer', 'voice_director'):
        assert company.chain(role)[0].model_identity == ('agy', 'gemini-4-neon-medium'), role
    assert company.chain('script_critic')[0].model_identity == ('agy', 'gemini-4-carbon-medium')
    for role in company.roles:
        for slot in company.chain(role):
            assert 'opus' not in slot.model and 'astra' not in slot.model and 'carbon-high' not in slot.model, (role, slot)
    for critic_id, makers in CRITIC_OF.items():
        for maker_id in makers:
            assert company.chain(critic_id)[0].model_identity != company.chain(maker_id)[0].model_identity, (critic_id, maker_id)


@pytest.mark.parametrize('message', [
    "ERROR: Model 'gemini-pro-orchestrator' is not available in the active live catalog",
    'Error: unknown model gemini-pro-orchestrator',
    '{"error":{"code":"model_not_found","message":"Missing model"}}',
    'Error: model gemini-pro-orchestrator is not supported',
])
def test_unavailable_model_falls_back_immediately_without_resting_account(tmp_path, message):
    carbon = ModelSlot(cli='agy', model='gemini-pro-orchestrator')
    argon = ModelSlot(cli='agy', model='gemini-pro-orchestrator-argon')
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return _completed(1, stderr=message) if len(calls) == 1 else _completed()

    result = _failover(tmp_path, [carbon, argon], run)
    assert result.ok and result.model == argon.model and len(calls) == 2
    book = QuotaBook(tmp_path / 'cache/agent-quota.yaml')
    assert book.resting(carbon, NOW)
    assert not book.resting(argon, NOW)


def test_resting_slot_is_skipped(tmp_path):
    book = QuotaBook(tmp_path / 'quota.yaml')
    book.rest(CODEX_SLOT, NOW + timedelta(hours=1), 'quota')
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return _completed()

    result = _failover(tmp_path, [CODEX_SLOT, AGY_SLOT], runner,
                       quota=QuotaBook(book.path))
    assert result.model == AGY_SLOT.model
    assert len(calls) == 1
    assert calls[0][0] == 'agy'


def test_quota_rests_slot_default_five_hours(tmp_path):
    with pytest.raises(AllAgentsExhausted) as error:
        _failover(tmp_path, [CODEX_SLOT], lambda *a, **kw: _completed(1, 'usage limit'))
    book = QuotaBook(tmp_path / 'cache/agent-quota.yaml')
    assert error.value.earliest_return == NOW + timedelta(hours=5)
    assert datetime.fromisoformat(book.snapshot(NOW)[0]['resting_until']) == NOW + timedelta(hours=5)
    assert book.resting(CODEX_SLOT, NOW)
    assert not book.resting(CODEX_SLOT, NOW + timedelta(hours=5))
    rows = [json.loads(line) for line in
            (tmp_path / 'topics/logs/activity.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [row['event'] for row in rows] == ['start', 'end', 'quota']


def test_parse_reset_reads_cli_hint():
    assert parse_reset('try again at 21:30', NOW) == NOW.replace(hour=21, minute=30)
    assert parse_reset('try again at 17:30', NOW) == NOW.replace(hour=17, minute=30) + timedelta(days=1)
    assert parse_reset("You've hit your weekly limit · resets 5pm (Asia/Ho_Chi_Minh)", NOW) == NOW.replace(hour=17, minute=0) + timedelta(days=1)
    assert parse_reset('resets at 5pm', NOW) == NOW.replace(hour=17, minute=0) + timedelta(days=1)
    assert parse_reset('resets 17:00', NOW) == NOW.replace(hour=17, minute=0) + timedelta(days=1)
    assert parse_reset('resets in 2 hours', NOW) == NOW + timedelta(hours=2)
    assert parse_reset('resets in 15 minutes', NOW) == NOW + timedelta(minutes=15)
    assert parse_reset('usage limit', NOW) is None
    assert parse_reset('resets 5', NOW) is None


def test_weekly_limit_fails_over_and_rests_all_slots_until_reset(tmp_path):
    other = ModelSlot(cli='codex', model='gpt-6.1-sol')
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv[0])
        if argv[0] == 'codex':
            return _completed(1, "You've hit your weekly limit · resets 5pm (Asia/Ho_Chi_Minh)")
        return _completed()

    result = _failover(tmp_path, [CODEX_SLOT, other, AGY_SLOT], runner)
    assert result.ok and result.agent == 'agy'
    assert calls == ['codex', 'agy']
    book = QuotaBook(tmp_path / 'cache/agent-quota.yaml')
    assert book.resting(CODEX_SLOT, NOW)
    assert book.resting(other, NOW)
    assert book.resting(ModelSlot(cli='codex', model='gpt-6-luna'), NOW)
    assert not book.resting(AGY_SLOT, NOW)
    expected_reset = NOW.replace(hour=17, minute=0) + timedelta(days=1)
    entries = {e['model']: e['resting_until'] for e in book.snapshot(NOW) if e['cli'] == 'codex'}
    assert entries.get('*') == expected_reset.isoformat()


def test_account_quota_rests_all_slots_of_cli(tmp_path):
    other = ModelSlot(cli='codex', model='gpt-6.1-sol')
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv[0])
        return _completed(1, 'account quota exceeded') if argv[0] == 'codex' else _completed()

    _failover(tmp_path, [CODEX_SLOT, other, AGY_SLOT], runner)
    book = QuotaBook(tmp_path / 'cache/agent-quota.yaml')
    assert calls == ['codex', 'agy']
    assert book.resting(other, NOW)
    assert book.resting(ModelSlot(cli='codex', model='gpt-6-luna'), NOW)
    assert not book.resting(AGY_SLOT, NOW)


def test_activity_lines_written(tmp_path):
    _failover(tmp_path, [CODEX_SLOT], lambda *a, **kw: _completed())
    rows = [json.loads(line) for line in
            (tmp_path / 'topics/logs/activity.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [row['event'] for row in rows] == ['start', 'end']
    for row in rows:
        assert row['role'] == 'writer'
        assert row['model'] == 'gpt-6-astra'
        assert row['slug'] == 'gout'
        assert row['step'] == 'draft'
    assert rows[-1]['ok'] is True


def test_quota_preserves_other_slots_with_injected_clock(tmp_path):
    past = NOW.replace(year=2020)
    book = QuotaBook(tmp_path / 'quota.yaml')
    book.rest(CODEX_SLOT, past + timedelta(hours=2), 'quota')
    book.rest(AGY_SLOT, past + timedelta(hours=3), 'quota')
    assert QuotaBook(book.path).resting(CODEX_SLOT, past)


def test_invoke_prepares_windows_launcher(tmp_path, monkeypatch):
    from healthvideo import process
    monkeypatch.setattr(process.shutil, 'which', lambda command: 'C:/tools/codex.exe')
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return _completed()

    _failover(tmp_path, [CODEX_SLOT], runner)
    assert calls[0][0] == 'C:/tools/codex.exe'


def test_server_overload_fails_over_and_rests_briefly(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        if len(calls) == 1:
            return _completed(1, stderr='UNAVAILABLE (code 503): No capacity available for model x')
        return _completed()

    book = QuotaBook(tmp_path / 'quota.yaml')
    result = _failover(tmp_path, [AGY_SLOT, CODEX_SLOT], runner, quota=book)
    assert result.ok and result.model == CODEX_SLOT.model
    assert book.resting(AGY_SLOT, NOW + timedelta(minutes=5))
    assert not book.resting(AGY_SLOT, NOW + timedelta(minutes=11))


def test_all_busy_slots_return_transient_failure_for_durable_retry_budget(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv[0])
        return _completed(1, stderr='UNAVAILABLE (code 503): overloaded')

    book = QuotaBook(tmp_path / 'quota.yaml')
    result = _failover(tmp_path, [AGY_SLOT, CODEX_SLOT], runner, quota=book)
    assert not result.ok and not result.quota_exhausted
    assert result.failure_kind == 'transient'
    assert result.agent == 'codex'
    assert calls == ['agy', 'codex']
    for slot in (AGY_SLOT, CODEX_SLOT):
        assert book.resting(slot, NOW + timedelta(minutes=5))
        assert not book.resting(slot, NOW + timedelta(minutes=11))


def test_plain_failure_does_not_fail_over(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return _completed(1, stderr='Traceback: boom')

    result = _failover(tmp_path, [AGY_SLOT, CODEX_SLOT], runner)
    assert not result.ok and len(calls) == 1


def test_long_argv_prompt_goes_through_file(tmp_path, monkeypatch):
    from healthvideo import agents, process
    monkeypatch.setattr(process.shutil, 'which', lambda command: 'C:/tools/agy.exe')
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return _completed()

    long_prompt = 'ghi chú bác sĩ ' * 3000
    agents.invoke(agents.AGY, long_prompt, cwd=tmp_path, log_dir=tmp_path / 'logs', runner=runner)
    agents.invoke(agents.AGY, 'ngắn', cwd=tmp_path, log_dir=tmp_path / 'logs', runner=runner)
    passed = calls[0][calls[0].index('-p') + 1]
    assert len(passed) < agents.MAX_ARGV_PROMPT
    (prompt_file,) = (tmp_path / 'logs').glob('*-agy-prompt.md')
    assert str(prompt_file) in passed
    assert prompt_file.read_text(encoding='utf-8').startswith(long_prompt + '\n')
    assert calls[1][calls[1].index('-p') + 1].startswith('ngắn\n')


def test_exclude_slots_avoids_excluded_slots(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return _completed()

    result = _failover(tmp_path, [CODEX_SLOT, AGY_SLOT], runner, exclude_slots=[CODEX_SLOT])
    assert result.ok and result.model == AGY_SLOT.model
    assert len(calls) == 1 and calls[0][0] == 'agy'


def test_exclude_slots_never_falls_back_to_maker_slot_when_all_excluded(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return _completed()

    with pytest.raises(ValueError, match='model độc lập'):
        _failover(tmp_path, [CODEX_SLOT], runner, exclude_slots=[CODEX_SLOT])
    assert calls == []


def test_exclude_slots_exhausts_without_touching_maker_slot(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv[0])
        return _completed(1, stderr='429 rate limit exceeded')

    with pytest.raises(AllAgentsExhausted):
        _failover(tmp_path, [CODEX_SLOT, AGY_SLOT], runner, exclude_slots=[CODEX_SLOT])
    assert calls == ['agy']


def test_cancel_running_job_terminates_child_and_removes_job_file(tmp_path):
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        job_dir = tmp_path / 'topics/logs/gout-test'
        job_dir.mkdir(parents=True, exist_ok=True)
        job_file = job_dir / '.job-test-cancel-1.json'
        job_file.write_text(
            json.dumps({
                'job_id': 'test-cancel-1',
                'role': 'writer',
                'slug': 'gout-test',
                'step': 'draft',
                'cli': 'codex',
                'model': 'gpt-6.1-sol',
                'child_pid': proc.pid,
                'child_process_token': process_token(proc.pid),
                'started_at': NOW.isoformat(),
            }),
            encoding='utf-8',
        )
        cancelled = cancel_running_job(tmp_path, job_id='test-cancel-1')
        assert len(cancelled) == 1
        assert cancelled[0]['job_id'] == 'test-cancel-1'
        assert proc.wait(timeout=5) is not None
        assert not job_file.exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_empty_nonzero_cli_exit_fails_over_as_transient(tmp_path: Path) -> None:
    calls: list[str] = []

    def failover_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv[0])
        if len(calls) == 1:
            return _completed(returncode=1, stdout="", stderr="")
        return _completed(returncode=0, stdout="ok")

    result = _failover(tmp_path, [AGY_SLOT, CODEX_SLOT], failover_runner)
    assert result.ok is True
    assert result.agent == "codex"
    assert calls == ["agy", "codex"]

    all_empty = _failover(
        tmp_path,
        [AGY_SLOT, CODEX_SLOT],
        lambda *a, **kw: _completed(returncode=1, stdout="", stderr=""),
    )
    assert all_empty.ok is False
    assert all_empty.failure_kind == "transient"


def test_activity_end_event_records_monotonic_duration_usage_and_failure_kind(tmp_path: Path) -> None:
    _failover(
        tmp_path,
        [CODEX_SLOT],
        lambda *a, **kw: _completed(returncode=0, stdout="Done\ntokens used\n12,345\n"),
    )
    _failover(
        tmp_path,
        [CODEX_SLOT],
        lambda *a, **kw: _completed(
            returncode=0,
            stdout=json.dumps({"usage": {"input_tokens": 100, "output_tokens": 50, "cached_tokens": 40, "reasoning_tokens": 10}}),
        ),
    )
    _failover(
        tmp_path,
        [CODEX_SLOT],
        lambda *a, **kw: _completed(returncode=1, stderr="permission denied"),
    )

    ends = [
        json.loads(line)
        for line in (tmp_path / "topics/logs/activity.jsonl").read_text(encoding="utf-8").splitlines()
        if json.loads(line)["event"] == "end"
    ]
    assert len(ends) == 3

    assert ends[0]["usage_available"] is True
    assert ends[0]["cli_total_tokens"] == 12345
    assert ends[0]["failure_kind"] is None
    assert isinstance(ends[0]["duration_s"], (int, float)) and ends[0]["duration_s"] >= 0

    assert ends[1]["usage_available"] is True
    assert ends[1]["cli_total_tokens"] == 150
    assert ends[1]["input_tokens"] == 100
    assert ends[1]["output_tokens"] == 50
    assert ends[1]["cached_tokens"] == 40
    assert ends[1]["reasoning_tokens"] == 10

    assert ends[2]["ok"] is False
    assert ends[2]["usage_available"] is False
    assert ends[2]["cli_total_tokens"] is None
    assert ends[2]["failure_kind"] == "configuration"


def test_invoke_with_failover_optional_local_llm_hook_and_single_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from healthvideo import local_llm

    with pytest.raises(ValueError, match="cấm"):
        invoke_with_failover(
            [CODEX_SLOT],
            "prompt",
            cwd=tmp_path,
            log_dir=tmp_path / "logs",
            role="writer",
            slug="gout",
            step="draft",
            runner=lambda *a, **kw: pytest.fail("CLI must not run for forbidden local role"),
            local_task="feedback_inbox",
        )

    # Local succeeds -> bypasses CLI runner and logs ollama activity.
    sample_data = local_llm.ChatStatusSummary(reply="Đang chờ bác sĩ duyệt.", action="status")
    monkeypatch.setattr(
        local_llm,
        "try_local_task",
        lambda **kwargs: local_llm.LocalAttempt(
            ok=True,
            used_local=True,
            model="qwen3:4b",
            data=sample_data,
            prompt_eval_count=80,
            eval_count=20,
            total_duration_s=0.45,
            eval_tok_per_s=44.4,
        ),
    )
    local_res = invoke_with_failover(
        [CODEX_SLOT],
        "status?",
        cwd=tmp_path,
        log_dir=tmp_path / "logs",
        role="coordinator",
        slug="chung",
        step="chat",
        runner=lambda *a, **kw: pytest.fail("CLI runner must not run when local succeeds"),
        local_task="chat_status_summary",
    )
    assert local_res.ok is True
    assert local_res.agent == "ollama"
    assert local_res.used_local is True
    assert local_res.local_data == sample_data

    # Local disabled/fails -> falls back once to CLI slot.
    monkeypatch.setattr(
        local_llm,
        "try_local_task",
        lambda **kwargs: local_llm.LocalAttempt(ok=False, used_local=False, reason="local_llm_disabled"),
    )
    cli_calls: list[str] = []

    def fallback_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cli_calls.append(argv[0])
        return _completed(returncode=0, stdout="fallback ok")

    fb_res = invoke_with_failover(
        [CODEX_SLOT],
        "status?",
        cwd=tmp_path,
        log_dir=tmp_path / "logs",
        role="coordinator",
        slug="chung",
        step="chat",
        runner=fallback_runner,
        local_task="chat_status_summary",
    )
    assert fb_res.ok is True
    assert fb_res.agent == "codex"
    assert fb_res.used_local is False
    assert cli_calls == ["codex"]


@pytest.mark.parametrize("winerror", [5, 32])
def test_cancel_and_marker_cleanup_retry_windows_access_and_sharing_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, winerror: int
) -> None:
    from healthvideo.agents import _remove_job_marker

    original_unlink = Path.unlink
    attempts: dict[str, int] = {}

    def flaky_unlink(path: Path, *args: Any, **kwargs: Any) -> None:
        if path.name.startswith((".agent-running", ".cancelled-", ".job-")):
            attempts[path.name] = attempts.get(path.name, 0) + 1
            if attempts[path.name] <= 2:
                error = PermissionError("locked")
                error.winerror = winerror
                raise error
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)
    monkeypatch.setattr("healthvideo.agents.sleep", lambda _: None)

    cancel_file = tmp_path / "logs/.cancelled-job1"
    cancel_file.parent.mkdir(parents=True, exist_ok=True)
    cancel_file.write_text("cancelled\n", encoding="utf-8")
    assert _remove_job_marker(cancel_file) is True
    assert not cancel_file.exists()
    assert attempts[cancel_file.name] == 3

    # invoke() also uses _remove_job_marker on .cancelled-<job_id>
    attempts.clear()
    res = invoke(
        CODEX,
        "prompt",
        cwd=tmp_path,
        log_dir=tmp_path / "logs",
        job_id="job2",
        runner=lambda *a, **kw: (
            (tmp_path / "logs/.cancelled-job2").write_text("cancelled\n", encoding="utf-8"),
            _completed(0, "partial"),
        )[1],
    )
    assert res.failure_kind == "cancelled"
    assert not (tmp_path / "logs/.cancelled-job2").exists()
    assert attempts[".cancelled-job2"] == 3


def test_cancel_running_job_retries_windows_sharing_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        job_dir = tmp_path / "topics/logs/gout-cancel"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / ".agent-running").write_text("codex\n", encoding="utf-8")
        job_file = job_dir / ".job-test-cancel-win32.json"
        job_file.write_text(
            json.dumps({
                "job_id": "test-cancel-win32",
                "role": "writer",
                "slug": "gout-cancel",
                "step": "draft",
                "child_pid": proc.pid,
                "child_process_token": process_token(proc.pid),
            }),
            encoding="utf-8",
        )
        original_unlink = Path.unlink
        seen: dict[str, int] = {}

        def flaky_unlink(path: Path, *args: Any, **kwargs: Any) -> None:
            if path.name in {job_file.name, ".agent-running"}:
                seen[path.name] = seen.get(path.name, 0) + 1
                if seen[path.name] <= 2:
                    error = PermissionError("sharing violation")
                    error.winerror = 32
                    raise error
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", flaky_unlink)
        monkeypatch.setattr("healthvideo.agents.sleep", lambda _: None)

        cancelled = cancel_running_job(tmp_path, job_id="test-cancel-win32")
        assert len(cancelled) == 1
        assert not job_file.exists()
        assert not (job_dir / ".agent-running").exists()
        assert seen == {job_file.name: 3, ".agent-running": 3}
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_child_env_sets_utf8_defaults_and_preserves_vietnamese_over_windows_pipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from healthvideo.env import child_env

    monkeypatch.delenv("PYTHONUTF8", raising=False)
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    env = child_env()
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"

    # Preserve existing non-empty settings.
    monkeypatch.setenv("PYTHONUTF8", "0")
    monkeypatch.setenv("PYTHONIOENCODING", "utf-16")
    preserved = child_env()
    assert preserved["PYTHONUTF8"] == "0"
    assert preserved["PYTHONIOENCODING"] == "utf-16"

    # Real subprocess over a pipe must emit Vietnamese diacritics cleanly (no '?' or cp1252 error).
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    sample = "Đã kiểm tra: bác sĩ uống thuốc bổ gan chuyển hóa đúng?"
    proc = subprocess.run(
        [sys.executable, "-c", f"print({sample!r})"],
        env=child_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=True,
    )
    assert proc.stdout.strip() == sample


@pytest.mark.parametrize('message', ['HTTP 429', 'HTTP 503', 'sharing violation',
                                    'Access is denied while renaming temporary file'])
def test_cli_transient_error_precedes_configuration_wording(tmp_path, message):
    from healthvideo.agents import AgentCli, invoke

    result = invoke(AgentCli('codex', ('codex',), 'arg'), 'prompt', cwd=tmp_path,
                    log_dir=tmp_path / 'logs',
                    runner=lambda *args, **kwargs: _completed(1, stderr=message))
    assert result.failure_kind == 'transient'


@pytest.mark.parametrize('code', [5, 32, 33])
def test_cli_exception_windows_file_lock_is_transient(tmp_path, code):
    def locked(*args, **kwargs):
        error = PermissionError('locked')
        error.winerror = code
        raise error
    assert _failover(tmp_path, [CODEX_SLOT], locked).failure_kind == 'transient'
