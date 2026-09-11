from datetime import UTC, datetime
from pathlib import Path

from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.topic import TopicCard, TopicScores
from healthvideo.storage.files import read_yaml
from healthvideo.workflows.topic import (
    create_topic,
    list_topics,
    reject_topic,
    select_topic,
)


def test_create_and_list_topics_sorted_by_triage_rank(tmp_path: Path) -> None:
    inbox_dir = tmp_path / "topics"
    now = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)

    card1 = create_topic(
        inbox_dir=inbox_dir,
        title="Ăn mặn và huyết áp",
        question="Ăn mặn có làm tăng huyết áp?",
        slug="an-man-va-huyet-ap",
        target_audience="Người lớn",
        scores=TopicScores(preventive_value=0.9, evidence_readiness=0.8),
        now=now,
    )
    assert card1.slug == "an-man-va-huyet-ap"
    assert (inbox_dir / "an-man-va-huyet-ap.yaml").is_file()

    card2 = create_topic(
        inbox_dir=inbox_dir,
        title="Uống nước chanh giảm cân",
        question="Nước chanh có giảm mỡ bụng?",
        slug="nuoc-chanh-giam-can",
        target_audience="Phụ nữ",
        scores=TopicScores(preventive_value=0.2, evidence_readiness=0.2),
        now=now,
    )
    assert card2.slug == "nuoc-chanh-giam-can"

    topics = list_topics(inbox_dir)
    assert len(topics) == 2
    # card1 has higher rank than card2
    assert topics[0].slug == "an-man-va-huyet-ap"
    assert topics[1].slug == "nuoc-chanh-giam-can"


def test_reject_topic_sets_status_and_reason(tmp_path: Path) -> None:
    inbox_dir = tmp_path / "topics"
    now = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)

    card = create_topic(
        inbox_dir=inbox_dir,
        title="Uống nước chanh giảm cân",
        question="Nước chanh có giảm mỡ bụng?",
        slug="nuoc-chanh-giam-can",
        now=now,
    )
    assert card.status == "inbox"

    card_path = inbox_dir / "nuoc-chanh-giam-can.yaml"
    rejected = reject_topic(card_path, reason="Chủ đề thiếu cơ sở y học thực chứng", now=now)
    assert rejected.status == "rejected"
    assert rejected.rejection_reason == "Chủ đề thiếu cơ sở y học thực chứng"

    # Verify listing with filter
    active_inbox = list_topics(inbox_dir, status="inbox")
    assert len(active_inbox) == 0

    rejected_list = list_topics(inbox_dir, status="rejected")
    assert len(rejected_list) == 1
    assert rejected_list[0].slug == "nuoc-chanh-giam-can"


def test_select_topic_writes_card_and_advances_project_state(tmp_path: Path) -> None:
    project_dir = tmp_path / "project-v2"
    project_dir.mkdir(parents=True)
    (project_dir / "revisions" / "001" / "topic").mkdir(parents=True)

    # Initial manifest at IDEA state
    initial_manifest = ProjectManifestV2(
        schema_version="2.0",
        slug="an-man-va-huyet-ap",
        state=WorkflowState.IDEA,
        active_revision="001",
    )
    from healthvideo.storage.files import write_yaml_atomic
    write_yaml_atomic(project_dir / "project.yaml", initial_manifest.model_dump(mode="json"))

    card = TopicCard(
        slug="an-man-va-huyet-ap",
        title="Ăn mặn và huyết áp",
        question="Ăn mặn có làm tăng huyết áp không?",
        target_audience="Người lớn tuổi",
    )

    now = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
    updated_manifest = select_topic(project_dir, card, now=now)

    assert updated_manifest.state == WorkflowState.TOPIC_SELECTED
    saved_card_path = project_dir / "revisions" / "001" / "topic" / "card.yaml"
    assert saved_card_path.is_file()
    saved_card = read_yaml(saved_card_path)
    assert saved_card["slug"] == "an-man-va-huyet-ap"
    assert saved_card["status"] == "selected"
