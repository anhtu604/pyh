"""Tests for the run_queue factory loop with injected dependencies."""

import json
import subprocess
from dataclasses import fields
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from healthvideo.agents import (
    AgentResult,
    AllAgentsExhausted,
    invoke_with_failover,
)
from healthvideo.company import ModelSlot, load_company
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import read_yaml
from healthvideo.storage.queue import add_to_queue
from healthvideo.workflows.runner import (
    HARD_RULES,
    RunDeps,
    render_prompt,
    run_queue,
)


def _reliability_deps(tmp_path, *, invoke=None, read_state=None, python_steps=None):
    for slug in ('broken', 'healthy'):
        add_to_queue(tmp_path, _entry(slug))
        project = tmp_path / 'projects' / slug
        project.mkdir(parents=True)
    states = {'broken': WorkflowState.TOPIC_SELECTED,
              'healthy': WorkflowState.TOPIC_SELECTED}
    calls = []

    def default_invoke(*args, log_dir, **kwargs):
        calls.append(log_dir.name)
        if log_dir.name == 'healthy':
            states['healthy'] = WorkflowState.AWAITING_MEDICAL_REVIEW
            return AgentResult('fake', True, False, _log_file(log_dir))
        return SimpleNamespace(agent='fake', ok=False, failure_kind='transient',
                               log_path=_log_file(log_dir))

    return RunDeps(
        create_project=lambda root, entry: root / 'projects' / entry.slug,
        read_state=read_state or (lambda project: states[project.name]),
        reject_note=lambda _: None, python_steps=python_steps or {},
        changed_code_paths=lambda _: [], invoke=invoke or default_invoke,
    ), calls


def test_agent_transient_retry_persists_backoff_and_cap_without_output_reset(tmp_path, monkeypatch):
    from healthvideo.workflows import production_retry

    now = datetime(2026, 11, 14, tzinfo=UTC)
    clock = {'now': now}
    monkeypatch.setattr(production_retry, '_now', lambda: clock['now'])
    deps, calls = _reliability_deps(tmp_path)
    assert run_queue(tmp_path, deps).at_gate == ['healthy']
    run_queue(tmp_path, deps)
    assert calls.count('broken') == 1
    # A failed research agent's own evidence/project output is not fresh input.
    project = tmp_path / 'projects/broken'
    (project / 'project.yaml').write_text('active_revision: "001"\nstate: research_in_progress\n')
    evidence = project / 'revisions/001/evidence'
    evidence.mkdir(parents=True)
    (evidence / 'ledger.yaml').write_text('attempt_output: changed\n')
    clock['now'] += timedelta(seconds=120)
    run_queue(tmp_path, deps)
    run_queue(tmp_path, deps)
    assert calls.count('broken') == 2
    clock['now'] += timedelta(seconds=600)
    run_queue(tmp_path, deps)
    clock['now'] += timedelta(days=1)
    run_queue(tmp_path, deps)
    assert calls.count('broken') == 3
    stored = read_yaml(tmp_path / 'topics/logs/broken/agent-retry.yaml')
    assert stored['steps']['research']['attempts'] == 3


def test_agent_unknown_failure_and_invalid_success_are_held(tmp_path):
    calls = []

    def invoke(*args, log_dir, **kwargs):
        calls.append(log_dir.name)
        return AgentResult('fake', log_dir.name == 'healthy', False, _log_file(log_dir))

    deps, _ = _reliability_deps(tmp_path, invoke=invoke)
    for _ in range(2):
        assert set(run_queue(tmp_path, deps).blocked) == {'broken', 'healthy'}
    assert calls == ['broken', 'healthy']


def test_bad_state_and_tool_exception_do_not_crash_other_topics(tmp_path):
    def state(project):
        if project.name == 'broken':
            raise ValueError('corrupt project state')
        return WorkflowState.AWAITING_MEDICAL_REVIEW

    deps, _ = _reliability_deps(tmp_path, read_state=state)
    report = run_queue(tmp_path, deps)
    assert report.blocked == ['broken']
    assert report.at_gate == ['healthy']


def test_produce_has_live_identity_marker_and_cleans_it_on_exception(tmp_path):
    markers = []

    def produce(project):
        marker = tmp_path / 'topics/logs' / project.name / '.production-running'
        markers.append(json.loads(marker.read_text()))
        raise RuntimeError('render failed')

    deps, _ = _reliability_deps(
        tmp_path, read_state=lambda _: WorkflowState.MEDICALLY_APPROVED,
        python_steps={'produce': produce},
    )
    report = run_queue(tmp_path, deps)
    assert len(markers) == 2
    assert all(item['pid'] > 0 and item['process_token'] and item['started_at'] for item in markers)
    assert not list((tmp_path / 'topics/logs').glob('*/.production-running'))
    assert report.blocked == ['broken', 'healthy']


@pytest.mark.parametrize('quota_first', [False, True])
def test_retry_nested_production_resumes_renderer_before_review_or_gate(tmp_path, monkeypatch, quota_first):
    from healthvideo.workflows import product_review, production_retry

    entry = _entry('retry-render')
    add_to_queue(tmp_path, entry)
    project = tmp_path / 'projects' / entry.slug
    project.mkdir(parents=True)
    state = {'value': WorkflowState.PRODUCTION_IN_PROGRESS, 'fixed': False}
    calls = []
    clock = {'now': datetime(2026, 11, 14, tzinfo=UTC)}
    monkeypatch.setattr(production_retry, '_now', lambda: clock['now'])
    monkeypatch.setattr(product_review, 'revision_notes', lambda _: 'fix layout')
    monkeypatch.setattr(product_review, 'mark_fix_attempted', lambda _: state.update(fixed=True))
    monkeypatch.setattr(product_review, 'next_product_action',
                        lambda _: 'submit_video' if state['fixed'] else 'revise_product')

    def invoke(*args, log_dir, **kwargs):
        calls.append('agent')
        if quota_first and len(calls) == 1:
            raise AllAgentsExhausted(datetime.now(UTC) - timedelta(seconds=1))
        return AgentResult('fake', True, False, _log_file(log_dir))

    def produce(_):
        calls.append('produce')
        marker = tmp_path / 'topics/logs' / entry.slug / '.production-running'
        assert marker.exists()
        if calls.count('produce') == 1:
            raise RuntimeError('render timeout')
        state['value'] = WorkflowState.AWAITING_VIDEO_REVIEW

    deps = RunDeps(create_project=lambda *_: project, read_state=lambda _: state['value'],
                   reject_note=lambda _: None, changed_code_paths=lambda _: [], invoke=invoke,
                   product_review_pending=lambda _: True,
                   python_steps={'produce': produce, 'submit_video': lambda _: calls.append('gate')})
    if quota_first:
        assert run_queue(tmp_path, deps).waiting_model == [entry.slug]
    agents = ['agent'] * (2 if quota_first else 1)
    assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert calls == [*agents, 'produce']
    clock['now'] += timedelta(seconds=120)
    assert run_queue(tmp_path, deps).at_gate == [entry.slug]
    assert calls == [*agents, 'produce', 'produce']
    assert not (tmp_path / 'topics/logs' / entry.slug / 'production-retry.yaml').exists()


