from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewKind(StrEnum):
    MEDICAL = "medical"
    VIDEO = "video"


class ReviewRecord(BaseModel):
    """Audit trail of one doctor approval, bound to the artifacts it covers."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    id: UUID = Field(default_factory=uuid4)
    kind: ReviewKind
    decision: Literal["approved"] = "approved"
    reviewer: str
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    artifact_hashes: dict[str, str]
    note: str = ""

    @field_validator("reviewer")
    @classmethod
    def _require_named_reviewer(cls, value: str) -> str:
        reviewer = value.strip()
        if not reviewer:
            raise ValueError("reviewer must name the approving doctor")
        return reviewer

    @field_validator("reviewed_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        return value

    @field_validator("artifact_hashes")
    @classmethod
    def _require_artifact_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("artifact_hashes must bind the reviewed artifacts")
        return value
