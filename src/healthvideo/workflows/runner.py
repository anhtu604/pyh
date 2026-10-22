"""Select the next factory workflow step for a project state."""

from typing import Literal

from healthvideo.domain.project_v2 import WorkflowState

StepKind = Literal[
    "create",
    "research",
    "draft",
    "produce",
    "revise_medical",
    "revise_production",
]
AGENT_STEPS: frozenset[str] = frozenset(
    {"research", "draft", "revise_medical", "revise_production"}
)

_STEP_BY_STATE: dict[WorkflowState, StepKind] = {
    WorkflowState.TOPIC_SELECTED: "research",
    WorkflowState.RESEARCH_IN_PROGRESS: "research",
    WorkflowState.EVIDENCE_READY: "draft",
    WorkflowState.DRAFT_READY: "draft",
    WorkflowState.MEDICALLY_APPROVED: "produce",
    WorkflowState.PRODUCTION_IN_PROGRESS: "produce",
    WorkflowState.NEEDS_MEDICAL_REVISION: "revise_medical",
    WorkflowState.NEEDS_PRODUCTION_REVISION: "revise_production",
}


def next_step(state: WorkflowState | None) -> StepKind | None:
    """Return the next factory step for the given workflow state, or None."""
    if state is None:
        return "create"
    return _STEP_BY_STATE.get(state)
