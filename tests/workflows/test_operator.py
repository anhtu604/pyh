from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.project_v2 import (
    ResumableSideState,
    TopicRejectedSideState,
    WorkflowState,
)
from healthvideo.storage.files import write_yaml_atomic
from healthvideo.workflows.operator import get_next_action, render_status


def _v2_project(
    root: Path,
    state: WorkflowState,
    *,
    reason_code: str = "test_pause",
) -> Path:
    project_dir = root / state.value
    (project_dir / "revisions" / "001").mkdir(parents=True)
    manifest: dict[str, object] = {
        "schema_version": "2.0",
        "slug": "muoi-va-huyet-ap",
        "state": state.value,
        "active_revision": "001",
        "artifact_hashes": {"fixture": "unchanged"},
    }
    if state is WorkflowState.TOPIC_REJECTED:
        side_state = TopicRejectedSideState(
            type=state,
            reason_code=reason_code,
            entered_at=datetime(2026, 9, 12, tzinfo=UTC),
        )
        manifest["side_state"] = side_state.model_dump(mode="json")
    elif state in {
        WorkflowState.AWAITING_BROWSER_LOGIN,
        WorkflowState.AWAITING_SECOND_MODEL_REVIEW,
        WorkflowState.NEEDS_MEDICAL_REVISION,
        WorkflowState.NEEDS_PRODUCTION_REVISION,
        WorkflowState.BLOCKED,
    }:
        side_state = ResumableSideState(
            type=state,
            resume_state=WorkflowState.DRAFT_READY,
            reason_code=reason_code,
            entered_at=datetime(2026, 9, 12, tzinfo=UTC),
        )
        manifest["side_state"] = side_state.model_dump(mode="json")
    write_yaml_atomic(project_dir / "project.yaml", manifest)
    return project_dir


@pytest.mark.parametrize(
    ("state", "kind"),
    [
        (WorkflowState.IDEA, "choose_topic"),
        (WorkflowState.TOPIC_SELECTED, "confirm_brief"),
        (WorkflowState.AUTHOR_BRIEF_READY, "research"),
        (WorkflowState.RESEARCH_IN_PROGRESS, "research"),
        (WorkflowState.EVIDENCE_READY, "draft"),
        (WorkflowState.DRAFT_READY, "prepare_medical_review"),
        (WorkflowState.AWAITING_MEDICAL_REVIEW, "await_medical_approval"),
        (WorkflowState.MEDICALLY_APPROVED, "produce"),
        (WorkflowState.PRODUCTION_IN_PROGRESS, "produce"),
        (WorkflowState.AWAITING_VIDEO_REVIEW, "await_video_approval"),
        (WorkflowState.VIDEO_APPROVED, "package"),
        (WorkflowState.PACKAGED, "complete"),
        (WorkflowState.PUBLISHED_MANUAL, "complete"),
    ],
)
def test_next_action_is_projection_of_v2_state(
    tmp_path: Path, state: WorkflowState, kind: str
) -> None:
    """A wrong state-to-action branch must not send an operator to the wrong step."""
    action = get_next_action(_v2_project(tmp_path, state))

    assert action.kind.value == kind


@pytest.mark.parametrize(
    ("state", "kind"),
    [
        (WorkflowState.NEEDS_MEDICAL_REVISION, "revise_medical"),
        (WorkflowState.NEEDS_PRODUCTION_REVISION, "revise_production"),
        (WorkflowState.BLOCKED, "resolve_blocker"),
        (WorkflowState.AWAITING_BROWSER_LOGIN, "await_browser_login"),
        (WorkflowState.AWAITING_SECOND_MODEL_REVIEW, "await_second_model_review"),
        (WorkflowState.TOPIC_REJECTED, "reopen_topic"),
    ],
)
def test_next_action_explains_each_v2_side_state(
    tmp_path: Path, state: WorkflowState, kind: str
) -> None:
    """A side-state mutation must remain visible rather than falling through a main path."""
    action = get_next_action(_v2_project(tmp_path, state, reason_code="needs_attention"))

    assert action.kind.value == kind
    assert "needs_attention" in action.message


def test_v1_project_is_directed_to_safe_migration(tmp_path: Path) -> None:
    """A legacy manifest must not be routed through a v2 workflow action."""
    project_dir = tmp_path / "legacy"
    project_dir.mkdir()
    write_yaml_atomic(
        project_dir / "project.yaml",
        {"schema_version": "1.0", "slug": "legacy", "state": "idea"},
    )

    action = get_next_action(project_dir)

    assert action.kind.value == "migrate_legacy"
    assert action.artifact == project_dir / "project.yaml"


def test_invalid_manifest_fails_closed_with_manifest_path(tmp_path: Path) -> None:
    """Invalid state data must not produce a possibly unsafe suggested action."""
    project_dir = tmp_path / "invalid"
    project_dir.mkdir()
    manifest_path = project_dir / "project.yaml"
    manifest_path.write_text(
        "schema_version: '2.0'\nslug: invalid\nstate: unknown\nactive_revision: '001'\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="project.yaml"):
        get_next_action(project_dir)


def test_render_status_is_stable_and_does_not_write_project_state(tmp_path: Path) -> None:
    """Status rendering must be a reproducible projection, never a workflow mutation."""
    project_dir = _v2_project(tmp_path, WorkflowState.AWAITING_MEDICAL_REVIEW)
    manifest_path = project_dir / "project.yaml"
    before = manifest_path.read_bytes()

    first = render_status(project_dir)
    second = render_status(project_dir)

    assert first == second
    assert "await_medical_approval" in first
    assert manifest_path.read_bytes() == before
    assert not (project_dir / "STATUS.md").exists()