def test_tool_failure_holds_and_keyboard_interrupt_propagates(tmp_path):
    def invoke(*args, **kwargs):
        raise FileNotFoundError('missing executable')

    deps, _ = _reliability_deps(tmp_path, invoke=invoke)
    assert run_queue(tmp_path, deps).blocked == ['broken', 'healthy']
    for slug in ['broken', 'healthy']:
        stored = read_yaml(tmp_path / 'topics/logs' / slug / 'agent-retry.yaml')
        assert stored['steps']['research']['kind'] == 'configuration'
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt
    # A real changed brief releases the hold; KeyboardInterrupt must remain visible.
    from dataclasses import replace
    changed = replace(deps, invoke=interrupt)
    (tmp_path / 'profiles').mkdir()
    (tmp_path / 'profiles/company.yaml').write_text('changed: true')
    import pytest
    with pytest.raises(KeyboardInterrupt):
        run_queue(tmp_path, changed)


def test_post_agent_bookkeeping_failure_cannot_repeat_paid_call(tmp_path):
    from dataclasses import replace

    deps, calls = _reliability_deps(tmp_path)
    def fail(_):
        raise RuntimeError('git snapshot unavailable')
    deps = replace(deps, changed_code_paths=fail)
    run_queue(tmp_path, deps)
    run_queue(tmp_path, deps)
    assert calls.count('broken') == 1


def test_configuration_hold_releases_on_real_input_change_and_success_clears(tmp_path):
    calls, states = [], {'broken': WorkflowState.TOPIC_SELECTED, 'healthy': WorkflowState.TOPIC_SELECTED}
    fixed = {'value': False}
    def invoke(*args, log_dir, **kwargs):
        calls.append(log_dir.name)
        ok = fixed['value'] or log_dir.name == 'healthy'
        if ok:
            states[log_dir.name] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return AgentResult('fake', ok, False, _log_file(log_dir),
                           failure_kind=None if ok else 'configuration')
    deps, _ = _reliability_deps(tmp_path, invoke=invoke, read_state=lambda p: states[p.name])
    run_queue(tmp_path, deps)
    run_queue(tmp_path, deps)
    assert calls.count('broken') == 1
    fixed['value'] = True
    source = tmp_path / 'projects/broken/revisions/001/script/questions.yaml'
    source.parent.mkdir(parents=True)
    source.write_text('questions: [{id: Q1, ask: Updated brief}]\n', encoding='utf-8')
    assert run_queue(tmp_path, deps).at_gate == ['broken', 'healthy']
    assert calls.count('broken') == 2
    assert not (tmp_path / 'topics/logs/broken/agent-retry.yaml').exists()


def test_once_stops_after_one_completed_step_even_if_producer_state_is_unchanged(tmp_path):
    calls = []
    deps, _ = _reliability_deps(
        tmp_path, read_state=lambda _: WorkflowState.PRODUCTION_IN_PROGRESS,
        python_steps={'produce': lambda project: calls.append(project.name)},
    )
    run_queue(tmp_path, deps, once=True)
    assert calls == ['broken']


@pytest.mark.parametrize('kind', ['script', 'product'])
def test_failed_critic_report_cannot_be_rebound_to_changed_input(tmp_path, kind):
    """A CLI success without fresh output cannot adopt a prior failed attempt's score."""
    from healthvideo.workflows import product_review, script_review
    from tests.workflows import test_product_review as product_helpers
    from tests.workflows import test_script_review as script_helpers

    helpers = script_helpers if kind == 'script' else product_helpers
    reviewer = script_review if kind == 'script' else product_review
    project = helpers._queue(tmp_path)
    revision = project / 'revisions/001'
    state = {'value': WorkflowState.DRAFT_READY if kind == 'script'
             else WorkflowState.PRODUCTION_IN_PROGRESS, 'renders': 1}
    attempts = []

    def invoke(*args, log_dir, **kwargs):
        attempts.append(kwargs['step'])
        if len(attempts) == 1:
            helpers._report(project, 8, summary='OLD INPUT REPORT')
        elif len(attempts) == 4:
            # The second queue run includes one correction for its missing report.
            helpers._report(project, 8, summary='FRESH INPUT REPORT')
        return AgentResult('fake', len(attempts) != 1, False, _log_file(log_dir),
                           failure_kind='transient' if len(attempts) == 1 else None)

    deps = helpers._deps(state, invoke) if kind == 'script' else helpers._deps(project, state, invoke)
    assert run_queue(tmp_path, deps).blocked == [project.name]
    assert not (revision / reviewer.LOG).exists()
    stale_bytes = (revision / reviewer.REPORT).read_bytes()
    if kind == 'script':
        helpers._script(project, 'New script 2')
    else:
        helpers._render(project, 2)
    second = run_queue(tmp_path, deps)
    assert second.blocked == [project.name]
    assert not second.at_gate
    assert not (revision / reviewer.LOG).exists()
    diagnostics = tmp_path / 'topics/logs' / project.name / 'review-artifacts'
    assert any(path.read_bytes() == stale_bytes for path in diagnostics.glob('*.yaml'))
    # A genuine new input plus a newly written report remains consumable.
    if kind == 'script':
        helpers._script(project, 'New script 3')
    else:
        helpers._render(project, 3)
    final = run_queue(tmp_path, deps)
    assert final.at_gate == [project.name]
    assert read_yaml(revision / reviewer.LOG)['rounds'][-1]['summary'] == 'FRESH INPUT REPORT'


@pytest.mark.parametrize('mutate', ['answer', 'state'])
def test_failed_research_output_cannot_route_to_writer_before_retry_success(tmp_path, monkeypatch, mutate):
    from healthvideo.storage.files import write_yaml_atomic
    from healthvideo.workflows import production_retry
    from tests.workflows.test_script_review import _deps, _queue

    project = _queue(tmp_path)
    questions = project / 'revisions/001/script/questions.yaml'
    write_yaml_atomic(questions, {'questions': [{'id': 'Q1', 'ask': 'Question'}]})
    state = {'value': WorkflowState.DRAFT_READY}
    clock = {'now': datetime(2026, 11, 14, tzinfo=UTC)}
    monkeypatch.setattr(production_retry, '_now', lambda: clock['now'])
    calls = []
    def invoke(*args, log_dir, **kwargs):
        calls.append(kwargs['step'])
        if kwargs['step'] == 'research':
            write_yaml_atomic(questions, {'questions': [{'id': 'Q1', 'ask': 'Question',
                                                       'answer': 'Partial', 'claim_ids': ['C1']}]})
            if mutate == 'state':
                state['value'] = WorkflowState.EVIDENCE_READY
            return AgentResult('fake', False, False, _log_file(log_dir), failure_kind='transient')
        return AgentResult('fake', True, False, _log_file(log_dir))
    deps = _deps(state, invoke)
    assert run_queue(tmp_path, deps).blocked == [project.name]
    assert run_queue(tmp_path, deps).blocked == [project.name]
    assert calls == ['research']
    clock['now'] += timedelta(seconds=120)
    run_queue(tmp_path, deps)
    assert calls == ['research', 'research']
    assert read_yaml(tmp_path / 'topics/logs' / project.name / 'agent-retry.yaml')['steps']['research']['attempts'] == 2


