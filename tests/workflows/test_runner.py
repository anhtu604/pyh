"""Tests for workflow state to factory step mapping."""

import typing

import pytest

from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.workflows.runner import AGENT_STEPS, StepKind, next_step

EXPECTED_STEPS: dict[WorkflowState | None, StepKind] = {
    None: "create",
    WorkflowState.TOPIC_SELECTED: "research",
    WorkflowState.RESEARCH_IN_PROGRESS: "research",
    WorkflowState.EVIDENCE_READY: "draft",
    WorkflowState.DRAFT_READY: "script_review",
    WorkflowState.MEDICALLY_APPROVED: "produce",
    WorkflowState.PRODUCTION_IN_PROGRESS: "produce",
    WorkflowState.NEEDS_MEDICAL_REVISION: "revise_medical",
    WorkflowState.NEEDS_PRODUCTION_REVISION: "revise_production",
}


@pytest.mark.parametrize("state", [None, *WorkflowState])
def test_next_step_mapping(state: WorkflowState | None) -> None:
    assert next_step(state) == EXPECTED_STEPS.get(state)


def test_gates_never_have_a_step() -> None:
    assert next_step(WorkflowState.AWAITING_MEDICAL_REVIEW) is None
    assert next_step(WorkflowState.AWAITING_VIDEO_REVIEW) is None


def test_agent_steps_subset_of_step_kinds() -> None:
    assert AGENT_STEPS <= set(typing.get_args(StepKind))


@pytest.mark.parametrize('parallel', [False, True])
@pytest.mark.parametrize('plan_status', ['missing', 'valid', 'invalid'])
@pytest.mark.parametrize('repaired', [False, True])
def test_existing_invalid_shorts_plan_precedes_visual_review(
    tmp_path, monkeypatch, parallel, plan_status, repaired,
):
    from datetime import UTC, datetime

    from healthvideo.agents import AgentResult
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.domain.queue import QueueEntry
    from healthvideo.storage.files import read_yaml
    from healthvideo.workflows import runner
    from healthvideo.workflows.gate_review import approve_gate
    from tests.helpers import create_v2_project_fixture

    project = create_v2_project_fixture(
        tmp_path / 'projects', state=WorkflowState.AWAITING_MEDICAL_REVIEW,
    )
    approve_gate(project, GateKind.MEDICAL, reviewer='Fixture', now=datetime.now(UTC))
    plan = project / 'revisions/001/posts/shorts-plan.yaml'
    if plan_status != 'missing':
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text('clips: []\n', encoding='utf-8')
    ready = plan_status == 'valid'
    state = WorkflowState.MEDICALLY_APPROVED
    steps = []
    prompts = []
    problem = 'CL02: clip dọc cần ít nhất 2 anatomy.subject khác nhau'
    monkeypatch.setattr(runner, '_shorts_plan_validation_problem', lambda _: problem)

    def invoke(slots, prompt, **kwargs):
        nonlocal ready
        steps.append(kwargs['step'])
        prompts.append(prompt)
        if kwargs['step'] == 'shorts_plan' and repaired:
            ready = True
        return AgentResult('fixture', True, False, kwargs['log_dir'] / 'agent.log')

    def produce(_):
        nonlocal state
        state = WorkflowState.AWAITING_VIDEO_REVIEW

    deps = runner.RunDeps(
        create_project=lambda *a: project,
        read_state=lambda _: state,
        reject_note=lambda _: None,
        python_steps={'produce': produce},
        invoke=invoke,
        changed_code_paths=lambda _: [],
        shorts_plan_ready=lambda _: ready,
        visual_review_pending=lambda _: True,
        parallel_branches=parallel,
    )
    entry = QueueEntry(slug=project.name, title='Test', question='Test?', added='2026-11-19')
    report = runner.RunReport()
    runner._run_topic(tmp_path, deps, entry, report, max_steps_per_topic=2)

    expected = 'shorts_plan' if plan_status == 'invalid' else 'visual_review'
    assert steps == ([expected, 'visual_review'] if plan_status == 'invalid' and repaired else [expected])
    if plan_status == 'invalid':
        assert problem in prompts[0]
        assert prompts[0].index(problem) < prompts[0].index('## Quy tắc cứng')
        if not repaired:
            assert report.blocked == [project.name]
            log_dir = tmp_path / 'topics/logs' / project.name
            assert problem in (log_dir / 'blocked.txt').read_text(encoding='utf-8')
            retry = read_yaml(log_dir / 'agent-retry.yaml')['steps']['shorts_plan']
            assert retry['kind'] == 'validation'
            assert problem in retry['reason']
        else:
            assert report.blocked == []


