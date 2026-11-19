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