def test_all_overloaded_cli_slots_remain_capped_across_restarted_queue_ticks(tmp_path, monkeypatch):
    from healthvideo.workflows import production_retry

    monkeypatch.setattr('healthvideo.process.shutil.which', lambda _: None)
    clock = {'now': datetime(2026, 11, 14, tzinfo=UTC)}
    monkeypatch.setattr(production_retry, '_now', lambda: clock['now'])
    entry = _entry('overload-topic')
    add_to_queue(tmp_path, entry)
    project = tmp_path / 'projects' / entry.slug
    project.mkdir(parents=True)
    calls = []
    slots = [ModelSlot(cli='agy', model='fake-agy'), ModelSlot(cli='codex', model='fake-codex')]

    def fake_cli(argv, **kwargs):
        calls.append(argv[0])
        return subprocess.CompletedProcess(argv, 1, '', 'UNAVAILABLE (code 503): overloaded')

    def invoke(_slots, prompt, **kwargs):
        return invoke_with_failover(slots, prompt, **kwargs, runner=fake_cli, now=lambda: clock['now'])

    for attempt in range(1, 5):
        # Reconstruct the queue dependencies and quota book from disk each time.
        deps = RunDeps(create_project=lambda *_: project,
                       read_state=lambda _: WorkflowState.TOPIC_SELECTED,
                       reject_note=lambda _: None, python_steps={},
                       changed_code_paths=lambda _: [], invoke=invoke)
        assert run_queue(tmp_path, deps).blocked == [entry.slug]
        assert len(calls) == min(attempt, 3) * 2
        stored = read_yaml(tmp_path / 'topics/logs' / entry.slug / 'agent-retry.yaml')
        assert stored['steps']['research']['attempts'] == min(attempt, 3)
        # Expire both the 120/600s queue backoff and every provider's 10min busy rest.
        clock['now'] += timedelta(minutes=11)
    assert not (tmp_path / 'topics/logs' / entry.slug / 'waiting-model.txt').exists()


@pytest.mark.parametrize('interrupted', [False, True])
def test_quarantined_review_remains_diagnostic_on_quota_or_interrupt(tmp_path, interrupted):
    from tests.workflows import test_script_review as helpers

    project = helpers._queue(tmp_path)
    helpers._report(project, summary='Stale report before interrupted invocation')
    source = project / 'revisions/001/reviews/script-review.yaml'
    stale_bytes = source.read_bytes()
    def invoke(*args, **kwargs):
        raise KeyboardInterrupt if interrupted else AllAgentsExhausted(datetime.now(UTC) + timedelta(hours=1))
    deps = helpers._deps({'value': WorkflowState.DRAFT_READY}, invoke)
    if interrupted:
        with pytest.raises(KeyboardInterrupt):
            run_queue(tmp_path, deps)
    else:
        assert run_queue(tmp_path, deps).waiting_model == [project.name]
    logs = tmp_path / 'topics/logs' / project.name
    assert (logs / 'waiting-model.txt').exists() is not interrupted
    assert not source.exists()
    assert not (project / 'revisions/001/reviews/script-review-log.yaml').exists()
    assert any(path.read_bytes() == stale_bytes for path in (logs / 'review-artifacts').glob('*.yaml'))


@pytest.mark.parametrize('mutate', ['answer', 'state'])
def test_quota_partial_output_resumes_original_step_after_model_returns(tmp_path, monkeypatch, mutate):
    from healthvideo.storage.files import write_yaml_atomic
    from healthvideo.workflows import runner
    from tests.workflows.test_script_review import _deps, _queue

    project = _queue(tmp_path)
    questions = project / 'revisions/001/script/questions.yaml'
    write_yaml_atomic(questions, {'questions': [{'id': 'Q1', 'ask': 'Question'}]})
    state = {'value': WorkflowState.DRAFT_READY}
    clock = {'now': datetime.now(UTC)}
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock['now']
    monkeypatch.setattr(runner, 'datetime', Clock)
    calls = []
    def invoke(*args, log_dir, **kwargs):
        calls.append(kwargs['step'])
        if len(calls) == 1:
            write_yaml_atomic(questions, {'questions': [{'id': 'Q1', 'ask': 'Question', 'answer': 'Partial'}]})
            if mutate == 'state':
                state['value'] = WorkflowState.EVIDENCE_READY
            raise AllAgentsExhausted(clock['now'] + timedelta(seconds=120))
        if kwargs['step'] == 'draft':
            questions.unlink()
            state['value'] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return AgentResult('fake', True, False, _log_file(log_dir))
    deps = _deps(state, invoke)
    assert run_queue(tmp_path, deps).waiting_model == [project.name]
    assert run_queue(tmp_path, deps).waiting_model == [project.name]
    assert calls == ['research']
    clock['now'] += timedelta(seconds=120)
    assert run_queue(tmp_path, deps, once=True).advanced == [project.name]
    assert calls == ['research', 'research']
    assert run_queue(tmp_path, deps).at_gate == [project.name]
    assert calls == ['research', 'research', 'draft']
    logs = tmp_path / 'topics/logs' / project.name
    assert not (logs / 'waiting-model-step.yaml').exists()
    assert not (logs / 'agent-retry.yaml').exists()


def test_malformed_quota_resume_metadata_blocks_only_its_topic(tmp_path):
    deps, calls = _reliability_deps(tmp_path)
    metadata = tmp_path / 'topics/logs/broken/waiting-model-step.yaml'
    metadata.parent.mkdir(parents=True)
    metadata.write_text('version: 1\nstep: non-agent\nfingerprint: invalid\n')
    report = run_queue(tmp_path, deps)
    assert report.blocked == ['broken']
    assert report.at_gate == ['healthy']
    assert calls == ['healthy']


