from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from healthvideo.domain.gate_review import (
    GateApprovalRecord,
    GateKind,
    GateRejectionRecord,
)
from healthvideo.domain.project_v2 import WorkflowState

REVIEWER = "BS Nguyễn Văn An"


def test_gate_approval_rejects_blank_reviewer_and_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        GateApprovalRecord(
            kind=GateKind.MEDICAL,
            reviewer="   ",
            reviewed_at=datetime.now(UTC),
            artifact_hashes={"evidence/ledger.yaml": "0" * 64},
        )
    with pytest.raises(ValidationError):
        GateApprovalRecord(
            kind=GateKind.MEDICAL,
            reviewer=REVIEWER,
            reviewed_at=datetime.now(UTC).replace(tzinfo=None),
            artifact_hashes={"evidence/ledger.yaml": "0" * 64},
        )


def test_gate_approval_requires_at_least_one_artifact_hash() -> None:
    with pytest.raises(ValidationError):
        GateApprovalRecord(
            kind=GateKind.MEDICAL,
            reviewer=REVIEWER,
            reviewed_at=datetime.now(UTC),
            artifact_hashes={},
        )


def test_gate_rejection_requires_non_blank_reason() -> None:
    with pytest.raises(ValidationError):
        GateRejectionRecord(
            kind=GateKind.MEDICAL,
            reviewer=REVIEWER,
            reviewed_at=datetime.now(UTC),
            reason="   ",
            resume_state=WorkflowState.DRAFT_READY,
            artifact_hashes={"evidence/ledger.yaml": "0" * 64},
        )


def test_gate_rejection_round_trips_resume_state() -> None:
    record = GateRejectionRecord(
        kind=GateKind.VIDEO,
        reviewer=REVIEWER,
        reviewed_at=datetime.now(UTC),
        reason="Màu sắc chưa đúng brand.",
        resume_state=WorkflowState.PRODUCTION_IN_PROGRESS,
        artifact_hashes={"renders/render-manifest.json": "1" * 64},
    )
    assert record.resume_state is WorkflowState.PRODUCTION_IN_PROGRESS