@pytest.mark.parametrize('control', ['forced', 'production_retry', 'step_limit'])
@pytest.mark.parametrize('parallel', [False, True])
def test_shorts_repair_preserves_runner_controls(tmp_path, monkeypatch, control, parallel):
    from healthvideo.domain.queue import QueueEntry
    from healthvideo.workflows import runner
    from tests.helpers import create_v2_project_fixture

    project = create_v2_project_fixture(tmp_path / 'projects')
    plan = project / 'revisions/001/posts/shorts-plan.yaml'
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text('clips: []\n', encoding='utf-8')
    steps = []
    monkeypatch.setattr(runner, 'retry_status', lambda *a: {
        'allowed': True, 'attempts': int(control == 'production_retry'),
    })
    monkeypatch.setattr(runner, 'model_resume_step', lambda *a: 'posts' if control == 'forced' else None)

    def invoke(*args, **kwargs):
        steps.append(kwargs['step'])
        return 'ok', None, None, {}

    monkeypatch.setattr(runner, '_run_agent_invocation', invoke)
    deps = runner.RunDeps(
        create_project=lambda *a: project,
        read_state=lambda _: WorkflowState.MEDICALLY_APPROVED,
        reject_note=lambda _: None,
        python_steps={'produce': lambda _: steps.append('produce')},
        changed_code_paths=lambda _: [],
        shorts_plan_ready=lambda _: False,
        visual_review_pending=lambda _: True,
        parallel_branches=parallel,
    )
    entry = QueueEntry(slug=project.name, title='Test', question='Test?', added='2026-11-19')
    report = runner.RunReport()
    runner._run_topic(
        tmp_path, deps, entry, report, once=True,
        max_steps_per_topic=0 if control == 'step_limit' else 1,
    )
    assert steps == {'forced': ['posts'], 'production_retry': ['produce'], 'step_limit': []}[control]
    assert report.blocked == ([project.name] if control == 'step_limit' else [])


@pytest.mark.parametrize('returned_result', [False, True])
@pytest.mark.parametrize('error,kind', [
    (ConnectionError('offline'), 'transient'),
    (TimeoutError('late'), 'transient'),
    (PermissionError('sharing violation'), 'transient'),
    (FileNotFoundError('binary'), 'configuration'),
])
def test_runner_persists_shared_exception_classification(tmp_path, monkeypatch, error, kind, returned_result):
    from healthvideo.domain.queue import QueueEntry
    from healthvideo.storage.files import read_yaml
    from healthvideo.workflows import runner
    from tests.helpers import create_v2_project_fixture

    project = create_v2_project_fixture(tmp_path / 'projects')
    monkeypatch.setattr(runner, '_build_step_prompt', lambda *a, **kw: 'fixture prompt')

    def fail(*args, **kwargs):
        if returned_result:
            from healthvideo.agents import AgentResult

            log = tmp_path / 'agent.log'
            log.write_text(str(error), encoding='utf-8')
            return AgentResult('fixture', False, False, log, failure_kind=kind)
        raise error

    deps = runner.RunDeps(create_project=lambda *a: project, read_state=lambda _: None,
                          reject_note=lambda _: None, python_steps={}, invoke=fail,
                          changed_code_paths=lambda _: [])
    entry = QueueEntry(slug=project.name, title='Test', question='Test?', added='2026-11-19')
    status, *_ = runner._run_agent_invocation(tmp_path, deps, entry, project,
        runner.RunReport(), step='research', brief_context='fixture', log_dir=tmp_path / 'logs')
    assert status == 'blocked'
    record = read_yaml(tmp_path / 'topics/logs' / project.name / 'agent-retry.yaml')['steps']['research']
    assert record['kind'] == kind
    if returned_result and isinstance(error, PermissionError):
        assert 'sharing violation' in record['reason']
    assert bool(record['retry_after']) == (kind == 'transient')