def test_quota_observes_own_partial_changes_without_resetting_transient_cap(tmp_path, monkeypatch):
    from healthvideo.storage.files import write_yaml_atomic
    from healthvideo.workflows import production_retry
    from tests.workflows.test_script_review import _deps, _queue

    project = _queue(tmp_path)
    questions = project / 'revisions/001/script/questions.yaml'
    write_yaml_atomic(questions, {'questions': [
        {'id': f'Q{i}', 'ask': f'Question {i}', 'answer': f'Answer {i}'} for i in range(5)
    ]})
    clock = {'now': datetime.now(UTC)}
    monkeypatch.setattr(production_retry, '_now', lambda: clock['now'])
    calls = []
    def invoke(*args, log_dir, **kwargs):
        calls.append(kwargs['step'])
        # Writers are explicitly allowed to remove answers already incorporated.
        remaining = read_yaml(questions)
        remaining['questions'].pop()
        write_yaml_atomic(questions, remaining)
        if len(calls) % 2 == 0:
            raise AllAgentsExhausted(datetime.now(UTC) - timedelta(seconds=1))
        return AgentResult('fake', False, False, _log_file(log_dir), failure_kind='transient')
    deps = _deps({'value': WorkflowState.EVIDENCE_READY}, invoke)
    sidecar = tmp_path / 'topics/logs' / project.name / 'agent-retry.yaml'
    for attempts in [1, 1, 2, 2, 3]:
        run_queue(tmp_path, deps)
        assert read_yaml(sidecar)['steps']['draft']['attempts'] == attempts
        clock['now'] += timedelta(seconds=600)
    run_queue(tmp_path, deps)
    assert calls == ['draft'] * 5


def _entry(
    slug: str = "tang-huyet-ap",
    *,
    title: str = "Tăng huyết áp thầm lặng",
    question: str = "Vì sao huyết áp cao làm dày thành mạch?",
    doctor_note: str | None = "Lưu ý nhấn mạnh đo huyết áp tại nhà.",
) -> QueueEntry:
    return QueueEntry(
        slug=slug,
        title=title,
        question=question,
        doctor_note=doctor_note,
        added=date(2026, 10, 22),
    )


def _log_file(log_dir: Path, name: str = "fake-codex.log") -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / name
    log_path.write_text("fake agent log\n", encoding="utf-8")
    return log_path


def test_run_reviews_visuals_after_produce_before_video_gate(tmp_path):
    entry = _entry()
    add_to_queue(tmp_path, entry)
    project = tmp_path / 'projects' / entry.slug
    project.mkdir(parents=True)
    state = {'value': WorkflowState.MEDICALLY_APPROVED, 'pending': False, 'reviewed': False}
    calls = []

    def produce(_project):
        calls.append('produce')
        state['value'] = WorkflowState.AWAITING_VIDEO_REVIEW if state['reviewed'] else WorkflowState.PRODUCTION_IN_PROGRESS
        state['pending'] = not state['reviewed']

    def invoke(agents, prompt, *, cwd, log_dir, **_):
        assert 'visual-review.yaml' in prompt
        assert state['value'] == WorkflowState.PRODUCTION_IN_PROGRESS
        calls.append('visual_review')
        state['reviewed'] = True
        return AgentResult('codex', True, False, _log_file(log_dir))

    deps = RunDeps(
        create_project=lambda *_: project, read_state=lambda _: state['value'],
        reject_note=lambda _: None, python_steps={'produce': produce},
        changed_code_paths=lambda _: [], invoke=invoke,
        visual_review_pending=lambda _: state['pending'],
    )
    result = run_queue(tmp_path, deps)
    assert calls == ['produce', 'visual_review', 'produce']
    assert result.at_gate == [entry.slug]
    assert not result.blocked


def test_run_stops_at_medical_gate(tmp_path: Path) -> None:
    entry = _entry("tang-huyet-ap")
    add_to_queue(tmp_path, entry)
    stale_block = tmp_path / "topics" / "logs" / "tang-huyet-ap" / "blocked.txt"
    stale_block.parent.mkdir(parents=True)
    stale_block.write_text("lỗi từ lần chạy trước\n", encoding="utf-8")

    states: dict[str, WorkflowState] = {}
    created: list[str] = []
    prompts: list[str] = []

    def create_project(root: Path, item: QueueEntry) -> Path:
        project_dir = root / "projects" / item.slug
        project_dir.mkdir(parents=True, exist_ok=True)
        states[item.slug] = WorkflowState.TOPIC_SELECTED
        created.append(item.slug)
        return project_dir

    def fake_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
        **_: Any,
    ) -> AgentResult:
        prompts.append(prompt)
        slug = log_dir.name
        if states[slug] == WorkflowState.TOPIC_SELECTED:
            states[slug] = WorkflowState.EVIDENCE_READY
        elif states[slug] == WorkflowState.EVIDENCE_READY:
            states[slug] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir),
        )

    deps = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=fake_invoke,
    )

    report = run_queue(tmp_path, deps)

    assert created == ["tang-huyet-ap"]
    assert len(prompts) == 2
    assert states["tang-huyet-ap"] == WorkflowState.AWAITING_MEDICAL_REVIEW
    assert report.advanced == ["tang-huyet-ap"]
    assert report.at_gate == ["tang-huyet-ap"]
    assert report.blocked == []
    assert report.waiting_model == []
    assert not stale_block.exists()


def test_run_rerun_resumes_same_step(tmp_path: Path, monkeypatch) -> None:
    from healthvideo.workflows import production_retry

    clock = {'now': datetime(2026, 11, 14, tzinfo=UTC)}
    monkeypatch.setattr(production_retry, '_now', lambda: clock['now'])
    entry = _entry("suy-tim-man")
    add_to_queue(tmp_path, entry)

    states: dict[str, WorkflowState] = {}
    created_calls: list[str] = []
    run1_prompts: list[str] = []
    run2_prompts: list[str] = []

    def create_project(root: Path, item: QueueEntry) -> Path:
        project_dir = root / "projects" / item.slug
        project_dir.mkdir(parents=True, exist_ok=True)
        states[item.slug] = WorkflowState.TOPIC_SELECTED
        created_calls.append(item.slug)
        return project_dir

    def interrupted_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
        **_: Any,
    ) -> AgentResult:
        run1_prompts.append(prompt)
        return AgentResult(
            agent="codex",
            ok=False,
            quota_exhausted=False,
            log_path=_log_file(log_dir, "interrupted.log"),
            failure_kind="transient",
        )

    deps1 = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=interrupted_invoke,
    )

    report1 = run_queue(tmp_path, deps1)

    assert report1.blocked == ["suy-tim-man"]
    assert report1.advanced == []
    assert states["suy-tim-man"] == WorkflowState.TOPIC_SELECTED
    blocked_file = tmp_path / "topics" / "logs" / "suy-tim-man" / "blocked.txt"
    assert blocked_file.is_file()
    assert "interrupted.log" in blocked_file.read_text(encoding="utf-8")

    def normal_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
        **_: Any,
    ) -> AgentResult:
        run2_prompts.append(prompt)
        slug = log_dir.name
        if states[slug] == WorkflowState.TOPIC_SELECTED:
            states[slug] = WorkflowState.EVIDENCE_READY
        elif states[slug] == WorkflowState.EVIDENCE_READY:
            states[slug] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir, "resumed.log"),
        )

    deps2 = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=normal_invoke,
    )

    clock['now'] += timedelta(seconds=120)
    report2 = run_queue(tmp_path, deps2)

    assert created_calls == ["suy-tim-man"]
    expected_research_prompt = render_prompt(
        "research",
        project=str(tmp_path / "projects" / "suy-tim-man"),
        slug=entry.slug,
        title=entry.title,
        question=entry.question,
        doctor_note=entry.doctor_note or "",
    )
    assert run1_prompts == [expected_research_prompt]
    assert run2_prompts[0] == expected_research_prompt
    assert report2.advanced == ["suy-tim-man"]
    assert report2.at_gate == ["suy-tim-man"]
    assert report2.blocked == []


