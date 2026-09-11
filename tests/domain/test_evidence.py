from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from healthvideo.domain.evidence import (
    CandidateSource,
    EvidenceClaim,
    EvidenceQuestion,
    SearchLogRecord,
    SourceRecord,
    SourceSelection,
)
from healthvideo.storage.files import read_yaml


def test_extended_evidence_claim_defaults_and_validation() -> None:
    claim = EvidenceClaim(
        id="C01",
        text_public="Giảm muối giúp hạ huyết áp",
        text_technical="Reduced sodium lowers blood pressure",
        type="evidence",
        sources=["R01"],
        certainty="moderate",
        population="Người trưởng thành",
        applicability="Phù hợp với thói quen ăn uống của người Việt Nam",
        evidence_direction="supporting",
        doctor_notes="Cần lưu ý không khuyến cáo kiêng muối tuyệt đối",
    )
    assert claim.certainty == "moderate"
    assert claim.population == "Người trưởng thành"
    assert claim.applicability.startswith("Phù hợp")
    assert claim.evidence_direction == "supporting"

    # Invalid certainty
    with pytest.raises(ValidationError):
        EvidenceClaim(
            id="C02",
            text_public="...",
            text_technical="...",
            type="evidence",
            certainty="invalid_level",
        )


def test_extended_source_record_defaults_and_validation() -> None:
    source = SourceRecord(
        id="R01",
        title="Sodium reduction and blood pressure",
        authors=["Author A", "Author B"],
        year=2023,
        journal="The Lancet",
        doi="10.1016/S0140-6736(23)00000-0",
        pmid="37000000",
        pmcid="PMC10000000",
        retraction_status="clean",
        key_findings="Hạ natri giảm trung bình 5 mmHg huyết áp tâm thu",
    )
    assert source.journal == "The Lancet"
    assert source.retraction_status == "clean"
    assert source.pmcid == "PMC10000000"


def test_evidence_question_pico_model() -> None:
    question = EvidenceQuestion(
        patient_population="Người trưởng thành có nguy cơ hoặc đang bị tăng huyết áp",
        intervention="Chế độ ăn giảm natri (<2000mg/ngày)",
        comparison="Chế độ ăn bình thường",
        outcome="Mức giảm huyết áp tâm thu và tâm trương",
        search_keywords=["sodium reduction", "blood pressure", "hypertension", "diet"],
    )
    assert question.schema_version == "2.0"
    assert len(question.search_keywords) == 4
    assert question.language == "vi"


def test_search_log_and_candidate_models() -> None:
    now = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
    log = SearchLogRecord(
        database="pubmed",
        query="sodium reduction AND hypertension",
        searched_at=now,
        total_results=150,
        retrieved_count=10,
    )
    assert log.total_results == 150

    candidate = CandidateSource(
        source_id="pubmed-37000000",
        database="pubmed",
        title="Effect of dietary sodium on blood pressure",
        authors=["Smith J"],
        year=2022,
        pmid="37000000",
        doi="10.1000/182",
        venue="BMJ",
    )
    assert candidate.source_id == "pubmed-37000000"

    selection = SourceSelection(
        source_id="pubmed-37000000",
        decision="included",
        reason="Thử nghiệm ngẫu nhiên có đối chứng, cỡ mẫu lớn, phù hợp tiêu chí",
    )
    assert selection.decision == "included"


def test_existing_golden_ledgers_validate_backward_compatibility() -> None:
    # v1 golden ledger
    v1_path = Path("tests/fixtures/golden-project/evidence/ledger.yaml")
    assert v1_path.is_file()
    v1_data = read_yaml(v1_path)
    for record in v1_data["records"]:
        parsed_record = SourceRecord.model_validate(record)
        assert parsed_record.id.startswith("R")
        assert parsed_record.retraction_status == "unverified"
    for claim in v1_data["claims"]:
        parsed_claim = EvidenceClaim.model_validate(claim)
        assert parsed_claim.id.startswith("C")
        assert parsed_claim.certainty == "unrated"

    # v2 golden ledger
    v2_path = Path("tests/fixtures/golden-project-v2/revisions/001/evidence/ledger.yaml")
    assert v2_path.is_file()
    v2_data = read_yaml(v2_path)
    for record in v2_data["records"]:
        parsed_record = SourceRecord.model_validate(record)
        assert parsed_record.id.startswith("R")
    for claim in v2_data["claims"]:
        parsed_claim = EvidenceClaim.model_validate(claim)
        assert parsed_claim.id.startswith("C")
