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
@pytest.mark.parametrize('held_step', ['visual_review', 'produce'])
@pytest.mark.parametrize('rewrite_invalid', [False, True])
def test_run_topic_shorts_repair_through_all_hold_layers(
    tmp_path, parallel, plan_status, repaired, held_step, rewrite_invalid,
):
    """Exercise selection, invocation gating, validation and subsequent queue scans."""
    import json
    from datetime import UTC, datetime

    from healthvideo.agents import AgentResult
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.domain.queue import QueueEntry
    from healthvideo.storage.files import read_yaml, write_yaml_atomic
    from healthvideo.workflows import production_retry, runner
    from healthvideo.workflows.gate_review import approve_gate
    from healthvideo.workflows.shorts_plan import save_shorts_plan, shorts_plan_ready
    from tests.helpers import create_long_form_project_fixture

    project = create_long_form_project_fixture(tmp_path / 'projects')
    approve_gate(project, GateKind.MEDICAL, reviewer='Fixture', now=datetime.now(UTC))
    revision = project / 'revisions/001'
    approval = revision / 'reviews/medical-approval.yaml'
    approval_bytes = approval.read_bytes()
    plan = revision / 'posts/shorts-plan.yaml'
    plan_input = tmp_path / 'shorts-input.yaml'
    write_yaml_atomic(plan_input, {'schema_version': '1.0', 'clips': [{
        'id': 'CL01', 'title': 'Synthetic clip', 'hook_text': 'Synthetic hook',
        'start_scene_id': 'S01', 'end_scene_id': 'S02', 'target_seconds': 70,
        'caption': 'Synthetic caption [claim:C01].',
        'safety_caveat': 'Synthetic caveat [claim:C02].', 'safe_zone_checked': True,
    }]})
    save_shorts_plan(project, plan_input)
    valid_plan = plan.read_bytes()
    if plan_status == 'missing':
        plan.unlink()
    elif plan_status == 'invalid':
        data = read_yaml(plan)
        data['clips'][0]['end_scene_id'] = 'S01'  # drops the required caveat scene
        write_yaml_atomic(plan, data)
    assert shorts_plan_ready(project) == (plan_status == 'valid')
    entry = QueueEntry(slug=project.name, title='Test', question='Test?', added='2026-11-19')
    brief = json.dumps({'title': entry.title, 'question': entry.question,
                        'doctor_note': entry.doctor_note}, sort_keys=True)
    state = WorkflowState.MEDICALLY_APPROVED
    fingerprint = production_retry.agent_fingerprint(tmp_path, project, held_step, brief)
    production_retry.record_agent_failure(
        tmp_path, project, held_step, fingerprint, 'validation', ValueError('invalid clip input'),
    )
    production_retry.record_failure(tmp_path, project, state, ValueError('invalid clip input'))
    logs = tmp_path / 'topics/logs' / project.name
    (logs / 'blocked.txt').write_text('invalid clip input', encoding='utf-8')
    write_yaml_atomic(logs / 'leader-repair.yaml', {
        'revision': '001', 'phase': 'needs_attention', 'attempts': 20,
    })
    leader_bytes = (logs / 'leader-repair.yaml').read_bytes()
    production_bytes = (logs / 'production-retry.yaml').read_bytes()
    agent_bytes = (logs / 'agent-retry.yaml').read_bytes()
    steps = []

    def invoke(slots, prompt, **kwargs):
        step = kwargs['step']
        steps.append(step)
        if step == 'shorts_plan':
            # Selection must preserve every hold until the repair actually succeeds.
            assert (logs / 'agent-retry.yaml').read_bytes() == agent_bytes
            assert (logs / 'production-retry.yaml').read_bytes() == production_bytes
            assert (logs / 'blocked.txt').is_file()
            if repaired:
                plan.write_bytes(valid_plan)
            elif rewrite_invalid:
                plan.write_text(plan.read_text(encoding='utf-8') + '\n# failed repair\n', encoding='utf-8')
        return AgentResult('fixture', True, False, kwargs['log_dir'] / 'agent.log')

    def produce(_):
        nonlocal state
        assert shorts_plan_ready(project)
        steps.append('produce')
        state = WorkflowState.AWAITING_VIDEO_REVIEW

    deps = runner.RunDeps(
        create_project=lambda *a: pytest.fail('project already exists'),
        read_state=lambda _: state, reject_note=lambda _: None,
        python_steps={'produce': produce}, invoke=invoke, changed_code_paths=lambda _: [],
        shorts_plan_ready=shorts_plan_ready, visual_review_pending=lambda _: True,
        parallel_branches=parallel,
    )
    report = runner.RunReport()
    runner._run_topic(tmp_path, deps, entry, report, once=True)
    assert steps == (['shorts_plan'] if plan_status == 'invalid' else [])
    assert (logs / 'production-retry.yaml').read_bytes() == production_bytes
    assert (logs / 'leader-repair.yaml').read_bytes() == leader_bytes
    assert approval.read_bytes() == approval_bytes
    if plan_status == 'invalid' and repaired:
        assert not report.blocked
        assert production_retry.agent_fingerprint(tmp_path, project, held_step, brief) != fingerprint
        assert production_retry.outstanding_agent_retry(tmp_path, project, brief) is None
        assert production_retry.retry_status(tmp_path, project, state)['allowed']
        runner._run_topic(tmp_path, deps, entry, runner.RunReport())
        assert steps == ['shorts_plan', 'visual_review', 'produce']
    else:
        assert report.blocked == [project.name]
        for _ in range(3):
            again = runner.RunReport()
            runner._run_topic(tmp_path, deps, entry, again, once=True)
            assert again.blocked == [project.name]
        assert steps == (['shorts_plan'] if plan_status == 'invalid' else [])
        if plan_status == 'invalid':
            record = read_yaml(logs / 'agent-retry.yaml')['steps']['shorts_plan']
            assert record['kind'] == 'validation' and record['attempts'] == 1
            assert 'shorts-plan.yaml' in (logs / 'blocked.txt').read_text(encoding='utf-8')
        else:
            assert (logs / 'agent-retry.yaml').read_bytes() == agent_bytes
    assert approval.read_bytes() == approval_bytes


