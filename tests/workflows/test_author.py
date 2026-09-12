from datetime import UTC, datetime

from healthvideo.domain.author import AuthorBrief
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.topic import TopicCard
from healthvideo.storage.files import read_yaml
from healthvideo.workflows.author import save_author_brief
from healthvideo.workflows.create_project_v2 import create_project_v2
from healthvideo.workflows.topic import select_topic

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


def test_draft_brief_does_not_advance(tmp_path) -> None:
    """Saving a draft keeps the selected topic open for author confirmation."""
    project = _v2_topic_project(tmp_path)

    result = save_author_brief(
        project, AuthorBrief(title="Muối"), confirm=False, now=FROZEN_NOW
    )

    assert result.state is WorkflowState.TOPIC_SELECTED
    assert read_yaml(project / "revisions/001/author/brief.yaml")["title"] == "Muối"


def test_confirmed_brief_uses_existing_transition(tmp_path) -> None:
    """Confirming a brief advances the v2 state graph through its guarded edge."""
    project = _v2_topic_project(tmp_path)

    result = save_author_brief(
        project, AuthorBrief(title="Muối"), confirm=True, now=FROZEN_NOW
    )

    assert result.state is WorkflowState.AUTHOR_BRIEF_READY
    saved = ProjectManifestV2.model_validate(read_yaml(project / "project.yaml"))
    assert saved.state is WorkflowState.AUTHOR_BRIEF_READY