def test_unchanged_state_marks_blocked(tmp_path: Path) -> None:
    entry = _entry("gan-nhiem-mo")
    add_to_queue(tmp_path, entry)

    states: dict[str, WorkflowState] = {}

    def create_project(root: Path, item: QueueEntry) -> Path:
        project_dir = root / "projects" / item.slug
        project_dir.mkdir(parents=True, exist_ok=True)
        states[item.slug] = WorkflowState.TOPIC_SELECTED
        return project_dir

    def noop_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
        **_: Any,
    ) -> AgentResult:
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir, "noop.log"),
        )

    deps = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=noop_invoke,
    )

    report = run_queue(tmp_path, deps)

    assert report.blocked == ["gan-nhiem-mo"]
    assert report.advanced == []
    assert report.at_gate == []
    blocked_text = (
        tmp_path / "topics" / "logs" / "gan-nhiem-mo" / "blocked.txt"
    ).read_text(encoding="utf-8")
    assert "agent không làm đổi trạng thái" in blocked_text


def _quota_deps(states: dict[str, WorkflowState], exhausted: set[str], calls: list) -> RunDeps:
    def create_project(root: Path, item: QueueEntry) -> Path:
        project_dir = root / "projects" / item.slug
        project_dir.mkdir(parents=True, exist_ok=True)
        states[item.slug] = WorkflowState.TOPIC_SELECTED
        return project_dir

    def invoke(slots: Any, prompt: str, *, cwd: Path, log_dir: Path, **kwargs: Any) -> AgentResult:
        calls.append((list(slots), kwargs))
        slug = kwargs["slug"]
        if slug in exhausted:
            raise AllAgentsExhausted(datetime.now(UTC) + timedelta(hours=2))
        states[slug] = WorkflowState.EVIDENCE_READY
        return AgentResult(agent="codex", ok=True, quota_exhausted=False, log_path=_log_file(log_dir))

    return RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=invoke,
    )


def test_exhausted_topic_waits_others_continue(tmp_path: Path) -> None:
    add_to_queue(tmp_path, _entry("chu-de-1"))
    add_to_queue(tmp_path, _entry("chu-de-2"))
    states: dict[str, WorkflowState] = {}

    report = run_queue(tmp_path, _quota_deps(states, {"chu-de-1"}, []), once=False,
                       max_steps_per_topic=1)

    assert report.waiting_model == ["chu-de-1"]
    assert "chu-de-2" in report.advanced
    assert report.blocked == ["chu-de-2"]  # only the step cap stops it
    assert states["chu-de-1"] == WorkflowState.TOPIC_SELECTED
    waiting = tmp_path / "topics/logs/chu-de-1/waiting-model.txt"
    assert datetime.fromisoformat(waiting.read_text(encoding="utf-8")) > datetime.now(UTC)

    calls: list = []
    again = run_queue(tmp_path, _quota_deps(states, set(), calls), max_steps_per_topic=1)
    assert again.waiting_model == ["chu-de-1"]  # model not back yet: skipped, not invoked
    assert all(kwargs["slug"] != "chu-de-1" for _, kwargs in calls)


def test_waiting_topic_resumes_after_return(tmp_path: Path) -> None:
    add_to_queue(tmp_path, _entry("chu-de-1"))
    waiting = tmp_path / "topics/logs/chu-de-1/waiting-model.txt"
    waiting.parent.mkdir(parents=True)
    waiting.write_text((datetime.now(UTC) - timedelta(minutes=1)).isoformat(), encoding="utf-8")
    states: dict[str, WorkflowState] = {}

    report = run_queue(tmp_path, _quota_deps(states, set(), []), max_steps_per_topic=1)

    assert report.waiting_model == []
    assert "chu-de-1" in report.advanced
    assert not waiting.exists()


def test_code_changes_recorded(tmp_path: Path) -> None:
    entry = _entry("xo-vua-dong-mach")
    add_to_queue(tmp_path, entry)

    states: dict[str, WorkflowState] = {}
    current_changed: list[Path] = []

    def create_project(root: Path, item: QueueEntry) -> Path:
        project_dir = root / "projects" / item.slug
        project_dir.mkdir(parents=True, exist_ok=True)
        states[item.slug] = WorkflowState.TOPIC_SELECTED
        return project_dir

    def fake_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
        **_: Any,
    ) -> AgentResult:
        slug = log_dir.name
        if states[slug] == WorkflowState.TOPIC_SELECTED:
            states[slug] = WorkflowState.EVIDENCE_READY
            current_changed[:] = [Path("video/src/anatomy/ArteryWall.tsx")]
        elif states[slug] == WorkflowState.EVIDENCE_READY:
            states[slug] = WorkflowState.AWAITING_MEDICAL_REVIEW
            current_changed[:] = [
                Path("video/src/anatomy/ArteryWall.tsx"),
                Path("video/src/anatomy/ArteryWall.test.tsx"),
            ]
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir),
        )

    deps = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: list(current_changed),
        invoke=fake_invoke,
    )

    report = run_queue(tmp_path, deps)

    assert report.code_changes == [
        Path("video/src/anatomy/ArteryWall.tsx"),
        Path("video/src/anatomy/ArteryWall.test.tsx"),
    ]
    review_path = tmp_path / "topics" / "code-review.yaml"
    assert review_path.is_file()
    payload = read_yaml(review_path)
    assert payload["version"] == 1
    entries = payload["entries"]
    assert len(entries) == 2
    assert entries[0]["path"] == "video/src/anatomy/ArteryWall.tsx"
    assert entries[0]["slug"] == "xo-vua-dong-mach"
    datetime.fromisoformat(entries[0]["at"])
    assert entries[1]["path"] == "video/src/anatomy/ArteryWall.test.tsx"
    assert entries[1]["slug"] == "xo-vua-dong-mach"
    datetime.fromisoformat(entries[1]["at"])


