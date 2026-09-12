"""Immutable contracts for a bounded, advisory second-model review."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from healthvideo.domain.project_v2 import WorkflowState

_HASH = r"^[0-9a-f]{64}$"
_REQUEST_ID = r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{12}$"
_REQUIRED_ARTIFACTS = frozenset({"author/brief.yaml", "evidence/ledger.yaml"})
_OPTIONAL_ARTIFACTS = frozenset({"script/script.yaml", "storyboard/storyboard.yaml"})


class AgentReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Literal["info", "warning", "blocking"]
    artifact: str = Field(min_length=1, pattern=r"\S")
    problem: str = Field(min_length=1, pattern=r"\S")
    suggested_patch: str = Field(min_length=1, pattern=r"\S")


class AgentReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    request_id: str = Field(pattern=_REQUEST_ID)
    project_slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    revision: str = Field(pattern=r"^[0-9]{3}$")
    reason_code: str = Field(pattern=r"\S")
    created_at: datetime
    source_state: Literal[WorkflowState.EVIDENCE_READY, WorkflowState.DRAFT_READY]
    artifact_hashes: dict[str, str]
    packet_sha256: str = Field(pattern=_HASH)

    @field_validator("created_at")
    @classmethod
    def aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @field_validator("artifact_hashes")
    @classmethod
    def valid_artifact_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        if not _REQUIRED_ARTIFACTS <= value.keys() or not value.keys() <= (
            _REQUIRED_ARTIFACTS | _OPTIONAL_ARTIFACTS
        ):
            raise ValueError(
                "artifact_hashes contain a missing or undeclared source path"
            )
        if any(
            len(h) != 64 or any(c not in "0123456789abcdef" for c in h)
            for h in value.values()
        ):
            raise ValueError("artifact_hashes must contain SHA-256 hashes")
        return value


class AgentReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    request_id: str = Field(pattern=_REQUEST_ID)
    revision: str = Field(pattern=r"^[0-9]{3}$")
    request_hash: str = Field(pattern=_HASH)
    reviewer: str = Field(pattern=r"\S")
    model: str = Field(pattern=r"\S")
    reviewed_at: datetime
    issues: list[AgentReviewIssue] = Field(default_factory=list)
    summary: str = Field(pattern=r"\S")

    @field_validator("reviewed_at")
    @classmethod
    def aware_reviewed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        return value
