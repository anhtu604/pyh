from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from healthvideo.domain.project_v2 import (
    ProjectManifestV2,
    TopicRejectedSideState,
    WorkflowState,
)


def test_project_manifest_v2_defaults_to_the_first_active_revision() -> None:
    project = ProjectManifestV2(slug="muoi-va-huyet-ap")

    assert project.schema_version == "2.0"
    assert project.state is WorkflowState.IDEA
    assert project.active_revision == "001"
    with pytest.raises(ValidationError):
        ProjectManifestV2(slug="muoi-va-huyet-ap", active_revision="2")


def test_project_manifest_v2_requires_side_state_to_match_side_workflow_state() -> None:
    entered_at = datetime(2026, 9, 10, tzinfo=UTC)
    side_state = TopicRejectedSideState(
        type=WorkflowState.TOPIC_REJECTED,
        reason_code="insufficient_evidence",
        entered_at=entered_at,
    )

    project = ProjectManifestV2(
        slug="muoi-va-huyet-ap",
        state=WorkflowState.TOPIC_REJECTED,
        side_state=side_state,
    )

    assert project.side_state == side_state
    with pytest.raises(ValidationError, match="side_state"):
        ProjectManifestV2(slug="muoi-va-huyet-ap", side_state=side_state)


def test_project_manifest_v2_requires_a_side_state_for_side_workflow_state() -> None:
    with pytest.raises(ValidationError, match="side_state"):
        ProjectManifestV2(
            slug="muoi-va-huyet-ap", state=WorkflowState.BLOCKED
        )