def test_run_never_invokes_approve(tmp_path: Path) -> None:
    dep_field_names = {f.name for f in fields(RunDeps)}
    assert not any("approve" in name.lower() for name in dep_field_names)

    entry = _entry("kiem-soat-duong-huyet")
    add_to_queue(tmp_path, entry)

    states: dict[str, WorkflowState] = {}
    recorded_argv: list[list[str]] = []
    recorded_prompts: list[str] = []

    def create_project(root: Path, item: QueueEntry) -> Path:
        project_dir = root / "projects" / item.slug
        project_dir.mkdir(parents=True, exist_ok=True)
        states[item.slug] = WorkflowState.TOPIC_SELECTED
        return project_dir

    def fake_subprocess_runner(
        argv: list[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        recorded_argv.append(list(argv))
        prompt_text = kwargs.get("input") or ""
        recorded_prompts.append(prompt_text)
        slug = "kiem-soat-duong-huyet"
        if states[slug] == WorkflowState.TOPIC_SELECTED:
            states[slug] = WorkflowState.EVIDENCE_READY
        elif states[slug] == WorkflowState.EVIDENCE_READY or states[slug] == WorkflowState.NEEDS_MEDICAL_REVISION:
            states[slug] = WorkflowState.AWAITING_MEDICAL_REVIEW
        elif states[slug] == WorkflowState.NEEDS_PRODUCTION_REVISION:
            states[slug] = WorkflowState.PRODUCTION_IN_PROGRESS
        return subprocess.CompletedProcess(
            args=argv,
            returncode=0,
            stdout="ok\n",
            stderr="",
        )

    def invoke_via_fake_runner(
        slots: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
        **kwargs: Any,
    ) -> AgentResult:
        return invoke_with_failover(
            slots,
            prompt,
            cwd=cwd,
            log_dir=log_dir,
            runner=fake_subprocess_runner,
            **kwargs,
        )

    def fake_produce(project_dir: Path) -> None:
        states[project_dir.name] = WorkflowState.AWAITING_VIDEO_REVIEW

    # Every role on codex (prompt via stdin), as the old agents=(CODEX,) did.
    company = load_company()
    codex_only = company.model_copy(update={
        "tiers": {tier: [ModelSlot(cli="codex", model="gpt-6.1-sol")] for tier in company.tiers},
        "roles": {key: role.model_copy(update={"models": None})
                  for key, role in company.roles.items()},
    })
    deps = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: "Cần chỉnh lại mô tả cơ chế.",
        python_steps={"produce": fake_produce},
        changed_code_paths=lambda _root: [],
        invoke=invoke_via_fake_runner,
        company=codex_only,
    )

    run_queue(tmp_path, deps)
    assert states["kiem-soat-duong-huyet"] == WorkflowState.AWAITING_MEDICAL_REVIEW

    states["kiem-soat-duong-huyet"] = WorkflowState.NEEDS_MEDICAL_REVISION
    run_queue(tmp_path, deps)
    assert states["kiem-soat-duong-huyet"] == WorkflowState.AWAITING_MEDICAL_REVIEW

    states["kiem-soat-duong-huyet"] = WorkflowState.NEEDS_PRODUCTION_REVISION
    run_queue(tmp_path, deps)
    assert states["kiem-soat-duong-huyet"] == WorkflowState.AWAITING_VIDEO_REVIEW

    assert len(recorded_prompts) == 4
    for argv in recorded_argv:
        for token in argv:
            assert "review approve" not in token

    for prompt in recorded_prompts:
        stripped = prompt
        for rule in HARD_RULES:
            stripped = stripped.replace(rule, "")
        assert "review approve" not in stripped


def test_produce_runs_python_step(tmp_path: Path) -> None:
    entry = _entry("soi-than")
    add_to_queue(tmp_path, entry)

    project_dir = tmp_path / "projects" / entry.slug
    project_dir.mkdir(parents=True, exist_ok=True)
    states: dict[str, WorkflowState] = {
        entry.slug: WorkflowState.MEDICALLY_APPROVED,
    }
    produced_dirs: list[Path] = []
    agent_calls: list[str] = []

    def fake_produce(target_dir: Path) -> None:
        produced_dirs.append(target_dir)
        states[target_dir.name] = WorkflowState.AWAITING_VIDEO_REVIEW

    def unexpected_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
        **_: Any,
    ) -> AgentResult:
        agent_calls.append(prompt)
        raise AssertionError("Agent should not be invoked for produce step")

    deps = RunDeps(
        create_project=lambda root, item: root / "projects" / item.slug,
        read_state=lambda p: states[p.name],
        reject_note=lambda _p: None,
        python_steps={"produce": fake_produce},
        changed_code_paths=lambda _root: [],
        invoke=unexpected_invoke,
    )

    report = run_queue(tmp_path, deps)

    assert produced_dirs == [project_dir]
    assert agent_calls == []
    assert states[entry.slug] == WorkflowState.AWAITING_VIDEO_REVIEW
    assert report.advanced == [entry.slug]
    assert report.at_gate == [entry.slug]
    assert report.blocked == []


def test_once_runs_single_step(tmp_path: Path) -> None:
    entry1 = _entry("chu-de-mot")
    entry2 = _entry("chu-de-hai")
    add_to_queue(tmp_path, entry1)
    add_to_queue(tmp_path, entry2)

    states: dict[str, WorkflowState] = {}
    invoked_slugs: list[str] = []

    def create_project(root: Path, item: QueueEntry) -> Path:
        project_dir = root / "projects" / item.slug
        project_dir.mkdir(parents=True, exist_ok=True)
        states[item.slug] = WorkflowState.TOPIC_SELECTED
        return project_dir

    def fake_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
        **_: Any,
    ) -> AgentResult:
        slug = log_dir.name
        invoked_slugs.append(slug)
        if states[slug] == WorkflowState.TOPIC_SELECTED:
            states[slug] = WorkflowState.EVIDENCE_READY
        elif states[slug] == WorkflowState.EVIDENCE_READY:
            states[slug] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir),
        )

    deps = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=fake_invoke,
    )

    report = run_queue(tmp_path, deps, once=True)

    assert invoked_slugs == ["chu-de-mot"]
    assert states["chu-de-mot"] == WorkflowState.EVIDENCE_READY
    assert "chu-de-hai" not in states
    assert report.advanced == ["chu-de-mot"]
    assert report.at_gate == []
    assert report.blocked == []


def test_revise_step_gets_reject_note(tmp_path: Path) -> None:
    entry = _entry("benh-gut")
    add_to_queue(tmp_path, entry)

    project_dir = tmp_path / "projects" / entry.slug
    project_dir.mkdir(parents=True, exist_ok=True)
    states: dict[str, WorkflowState] = {
        entry.slug: WorkflowState.NEEDS_MEDICAL_REVISION,
    }
    captured_prompts: list[str] = []
    reject_note_calls: list[Path] = []
    note_text = "Bổ sung RCT về ngưỡng acid uric mục tiêu dưới 6 mg/dL."

    def get_reject_note(target_dir: Path) -> str | None:
        reject_note_calls.append(target_dir)
        return note_text

    def fake_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
        **_: Any,
    ) -> AgentResult:
        captured_prompts.append(prompt)
        states[log_dir.name] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir),
        )

    deps = RunDeps(
        create_project=lambda root, item: root / "projects" / item.slug,
        read_state=lambda p: states[p.name],
        reject_note=get_reject_note,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=fake_invoke,
    )

    report = run_queue(tmp_path, deps)

    assert reject_note_calls == [project_dir]
    assert len(captured_prompts) == 1
    assert note_text in captured_prompts[0]
    assert report.advanced == [entry.slug]
    assert report.at_gate == [entry.slug]


