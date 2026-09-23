import sys
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from typing import Any, Self

import pytest

from healthvideo.domain.jev_decision import (
    ClaimCheckFlag,
    ClaimTriageInput,
    JevDecisionKind,
    SecondModelRecommendation,
    SecondModelRoutingInput,
    TopicPriorityBand,
    TopicTriageInput,
)
from healthvideo.jev.client import FakeJevTransport, JevClient, TypeSafeSdkTransport
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


def test_official_sdk_transport_uses_system_one(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    sdk = ModuleType("typesafe_sdk")

    class Choice:
        def __init__(self, *, instructions: str, criteria: dict[str, str | None]) -> None:
            self.instructions = instructions
            self.criteria = criteria

    class TypeSafeClient:
        def __init__(self, **kwargs: Any) -> None:
            calls.append({"client": kwargs})

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def system_one(self, **kwargs: Any) -> SimpleNamespace:
            calls.append({"system_one": kwargs})
            return SimpleNamespace(
                model="jev-latest",
                choices={"decision": SimpleNamespace(choice="high", confidence=0.96)},
            )

    sdk.Choice = Choice  # type: ignore[attr-defined]
    sdk.TypeSafeClient = TypeSafeClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)
    result = TypeSafeSdkTransport("test-key").decide(
        decision_type="topic_triage", input_payload={"title": "Synthetic topic"}, model="jev-latest"
    )

    assert result["choice"] == "high"
    assert result["confidence"] == 0.96
    request = calls[1]["system_one"]
    assert request["state"] == {"title": "Synthetic topic"}
    assert request["model"] == "jev-latest"
    assert set(request["questions"]["decision"].criteria) == {
        "high", "standard", "low", "manual_review_required"
    }


def test_provider_exception_does_not_leak_secret() -> None:
    secret = "synthetic-secret-do-not-print"

    class FailingTransport:
        def decide(self, **_kwargs: Any) -> dict[str, Any]:
            raise RuntimeError(f"provider rejected {secret}")

    client = JevClient(JevConfig(api_key=secret), FailingTransport())  # type: ignore[arg-type]
    record = client.evaluate_topic(TopicTriageInput(slug="safe", title="Synthetic"))
    assert record.normalized_choice == "manual_review_required"
    assert secret not in record.model_dump_json()


def test_oversized_input_skips_provider() -> None:
    transport = FakeJevTransport()
    client = JevClient(JevConfig(api_key="test-key", max_input_bytes=100), transport)
    record = client.evaluate_topic(TopicTriageInput(slug="large", title="x" * 200))
    assert record.normalized_choice == "manual_review_required"
    assert transport.calls == []


@pytest.mark.parametrize(
    ("evaluate", "input_data", "choice"),
    [
        ("evaluate_topic", TopicTriageInput(slug="safe", title="Synthetic"), "high"),
        (
            "evaluate_claim",
            ClaimTriageInput(
                claim_id="CLM-001", text_public="Synthetic", text_technical="Synthetic",
                claim_type="evidence", certainty="unrated", source_count=0,
            ),
            "citation_check",
        ),
        (
            "evaluate_second_model",
            SecondModelRoutingInput(
                project_slug="safe", revision="001", source_state="evidence_ready",
                claim_count=1, unrated_certainty_count=1, low_certainty_count=0,
            ),
            "consider_review",
        ),
    ],
)
def test_provider_text_is_not_persisted(evaluate: str, input_data: Any, choice: str) -> None:
    secret = "synthetic-secret-do-not-persist"
    transport = FakeJevTransport(
        {"choice": choice, "confidence": 0.99, "reason": secret, "flags": [secret]}
    )
    client = JevClient(JevConfig(api_key="test-key"), transport)
    record = getattr(client, evaluate)(input_data)
    assert record.normalized_choice == choice
    assert secret not in record.model_dump_json()
