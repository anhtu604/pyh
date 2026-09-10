import pytest

from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import (
    MAIN_RULES,
    TransitionContext,
    TransitionError,
    transition_v2,
)

MAIN_EDGES = {
    (WorkflowState.IDEA, WorkflowState.TOPIC_SELECTED),
    (WorkflowState.TOPIC_SELECTED, WorkflowState.AUTHOR_BRIEF_READY),
    (WorkflowState.AUTHOR_BRIEF_READY, WorkflowState.RESEARCH_IN_PROGRESS),
    (WorkflowState.RESEARCH_IN_PROGRESS, WorkflowState.EVIDENCE_READY),
    (WorkflowState.EVIDENCE_READY, WorkflowState.DRAFT_READY),
    (WorkflowState.DRAFT_READY, WorkflowState.AWAITING_MEDICAL_REVIEW),
    (WorkflowState.AWAITING_MEDICAL_REVIEW, WorkflowState.MEDICALLY_APPROVED),
    (WorkflowState.MEDICALLY_APPROVED, WorkflowState.PRODUCTION_IN_PROGRESS),
    (WorkflowState.PRODUCTION_IN_PROGRESS, WorkflowState.AWAITING_VIDEO_REVIEW),
    (WorkflowState.AWAITING_VIDEO_REVIEW, WorkflowState.VIDEO_APPROVED),
    (WorkflowState.VIDEO_APPROVED, WorkflowState.PACKAGED),
    (WorkflowState.PACKAGED, WorkflowState.PUBLISHED_MANUAL),
    (WorkflowState.PRODUCTION_IN_PROGRESS, WorkflowState.MEDICALLY_APPROVED),
}


def test_main_graph_requires_artifacts_and_active_revision() -> None:
    project = ProjectManifestV2(slug="muoi-va-huyet-ap", state="draft_ready")
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset(),
    )

    with pytest.raises(TransitionError, match="missing required artifacts"):
        transition_v2(project, WorkflowState.AWAITING_MEDICAL_REVIEW, context)


def test_main_graph_has_only_the_documented_main_and_recovery_edges() -> None:
    assert set(MAIN_RULES) == MAIN_EDGES


def test_main_graph_rejects_mismatched_revision_and_invalid_input_hash() -> None:
    project = ProjectManifestV2(slug="muoi-va-huyet-ap")
    artifacts = frozenset({"topic/card.yaml"})

    with pytest.raises(TransitionError, match="active revision"):
        transition_v2(
            project,
            WorkflowState.TOPIC_SELECTED,
            TransitionContext("002", "0" * 64, artifacts),
        )
    with pytest.raises(TransitionError, match="current input hash"):
        transition_v2(
            project,
            WorkflowState.TOPIC_SELECTED,
            TransitionContext("001", "not-a-hash", artifacts),
        )


def test_main_graph_advances_with_the_rule_specific_validated_artifacts() -> None:
    project = ProjectManifestV2(slug="muoi-va-huyet-ap")
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset({"topic/card.yaml"}),
    )

    changed = transition_v2(project, WorkflowState.TOPIC_SELECTED, context)

    assert changed.state is WorkflowState.TOPIC_SELECTED
    assert changed.side_state is None


def test_main_graph_rejects_non_main_edge() -> None:
    project = ProjectManifestV2(slug="muoi-va-huyet-ap")
    context = TransitionContext("001", "0" * 64, frozenset({"topic/card.yaml"}))

    with pytest.raises(TransitionError, match="invalid v2 transition"):
        transition_v2(project, WorkflowState.DRAFT_READY, context)
