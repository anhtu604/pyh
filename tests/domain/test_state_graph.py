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


@pytest.mark.parametrize(
    ("run_published", "staging_verified_unusable", "reason_code", "message"),
    [
        (None, True, "staging_unusable", "run must be unpublished"),
        (True, True, "staging_unusable", "run must be unpublished"),
        (False, None, "staging_unusable", "staging must be verified unusable"),
        (False, False, "staging_unusable", "staging must be verified unusable"),
        (False, True, None, "reason code"),
        (False, True, "", "reason code"),
    ],
)
def test_recovery_requires_verified_unpublished_unusable_run(
    run_published: bool | None,
    staging_verified_unusable: bool | None,
    reason_code: str | None,
    message: str,
) -> None:
    project = ProjectManifestV2(
        slug="muoi-va-huyet-ap", state=WorkflowState.PRODUCTION_IN_PROGRESS
    )
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset({"reviews/medical-approval.yaml"}),
        reason_code=reason_code,
        run_published=run_published,
        staging_verified_unusable=staging_verified_unusable,
    )

    with pytest.raises(TransitionError, match=message):
        transition_v2(project, WorkflowState.MEDICALLY_APPROVED, context)


def test_recovery_advances_only_after_verified_unpublished_unusable_run() -> None:
    project = ProjectManifestV2(
        slug="muoi-va-huyet-ap", state=WorkflowState.PRODUCTION_IN_PROGRESS
    )
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset({"reviews/medical-approval.yaml"}),
        reason_code="staging_unusable",
        run_published=False,
        staging_verified_unusable=True,
    )

    assert transition_v2(project, WorkflowState.MEDICALLY_APPROVED, context).state is (
        WorkflowState.MEDICALLY_APPROVED
    )


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"new_revision_from": "000"}, "revision service"),
        ({"run_published": False}, "reserved for recovery"),
        ({"staging_verified_unusable": True}, "reserved for recovery"),
    ],
)
def test_ordinary_edge_rejects_revision_and_recovery_only_context(
    extra: dict[str, bool | str], message: str
) -> None:
    project = ProjectManifestV2(slug="muoi-va-huyet-ap")
    valid = {
        "active_revision": "001",
        "current_input_hash": "0" * 64,
        "validated_artifacts": frozenset({"topic/card.yaml"}),
    }

    with pytest.raises(TransitionError, match=message):
        transition_v2(
            project,
            WorkflowState.TOPIC_SELECTED,
            TransitionContext(**valid, **extra),
        )
