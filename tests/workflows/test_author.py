from datetime import UTC, datetime

import pytest

from healthvideo.domain.author import AuthorBrief
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.domain.topic import TopicCard
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.author import save_author_brief
from healthvideo.workflows.create_project_v2 import create_project_v2
from healthvideo.workflows.orientation import begin_orientation
from healthvideo.workflows.topic import select_topic
from tests.helpers import ORIENTATION_SCOPE, complete_orientation_fixture

FROZEN_NOW = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)


def _v2_topic_project(tmp_path):
    project = create_project_v2(tmp_path, "muoi", "Muối", now=FROZEN_NOW)
    select_topic(
        project,
        TopicCard(
            slug="muoi",
            title="Muối",
            question="Muối ảnh hưởng huyết áp như thế nào?",
        ),
        now=FROZEN_NOW,
    )
    return project


def _force_state(project_dir, state: WorkflowState) -> None:
    """Reach a state without its workflow, to prove the guard below is the one acting."""
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    advanced = transition_v2(
        manifest,
        state,
        TransitionContext(
            active_revision="001",
            current_input_hash="0" * 64,
            validated_artifacts=frozenset({"orientation/completed/<run_id>.yaml"}),
        ),
    )
    write_yaml_atomic(project_dir / "project.yaml", advanced.model_dump(mode="json"))


def _oriented_project(tmp_path):
    project = _v2_topic_project(tmp_path)
    complete_orientation_fixture(project, now=FROZEN_NOW)
    return project


def test_draft_brief_does_not_advance(tmp_path) -> None:
    """Saving a draft keeps the selected topic open for author confirmation."""
    project = _v2_topic_project(tmp_path)

    result = save_author_brief(
        project, AuthorBrief(title="Muối"), confirm=False, now=FROZEN_NOW
    )

    assert result.state is WorkflowState.TOPIC_SELECTED
    assert read_yaml(project / "revisions/001/author/brief.yaml")["title"] == "Muối"


def test_confirming_brief_from_topic_selected_fails_closed(tmp_path) -> None:
    """Orientation must complete before an author brief can be confirmed."""
    project = _v2_topic_project(tmp_path)

    with pytest.raises(ValueError, match="awaiting_editorial_direction"):
        save_author_brief(
            project, AuthorBrief(title="Muối"), confirm=True, now=FROZEN_NOW
        )

    saved = ProjectManifestV2.model_validate(read_yaml(project / "project.yaml"))
    assert saved.state is WorkflowState.TOPIC_SELECTED


def test_confirming_without_an_authoritative_orientation_is_rejected(tmp_path) -> None:
    """A brief may not bind context that no completed orientation record supports."""
    project = _v2_topic_project(tmp_path)
    begin_orientation(project, ORIENTATION_SCOPE)
    _force_state(project, WorkflowState.AWAITING_EDITORIAL_DIRECTION)

    with pytest.raises(ValueError, match="no completed orientation"):
        save_author_brief(
            project, AuthorBrief(title="Muối"), confirm=True, now=FROZEN_NOW
        )

    saved = ProjectManifestV2.model_validate(read_yaml(project / "project.yaml"))
    assert saved.state is WorkflowState.AWAITING_EDITORIAL_DIRECTION


def test_confirming_with_a_validated_orientation_advances(tmp_path) -> None:
    """The doctor's confirmation is the only route into the full evidence workflow."""
    project = _oriented_project(tmp_path)

    result = save_author_brief(
        project, AuthorBrief(title="Muối"), confirm=True, now=FROZEN_NOW
    )

    assert result.state is WorkflowState.AUTHOR_BRIEF_READY
