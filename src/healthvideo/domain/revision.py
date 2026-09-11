"""Immutable provenance record of one workflow revision."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_REVISION_ID_PATTERN = r"^[0-9]{3}$"


class RevisionRecord(BaseModel):
    """Where a revision came from and why it was created.

    Written once as ``workflow.yaml`` at the root of a newly promoted
    revision. The root revision ``001`` of a project has no ``RevisionRecord``:
    it is created directly (by ``project new`` or ``project migrate``), not by
    the revision service this record belongs to.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    revision: str = Field(pattern=_REVISION_ID_PATTERN)
    parent_revision: str = Field(pattern=_REVISION_ID_PATTERN)
    reason: str = Field(pattern=r"\S")
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value
