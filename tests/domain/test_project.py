import pytest

from healthvideo.domain.project import ORDER, ProjectManifest, ProjectState, transition

EXPECTED_V1_ORDER = [
    "idea",
    "evidence_in_progress",
    "evidence_ready",
    "awaiting_medical_review",
    "script_approved",
    "producing",
    "rendered",
    "awaiting_video_review",
    "approved_to_publish",
    "published",
]


def test_v1_linear_order_and_transition_are_unchanged() -> None:
    assert [state.value for state in ORDER] == EXPECTED_V1_ORDER
    project = ProjectManifest(slug="muoi-va-huyet-ap")

    assert (
        transition(project, ProjectState.EVIDENCE_IN_PROGRESS).state
        is ProjectState.EVIDENCE_IN_PROGRESS
    )
    with pytest.raises(ValueError, match="Invalid transition"):
        transition(project, ProjectState.RENDERED)
