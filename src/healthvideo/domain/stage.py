"""Immutable audit record of one pipeline stage run, bound to its input/output hashes."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SHA256_HEX_PATTERN = r"^[0-9a-f]{64}$"


class StageStatus(StrEnum):
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class StageManifest(BaseModel):
    """A single append-only record of one AI/tool stage run.

    A stage is only trustworthy once ``status`` is ``complete``: only then
    does it carry the ``output_hash`` and ``completed_at`` that bind the
    record to what the stage actually produced.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    stage: str = Field(pattern=r"\S")
    status: StageStatus
    input_hash: str = Field(pattern=_SHA256_HEX_PATTERN)
    output_hash: str | None = Field(default=None, pattern=_SHA256_HEX_PATTERN)
    tool_version: str = Field(pattern=r"\S")
    agent: str = Field(pattern=r"\S")
    model: str = Field(pattern=r"\S")
    started_at: datetime
    completed_at: datetime | None = None
    estimated_input_tokens: int = Field(ge=0)
    estimated_output_tokens: int = Field(ge=0)

    @field_validator("started_at", "completed_at")
    @classmethod
    def _require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("stage timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _validate_completion_invariants(self) -> StageManifest:
        if self.status is StageStatus.COMPLETE:
            if self.output_hash is None or self.completed_at is None:
                raise ValueError(
                    "a complete stage requires output_hash and completed_at"
                )
        elif self.output_hash is not None:
            raise ValueError("output_hash is only recorded for a complete stage")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        return self
