from datetime import UTC, datetime
from pathlib import Path

from healthvideo.domain.jev_decision import (
    ClaimCheckFlag,
    JevDecisionKind,
    SecondModelRecommendation,
    TopicPriorityBand,
)
from healthvideo.domain.topic import TopicCard, TopicScores
from healthvideo.jev.client import FakeJevTransport, JevClient
from healthvideo.jev.config import JevConfig
from healthvideo.storage.files import read_yaml
from healthvideo.workflows.jev_triage import (
    recommend_second_model_review,
    triage_claims_advisory,
    triage_topic_advisory,
)
from tests.helpers import create_v2_project_fixture


def test_triage_topic_advisory_preserves_card_and_scores() -> None:
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)
    scores = TopicScores(preventive_value=0.8, evidence_readiness=0.85)
    card = TopicCard(
        slug="topic-card-test",
        title="Tiêu đề test",
        question="Câu hỏi?",
        scores=scores,
        status="inbox",
        created_at=now,
    )
    transport = FakeJevTransport(
        default_response={
            "choice": "high",
            "confidence": 0.94,
            "flags": [],
            "reason": "Ưu tiên cao",
        }
    )
    client = JevClient(config=JevConfig(api_key="k"), transport=transport)

    record = triage_topic_advisory(card, client=client, now=now)

    assert record.decision_kind == JevDecisionKind.TOPIC_TRIAGE
    assert record.normalized_choice == TopicPriorityBand.HIGH.value
    # Guarantee immutability: card status and scores are unchanged
    assert card.status == "inbox"
    assert card.scores.preventive_value == 0.8


def test_triage_claims_advisory_reads_ledger_without_mutation(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path / "project")
    transport = FakeJevTransport(
        default_response={
            "choice": "citation_check",
            "confidence": 0.91,
            "flags": ["citation_check"],
            "reason": "Cần thêm trích dẫn",
        }
    )
    client = JevClient(config=JevConfig(api_key="k"), transport=transport)
    manifest_bytes_before = (project_dir / "project.yaml").read_bytes()
    ledger_bytes_before = (project_dir / "revisions/001/evidence/ledger.yaml").read_bytes()

    records = triage_claims_advisory(project_dir, client=client, write_artifact=True)

    assert len(records) > 0
    assert records[0].normalized_choice == ClaimCheckFlag.CITATION_CHECK.value
    # Manifest and ledger are completely unchanged
    assert (project_dir / "project.yaml").read_bytes() == manifest_bytes_before
    assert (project_dir / "revisions/001/evidence/ledger.yaml").read_bytes() == ledger_bytes_before
    # Advisory artifact written write-once
    advisory_path = project_dir / "revisions/001/evidence/jev-claim-advisory.yaml"
    assert advisory_path.is_file()
    data = read_yaml(advisory_path)
    assert "advisories" in data


def test_recommend_second_model_review_advisory_only(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path / "project")
    transport = FakeJevTransport(
        default_response={
            "choice": "consider_review",
            "confidence": 0.92,
            "flags": [],
            "reason": "Chủ đề rủi ro cao, đề xuất phản biện",
        }
    )
    client = JevClient(config=JevConfig(api_key="k"), transport=transport)
    state_before = (project_dir / "project.yaml").read_text(encoding="utf-8")

    record = recommend_second_model_review(project_dir, client=client, write_artifact=True)

    assert record.decision_kind == JevDecisionKind.SECOND_MODEL_ROUTING
    assert record.normalized_choice == SecondModelRecommendation.CONSIDER_REVIEW.value
    # State has NOT changed to awaiting_second_model_review
    state_after = (project_dir / "project.yaml").read_text(encoding="utf-8")
    assert state_before == state_after
    # No handoff XML was generated
    assert not (project_dir / "revisions/001/handoffs/second-model").exists()
    # Advisory file was created
    advisory_file = project_dir / "revisions/001/handoffs/jev-review-advisory.yaml"
    assert advisory_file.is_file()
