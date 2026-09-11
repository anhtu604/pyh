"""v2 gate approval/rejection records — reviewer accountability for one gate."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from healthvideo.domain.project_v2 import WorkflowState


class GateKind(StrEnum):
    MEDICAL = "medical"
    VIDEO = "video"


class GateApprovalRecord(BaseModel):
    """Audit trail of one gate approval, bound to the artifacts it covers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    kind: GateKind
    reviewer: str
    reviewed_at: datetime
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


class GateRejectionRecord(BaseModel):
    """Audit trail of one gate rejection: why, and where the workflow resumes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    kind: GateKind
    reviewer: str
    reviewed_at: datetime
    reason: str = Field(pattern=r"\S")
    resume_state: WorkflowState
    artifact_hashes: dict[str, str]

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