def test_agent_prompt_carries_doctor_standards(tmp_path: Path) -> None:
    from healthvideo.workflows import standards

    entry = _entry("benh-gut")
    add_to_queue(tmp_path, entry)
    (tmp_path / "projects" / entry.slug).mkdir(parents=True, exist_ok=True)
    standards.record(tmp_path, slug="chung", gate="medical", revision="001", kind="reject",
                     text="Cắt đuôi giải thích ở mọi dòng.")
    standards.record(tmp_path, slug="khac", gate="medical", revision="001", kind="reject",
                     text="Góp ý riêng cho chủ đề khác.")
    states = {entry.slug: WorkflowState.NEEDS_MEDICAL_REVISION}
    captured: list[str] = []

    def fake_invoke(agents: Any, prompt: str, *, cwd: Path, log_dir: Path, **_: Any) -> AgentResult:
        captured.append(prompt)
        states[log_dir.name] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return AgentResult(agent="codex", ok=True, quota_exhausted=False, log_path=_log_file(log_dir))

    deps = RunDeps(
        create_project=lambda root, item: root / "projects" / item.slug,
        read_state=lambda p: states[p.name],
        reject_note=lambda _p: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=fake_invoke,
    )
    run_queue(tmp_path, deps)

    assert len(captured) == 1
    assert "Chuẩn của bác sĩ" in captured[0]
    assert "Cắt đuôi giải thích ở mọi dòng." in captured[0]
    assert "Góp ý riêng cho chủ đề khác." not in captured[0]
    from healthvideo.workflows.runner import HARD_RULES
    assert captured[0].rstrip().endswith('\n'.join(f'- {rule}' for rule in HARD_RULES))


def test_agent_prompt_uses_pinned_v1_standards_and_filters_other_slug_feedback(
    tmp_path: Path,
) -> None:
    from healthvideo.storage.files import write_yaml_atomic
    from healthvideo.workflows import factory_standards, standards
    from tests.helpers import create_v2_project_fixture

    v1_entries = [
        {
            "id": f"std-{stage}-v1",
            "stage": stage,
            "version": 1,
            "text": "Chuẩn kịch bản v1 đã pin cho project." if stage == 1 else f"Chuẩn stage {stage} v1",
            "reviewer": "Bác sĩ",
            "accepted_at": datetime.now(UTC).isoformat(),
            "scope": "channel",
        }
        for stage in range(1, 5)
    ]
    write_yaml_atomic(
        tmp_path / factory_standards.STANDARDS_FILE,
        {"version": 1, "entries": v1_entries},
    )

    entry = _entry("muoi-va-huyet-ap-v2")
    add_to_queue(tmp_path, entry)
    project_dir = create_v2_project_fixture(tmp_path / "projects")
    factory_standards.pin_standards(tmp_path, project_dir)

    write_yaml_atomic(
        tmp_path / factory_standards.STANDARDS_FILE,
        {
            "version": 1,
            "entries": [
                *v1_entries,
                {
                    "id": "std-1-v2",
                    "stage": 1,
                    "version": 2,
                    "text": "Chuẩn kịch bản v2 mới chấp nhận sau.",
                    "reviewer": "Bác sĩ",
                    "accepted_at": datetime.now(UTC).isoformat(),
                    "scope": "channel",
                },
            ],
        },
    )
    assert factory_standards.accepted_standards(tmp_path)[1]["version"] == 2

    standards.record(
        tmp_path,
        slug=entry.slug,
        gate="medical",
        revision="001",
        kind="comment",
        text="Góp ý đúng của project.",
    )
    standards.record(
        tmp_path,
        slug="slug-khac",
        gate="medical",
        revision="001",
        kind="comment",
        text="Góp ý riêng của slug-khac không được lọt vào.",
    )

    states = {entry.slug: WorkflowState.NEEDS_MEDICAL_REVISION}
    captured: list[str] = []

    def fake_invoke(agents: Any, prompt: str, *, cwd: Path, log_dir: Path, **_: Any) -> AgentResult:
        captured.append(prompt)
        states[log_dir.name] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return AgentResult(agent="codex", ok=True, quota_exhausted=False, log_path=_log_file(log_dir))

    deps = RunDeps(
        create_project=lambda root, item: root / "projects" / item.slug,
        read_state=lambda p: states[p.name],
        reject_note=lambda _p: 'L01: sửa câu này theo góp ý bác sĩ.',
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=fake_invoke,
    )
    run_queue(tmp_path, deps)

    assert len(captured) == 1
    assert "Giai đoạn 1 · v1: Chuẩn kịch bản v1 đã pin cho project." in captured[0]
    assert "Chuẩn kịch bản v2 mới chấp nhận sau." not in captured[0]
    assert "Góp ý đúng của project." in captured[0]
    assert "Góp ý riêng của slug-khac không được lọt vào." not in captured[0]


def test_packaged_topic_is_not_reported_at_gate(tmp_path: Path) -> None:
    add_to_queue(tmp_path, _entry("da-dong-goi"))
    (tmp_path / "projects" / "da-dong-goi").mkdir(parents=True)
    deps = RunDeps(
        create_project=lambda root, item: root / "projects" / item.slug,
        read_state=lambda _project_dir: WorkflowState.PACKAGED,
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=lambda *a, **kw: None,
    )
    report = run_queue(tmp_path, deps)
    assert report.at_gate == [] and report.blocked == []


def test_produce_validation_failure_waits_for_changed_inputs(tmp_path):
    entry = _entry()
    add_to_queue(tmp_path, entry)
    project = tmp_path / 'projects' / entry.slug
    project.mkdir(parents=True)
    manifest = project / 'project.yaml'
    manifest.write_text('revision: 001', encoding='utf-8')
    calls = []

    def produce(_):
        calls.append('produce')
        raise ValueError('visual budget failed: chart_crop')

    deps = RunDeps(
        create_project=lambda *_: project,
        read_state=lambda _: WorkflowState.MEDICALLY_APPROVED,
        reject_note=lambda _: None, python_steps={'produce': produce},
        changed_code_paths=lambda _: [], visual_review_pending=lambda _: False,
    )
    for _ in range(3):
        assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert calls == ['produce']
    retry_file = tmp_path / 'topics/logs' / entry.slug / 'production-retry.yaml'
    assert retry_file.is_file()
    assert read_yaml(retry_file)['kind'] == 'validation'
    manifest.write_text('revision: 002', encoding='utf-8')
    run_queue(tmp_path, deps)
    assert calls == ['produce', 'produce']
    profile = tmp_path / 'profiles/voice.yaml'
    profile.parent.mkdir()
    profile.write_text('model: changed', encoding='utf-8')
    run_queue(tmp_path, deps)
    assert len(calls) == 3
    code = tmp_path / 'src/healthvideo/workflows/produce.py'
    code.parent.mkdir(parents=True)
    code.write_text('# fixed production validation', encoding='utf-8')
    run_queue(tmp_path, deps)
    assert len(calls) == 4
    for relative in ('assets/illustration.png', 'reviews/visual-review.yaml',
                     'reviews/visual/candidates.yaml', 'storyboard/storyboard.yaml'):
        artifact = project / 'revisions/001' / relative
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b'changed')
        before = len(calls)
        run_queue(tmp_path, deps)
        assert len(calls) == before + 1
        run_queue(tmp_path, deps)
        assert len(calls) == before + 1


