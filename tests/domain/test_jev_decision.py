from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from healthvideo.domain.jev_decision import (
    ClaimCheckFlag,
    ClaimTriageInput,
    JevAdvisoryRecord,
    JevDecisionKind,
    SecondModelRecommendation,
    SecondModelRoutingInput,
    TopicPriorityBand,
    TopicRiskFlag,
    TopicTriageInput,
)


def test_topic_triage_input_validation() -> None:
    inp = TopicTriageInput(
        slug="sleep-hygiene",
        title="Vệ sinh giấc ngủ",
        question="Làm sao ngủ ngon?",
        target_audience="Người lớn tuổi",
        preventive_value=0.8,
        evidence_readiness=0.9,
        clarity=0.7,
        harm_risk=0.1,
        production_cost=0.3,
    )
    assert inp.slug == "sleep-hygiene"
    with pytest.raises(ValidationError):
        inp.slug = "mutated"  # frozen check


def test_claim_triage_input_validation() -> None:
    inp = ClaimTriageInput(
        claim_id="CLM-001",
        text_public="Uống đủ nước",
        text_technical="Duy trì thể tích dịch cơ thể",
        claim_type="evidence",
        certainty="moderate",
        source_count=2,
        source_types=["systematic_review", "rct"],
    )
    assert inp.claim_id == "CLM-001"
    assert inp.source_count == 2


def test_second_model_routing_input_validation() -> None:
    inp = SecondModelRoutingInput(
        project_slug="p1",
        revision="001",
        source_state="evidence_ready",
        claim_count=3,
        unrated_certainty_count=1,
        low_certainty_count=0,
        has_doctor_notes=True,
    )
    assert inp.project_slug == "p1"
    assert inp.revision == "001"


def test_jev_advisory_record_valid_model() -> None:
    now = datetime.now(UTC)
    record = JevAdvisoryRecord(
        decision_id="20260921T120000Z-deadbeef",
        decision_kind=JevDecisionKind.TOPIC_TRIAGE,
        normalized_choice=TopicPriorityBand.HIGH.value,
        confidence=0.95,
        model_identifier="jev-v1",
        input_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        created_at=now,
        reason="Độ sẵn sàng bằng chứng cao và rủi ro thấp",
        flags=[TopicRiskFlag.NOVEL_UNVERIFIED_CLAIM.value],
    )
    assert record.decision_kind == JevDecisionKind.TOPIC_TRIAGE
    assert record.confidence == 0.95
    assert record.is_high_confidence is True


def test_jev_advisory_record_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        JevAdvisoryRecord(
            decision_id="20260921T120000Z-deadbeef",
            decision_kind=JevDecisionKind.CLAIM_TRIAGE,
            normalized_choice=ClaimCheckFlag.CITATION_CHECK.value,
            confidence=0.85,
            model_identifier="jev-v1",
            input_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            created_at=datetime(2026, 9, 21, 12, 0, 0),  # noqa: DTZ001 - intentionally naive for test
            reason="Thiếu citation",
        )


def test_jev_advisory_record_forbids_sensitive_metadata_keys() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="sensitive or forbidden key"):
        JevAdvisoryRecord(
            decision_id="20260921T120000Z-deadbeef",
            decision_kind=JevDecisionKind.SECOND_MODEL_ROUTING,
            normalized_choice=SecondModelRecommendation.NOT_RECOMMENDED.value,
            confidence=0.92,
            model_identifier="jev-v1",
            input_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            created_at=now,
            reason="Độ rủi ro thấp",
            metadata={"raw_response": "forbidden-dump", "api_token": "secret"},
        )
