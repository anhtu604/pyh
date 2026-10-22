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
    WorkflowState.DRAFT_READY: "draft",
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