def test_transient_produce_failure_bounds_retries_with_backoff_and_clears_on_success(
    tmp_path, monkeypatch
):
    from healthvideo.workflows import production_retry

    entry = _entry()
    add_to_queue(tmp_path, entry)
    project = tmp_path / 'projects' / entry.slug
    project.mkdir(parents=True)
    manifest = project / 'project.yaml'
    manifest.write_text('revision: 001', encoding='utf-8')
    clock = {'now': datetime(2026, 10, 25, 9, 0, 0, tzinfo=UTC)}
    monkeypatch.setattr(production_retry, '_now', lambda: clock['now'])
    state = {'value': WorkflowState.MEDICALLY_APPROVED, 'should_fail': True}
    calls = []

    def produce(_):
        calls.append(clock['now'])
        if state['should_fail']:
            raise OSError('temporary network failure')
        state['value'] = WorkflowState.AWAITING_VIDEO_REVIEW

    deps = RunDeps(
        create_project=lambda *_: project,
        read_state=lambda _: state['value'],
        reject_note=lambda _: None, python_steps={'produce': produce},
        changed_code_paths=lambda _: [], visual_review_pending=lambda _: False,
    )
    retry_file = tmp_path / 'topics/logs' / entry.slug / 'production-retry.yaml'

    # Attempt 1 fails -> backoff 120s
    assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert len(calls) == 1
    assert read_yaml(retry_file)['attempts'] == 1

    # Before 120s: held without calling produce
    clock['now'] += timedelta(seconds=60)
    assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert len(calls) == 1

    # At 120s: attempt 2 fails -> backoff 600s
    clock['now'] += timedelta(seconds=60)
    assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert len(calls) == 2
    assert read_yaml(retry_file)['attempts'] == 2

    # Before 600s: held
    clock['now'] += timedelta(seconds=599)
    assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert len(calls) == 2

    # At 600s: attempt 3 fails -> permanently held for this fingerprint
    clock['now'] += timedelta(seconds=1)
    assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert len(calls) == 3
    assert read_yaml(retry_file)['attempts'] == 3
    assert read_yaml(retry_file)['retry_after'] is None

    # Even after hours/restart, attempt 4 is not made automatically
    clock['now'] += timedelta(hours=5)
    assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert len(calls) == 3

    # Input repair + successful produce clears retry record
    state['should_fail'] = False
    manifest.write_text('revision: 002', encoding='utf-8')
    report = run_queue(tmp_path, deps)
    assert len(calls) == 4
    assert report.at_gate == [entry.slug]
    assert not retry_file.exists()


def test_corrupt_retry_file_blocks_without_calling_produce(tmp_path):
    entry = _entry()
    add_to_queue(tmp_path, entry)
    project = tmp_path / 'projects' / entry.slug
    project.mkdir(parents=True)
    retry_file = tmp_path / 'topics/logs' / entry.slug / 'production-retry.yaml'
    retry_file.parent.mkdir(parents=True, exist_ok=True)
    retry_file.write_text(':::corrupt-yaml:::\n[', encoding='utf-8')
    calls = []

    deps = RunDeps(
        create_project=lambda *_: project,
        read_state=lambda _: WorkflowState.MEDICALLY_APPROVED,
        reject_note=lambda _: None, python_steps={'produce': lambda _: calls.append('produce')},
        changed_code_paths=lambda _: [], visual_review_pending=lambda _: False,
    )
    report = run_queue(tmp_path, deps)
    assert report.blocked == [entry.slug]
    assert calls == []


def test_paused_project_is_skipped_by_run_queue(tmp_path):
    entry = _entry()
    add_to_queue(tmp_path, entry)
    paused = tmp_path / 'topics/logs' / entry.slug / 'paused.yaml'
    paused.parent.mkdir(parents=True, exist_ok=True)
    paused.write_text('paused_at: "2026-11-15T20:00:00Z"\n', encoding='utf-8')
    calls = []

    deps = RunDeps(
        create_project=lambda *_: calls.append('create') or (tmp_path / 'projects' / entry.slug),
        read_state=lambda _: WorkflowState.TOPIC_SELECTED,
        reject_note=lambda _: None,
        python_steps={},
        invoke=lambda *_, **__: calls.append('invoke') or AgentResult('r', True, False, tmp_path / 'r.log', 'm'),
        changed_code_paths=lambda _: [],
        visual_review_pending=lambda _: False,
    )
    report = run_queue(tmp_path, deps)
    assert calls == []
    assert report.blocked == []
    assert report.at_gate == []
    assert not (tmp_path / 'projects' / entry.slug).exists()


@pytest.mark.parametrize('mode', ['raise', 'fail_result'])
def test_pause_during_running_step_stops_without_blocking(tmp_path, mode):
    entry = _entry()
    add_to_queue(tmp_path, entry)
    project = tmp_path / 'projects' / entry.slug
    project.mkdir(parents=True)
    paused = tmp_path / 'topics/logs' / entry.slug / 'paused.yaml'
    state = {'value': WorkflowState.TOPIC_SELECTED, 'calls': 0}

    def fake_invoke(*_, log_dir, **__):
        state['calls'] += 1
        if state['calls'] == 1:
            paused.parent.mkdir(parents=True, exist_ok=True)
            paused.write_text('paused_at: "2026-11-15T20:00:00Z"\n', encoding='utf-8')
            if mode == 'raise':
                raise RuntimeError('cancelled by doctor')
            log_file = log_dir / 'cancelled.log'
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.write_text('cancelled\n', encoding='utf-8')
            return AgentResult('expert', False, False, log_file, 'm', 'agent_error')
        state['value'] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return AgentResult('expert', True, False, tmp_path / 'ok.log', 'm')

    deps = RunDeps(
        create_project=lambda *_: project,
        read_state=lambda _: state['value'],
        reject_note=lambda _: None,
        python_steps={},
        invoke=fake_invoke,
        changed_code_paths=lambda _: [],
        visual_review_pending=lambda _: False,
        expert_brief_ready=lambda _: state['calls'] >= 2,
    )
    first_report = run_queue(tmp_path, deps)
    assert first_report.blocked == []
    assert not (paused.parent / 'blocked.txt').exists()
    assert not (paused.parent / 'agent-retry.yaml').exists()
    assert state['calls'] == 1

    paused.unlink()
    resumed_report = run_queue(tmp_path, deps)
    assert state['calls'] == 2
    assert resumed_report.at_gate == [entry.slug]
