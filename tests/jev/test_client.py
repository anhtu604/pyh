from datetime import UTC, datetime
from typing import Any

from healthvideo.domain.jev_decision import (
    ClaimCheckFlag,
    ClaimTriageInput,
    JevDecisionKind,
    SecondModelRecommendation,
    SecondModelRoutingInput,
    TopicPriorityBand,
    TopicTriageInput,
)
from healthvideo.jev.client import FakeJevTransport, JevClient
from healthvideo.jev.config import JevConfig


def test_client_success_topic_triage() -> None:
    config = JevConfig(api_key="valid-key", model="jev-v1", confidence_threshold=0.90)
    fake_transport = FakeJevTransport(
        default_response={
            "choice": "high",
            "confidence": 0.96,
            "flags": ["novel_unverified_claim"],
            "reason": "Chủ đề có tính sẵn sàng bằng chứng và phòng ngừa cao",
        }
    )
    client = JevClient(config=config, transport=fake_transport)
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)

    inp = TopicTriageInput(
        slug="topic-a",
        title="Title A",
        question="Q?",
        target_audience="Adults",
        preventive_value=0.9,
        evidence_readiness=0.8,
        clarity=0.8,
        harm_risk=0.1,
        production_cost=0.2,
    )

    record = client.evaluate_topic(inp, now=now)

    assert record.decision_kind == JevDecisionKind.TOPIC_TRIAGE
    assert record.normalized_choice == TopicPriorityBand.HIGH.value
    assert record.confidence == 0.96
    assert record.flags == ["novel_unverified_claim"]
    assert record.created_at == now
    assert len(fake_transport.calls) == 1
    assert fake_transport.calls[0]["decision_type"] == "topic_triage"


def test_client_fail_closed_missing_key() -> None:
    config = JevConfig(api_key=None)
    fake_transport = FakeJevTransport()
    client = JevClient(config=config, transport=fake_transport)
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)

    inp = TopicTriageInput(
        slug="topic-a",
        title="Title A",
        question="Q?",
        target_audience="Adults",
        preventive_value=0.5,
        evidence_readiness=0.5,
        clarity=0.5,
        harm_risk=0.5,
        production_cost=0.5,
    )

    record = client.evaluate_topic(inp, now=now)

    assert record.normalized_choice == TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value
    assert record.confidence == 0.0
    assert "chưa được cấu hình" in record.reason.lower() or "not configured" in record.reason.lower()
    assert len(fake_transport.calls) == 0  # Transport never called


def test_client_fail_closed_transport_error() -> None:
    config = JevConfig(api_key="valid-key")

    class FailingTransport:
        def decide(self, *, decision_type: str, input_payload: dict[str, Any], model: str) -> dict[str, Any]:
            raise ConnectionError("TypeSafe API endpoint unreachable")

    client = JevClient(config=config, transport=FailingTransport())  # type: ignore[arg-type]
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)

    inp = ClaimTriageInput(
        claim_id="CLM-001",
        text_public="Uống nước ấm trị bách bệnh",
        text_technical="Nước ấm chữa mọi bệnh",
        claim_type="evidence",
        certainty="unrated",
        source_count=0,
        source_types=[],
    )

    record = client.evaluate_claim(inp, now=now)

    assert record.normalized_choice == ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value
    assert record.confidence == 0.0
    assert "lỗi transport" in record.reason.lower() or "transport error" in record.reason.lower()


def test_client_fail_closed_low_confidence() -> None:
    config = JevConfig(api_key="valid-key", confidence_threshold=0.90)
    fake_transport = FakeJevTransport(
        default_response={
            "choice": "consider_review",
            "confidence": 0.72,  # below 0.90
            "flags": [],
            "reason": "Có thể cần phản biện",
        }
    )
    client = JevClient(config=config, transport=fake_transport)
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)

    inp = SecondModelRoutingInput(
        project_slug="proj-1",
        revision="001",
        source_state="evidence_ready",
        claim_count=3,
        unrated_certainty_count=1,
        low_certainty_count=1,
        has_doctor_notes=True,
    )

    record = client.evaluate_second_model(inp, now=now)

    # Choice forced to manual_review_required because confidence < 0.90
    assert record.normalized_choice == SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value
    assert record.confidence == 0.72
    assert "ngưỡng tin cậy" in record.reason.lower() or "confidence below threshold" in record.reason.lower()
