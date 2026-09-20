from __future__ import annotations

import pytest
from pydantic import ValidationError

from healthvideo.domain.evidence import CandidateSource
from healthvideo.domain.orientation import (
    CompletedOrientation,
    EditorialOption,
    OrientationScope,
    ProviderOutcome,
    SourceBackedContext,
)


def valid_option(source_id: str) -> EditorialOption:
    return EditorialOption(
        id="option-a",
        title="Một góc nhìn trung tính",
        framing="Đặt câu hỏi để bác sĩ tự xác định thông điệp.",
        context_source_ids=[source_id],
        questions_for_doctor=["Bác sĩ muốn công chúng hiểu điều gì?"],
    )


def valid_record(**changes: object) -> CompletedOrientation:
    values: dict[str, object] = {
        "run_id": "run-001",
        "topic_input_hash": "0" * 64,
        "included_source_ids": ["pubmed-9"],
        "context_points": [
            SourceBackedContext(
                text="Nguồn chỉ cung cấp bối cảnh ban đầu.",
                limitation="Không đủ để suy ra khuyến nghị cho từng cá nhân.",
                source_ids=["pubmed-9"],
            )
        ],
        "options": [
            valid_option("pubmed-9"),
            valid_option("pubmed-9").model_copy(update={"id": "option-b"}),
        ],
    }
    values.update(changes)
    return CompletedOrientation(**values)


def candidate(source_id: str = "pubmed-9") -> CandidateSource:
    return CandidateSource(
        source_id=source_id,
        database="pubmed",
        title="Synthetic candidate title",
    )


def test_completed_orientation_rejects_unknown_candidate() -> None:
    record = valid_record()

    with pytest.raises(ValueError, match="included candidate"):
        record.validate_candidate_binding([])


def test_completed_orientation_binds_options_and_context_to_included_candidates() -> None:
    record = valid_record()

    record.validate_candidate_binding([candidate()])

    with pytest.raises(ValueError, match="context source"):
        valid_record(
            options=[
                valid_option("missing"),
                valid_option("pubmed-9").model_copy(update={"id": "option-b"}),
            ]
        )


def test_completed_orientation_requires_two_or_three_distinct_editorial_options() -> None:
    with pytest.raises(ValidationError, match="two or three"):
        valid_record(options=[valid_option("pubmed-9")])

    with pytest.raises(ValidationError, match="duplicate editorial option"):
        valid_record(options=[valid_option("pubmed-9"), valid_option("pubmed-9")])


def test_completed_orientation_rejects_duplicate_or_unresolved_included_source_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate included source"):
        valid_record(included_source_ids=["pubmed-9", "pubmed-9"])

    record = valid_record(included_source_ids=["pubmed-9", "pubmed-10"])
    with pytest.raises(ValueError, match="duplicate candidate"):
        record.validate_candidate_binding([candidate("pubmed-9"), candidate("pubmed-9")])


def test_orientation_rejects_decision_and_approval_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        valid_record(doctor_decision="approve")

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        valid_option("pubmed-9").model_validate(
            {
                **valid_option("pubmed-9").model_dump(),
                "approval": "approved",
            }
        )


def test_scope_and_provider_outcome_are_frozen_and_capture_safe_status() -> None:
    scope = OrientationScope(
        topic_question="Chủ đề này cần được hiểu thế nào?",
        intended_audience="Người trưởng thành",
        exclusions=["Không tư vấn cá nhân hóa"],
    )
    outcome = ProviderOutcome(
        provider="pubmed",
        query_id="run-001",
        status="failed",
        failure_class="OSError",
        error_summary="Connection failed",
    )

    with pytest.raises(ValidationError, match="Instance is frozen"):
        scope.topic_question = "khác"  # type: ignore[misc]
    assert outcome.result_count is None


def test_source_backed_context_requires_a_limitation_and_included_source() -> None:
    with pytest.raises(ValidationError, match="limitation"):
        SourceBackedContext(text="Bối cảnh", limitation="", source_ids=["pubmed-9"])

    with pytest.raises(ValidationError, match="source-backed context"):
        valid_record(
            context_points=[
                SourceBackedContext(
                    text="Bối cảnh",
                    limitation="Giới hạn",
                    source_ids=["missing"],
                )
            ]
        )