@pytest.mark.parametrize('held_step,kind', [
    ('visual_review', 'configuration'), ('visual_review', 'agent_error'),
    ('visual_review', 'transient'), ('posts', 'validation'),
])
def test_invalid_shorts_does_not_bypass_other_agent_holds(tmp_path, held_step, kind):
    import json

    from healthvideo.domain.queue import QueueEntry
    from healthvideo.workflows import production_retry, runner
    from tests.helpers import create_v2_project_fixture

    project = create_v2_project_fixture(tmp_path / 'projects')
    plan = project / 'revisions/001/posts/shorts-plan.yaml'
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text('clips: []\n', encoding='utf-8')
    entry = QueueEntry(slug=project.name, title='Test', question='Test?', added='2026-11-19')
    brief = json.dumps({'title': entry.title, 'question': entry.question,
                        'doctor_note': entry.doctor_note}, sort_keys=True)
    fingerprint = production_retry.agent_fingerprint(tmp_path, project, held_step, brief)
    production_retry.record_agent_failure(
        tmp_path, project, held_step, fingerprint, kind, ValueError('held input'),
    )
    deps = runner.RunDeps(
        create_project=lambda *a: project, read_state=lambda _: WorkflowState.MEDICALLY_APPROVED,
        reject_note=lambda _: None, python_steps={}, changed_code_paths=lambda _: [],
        invoke=lambda *a, **kw: pytest.fail('unrelated hold must remain effective'),
        shorts_plan_ready=lambda _: False,
    )
    report = runner.RunReport()
    runner._run_topic(tmp_path, deps, entry, report, once=True)
    assert report.blocked == [project.name]


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


@pytest.mark.parametrize('parallel', [False, True])
@pytest.mark.parametrize('plan_status', ['missing', 'valid', 'invalid'])
@pytest.mark.parametrize('repaired', [False, True])
def test_production_validation_hold_allows_only_invalid_shorts_repair(
    tmp_path, monkeypatch, parallel, plan_status, repaired,
):
    from datetime import UTC, datetime

    from healthvideo.agents import AgentResult
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.domain.queue import QueueEntry
    from healthvideo.storage.files import read_yaml
    from healthvideo.workflows import runner
    from healthvideo.workflows.gate_review import approve_gate
    from healthvideo.workflows.production_retry import record_failure, retry_status
    from tests.helpers import create_v2_project_fixture

    project = create_v2_project_fixture(
        tmp_path / 'projects', state=WorkflowState.AWAITING_MEDICAL_REVIEW,
    )
    approve_gate(project, GateKind.MEDICAL, reviewer='Fixture', now=datetime.now(UTC))
    state = WorkflowState.MEDICALLY_APPROVED
    plan = project / 'revisions/001/posts/shorts-plan.yaml'
    if plan_status != 'missing':
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text('clips: []\n', encoding='utf-8')
    ready = plan_status == 'valid'
    problem = 'CL02: clip dọc cần ít nhất 2 anatomy.subject khác nhau'
    monkeypatch.setattr(runner, '_shorts_plan_validation_problem', lambda _: problem)
    record_failure(tmp_path, project, state, ValueError(problem))
    assert not retry_status(tmp_path, project, state)['allowed']
    retry_path = tmp_path / 'topics/logs' / project.name / 'production-retry.yaml'
    original_retry = retry_path.read_bytes()
    steps = []
    prompts = []

    def invoke(slots, prompt, **kwargs):
        nonlocal ready
        steps.append(kwargs['step'])
        prompts.append(prompt)
        if repaired:
            ready = True
            plan.write_text('clips: [repaired]\n', encoding='utf-8')
        return AgentResult('fixture', True, False, kwargs['log_dir'] / 'agent.log')

    deps = runner.RunDeps(
        create_project=lambda *a: project,
        read_state=lambda _: state,
        reject_note=lambda _: None,
        python_steps={'produce': lambda _: pytest.fail('production must remain held')},
        invoke=invoke,
        changed_code_paths=lambda _: [],
        shorts_plan_ready=lambda _: ready,
        visual_review_pending=lambda _: True,
        parallel_branches=parallel,
    )
    entry = QueueEntry(slug=project.name, title='Test', question='Test?', added='2026-11-19')
    report = runner.RunReport()
    runner._run_topic(tmp_path, deps, entry, report, once=True)
    assert steps == (['shorts_plan'] if plan_status == 'invalid' else [])
    assert retry_path.read_bytes() == original_retry
    if plan_status == 'invalid':
        assert problem in prompts[0]
        assert report.blocked == ([] if repaired else [project.name])
        assert retry_status(tmp_path, project, state)['allowed'] == repaired
        if not repaired:
            # One validation attempt per agent input fingerprint, persisted across scans.
            log_dir = retry_path.parent
            record = read_yaml(log_dir / 'agent-retry.yaml')['steps']['shorts_plan']
            assert record['kind'] == 'validation'
            assert record['attempts'] == 1
            for _ in range(3):
                again = runner.RunReport()
                runner._run_topic(tmp_path, deps, entry, again, once=True)
                assert again.blocked == [project.name]
            assert steps == ['shorts_plan']
            assert problem in (log_dir / 'blocked.txt').read_text(encoding='utf-8')
    else:
        assert report.blocked == [project.name]


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
