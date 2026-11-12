"""Tests for external coding agent invocation and quota failover."""

import json
import subprocess
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
    invoke,
    invoke_with_failover,
    parse_reset,
)
from healthvideo.company import ModelSlot

NOW = datetime(2026, 11, 8, 18, 0, tzinfo=timezone(timedelta(hours=7)))
CODEX_SLOT = ModelSlot(cli="codex", model="gpt-6-astra")
AGY_SLOT = ModelSlot(cli="agy", model="claude-opus-5-5-high")


@pytest.fixture(autouse=True)
def isolated_executables(monkeypatch):
    monkeypatch.setattr('healthvideo.process.shutil.which', lambda command: None)


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
    assert captured["kwargs"]["input"] == prompt
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
    assert prompt in captured["argv"]
    assert captured["argv"][captured["argv"].index("-p") + 1] == prompt
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


def test_factory_keeps_scarce_opus_last_and_critics_away_from_the_author():
    from healthvideo.workflows.factory_deps import default_run_deps
    company = default_run_deps(Path('.')).company
    for step in ('research', 'draft', 'revise_medical', 'product_review'):
        # agy has too little Opus quota for half a video (2026-11-12): reserve only.
        chain = company.chain(company.role_for_step(step).id)
        assert chain[0].model == 'gemini-4-carbon-high'
        assert chain[-1].model == 'claude-opus-5-5-high'
    assert company.chain('script_critic')[0].cli != company.chain('writer')[0].cli


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
    assert parse_reset('resets in 2 hours', NOW) == NOW + timedelta(hours=2)
    assert parse_reset('resets in 15 minutes', NOW) == NOW + timedelta(minutes=15)
    assert parse_reset('usage limit', NOW) is None


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
    assert prompt_file.read_text(encoding='utf-8') == long_prompt
    assert calls[1][calls[1].index('-p') + 1] == 'ngắn'
