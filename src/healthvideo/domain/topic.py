"""Domain models for topic discovery, signals, and triage scoring (§8)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TopicSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    platform: str
    url: str | None = None
    query: str = ""
    timestamp: datetime
    trend_metric: float | None = None


class TopicScores(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    novelty: float = Field(default=0.5, ge=0.0, le=1.0)
    preventive_value: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_readiness: float = Field(default=0.5, ge=0.0, le=1.0)
    clarity: float = Field(default=0.5, ge=0.0, le=1.0)
    harm_risk: float = Field(default=0.5, ge=0.0, le=1.0)
    production_cost: float = Field(default=0.5, ge=0.0, le=1.0)


def calculate_triage_rank(scores: TopicScores) -> float:
    """Calculate a normalized ranking score (0.0 to 1.0) for topic triage (§8)."""
    weighted = (
        scores.preventive_value * 0.35
        + scores.evidence_readiness * 0.30
        + scores.clarity * 0.15
        + scores.novelty * 0.10
        + (1.0 - scores.harm_risk) * 0.05
        + (1.0 - scores.production_cost) * 0.05
    )
    return round(max(0.0, min(1.0, weighted)), 4)


class TopicCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    id: str = ""
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str
    question: str = ""
    target_audience: str = ""
    signals: list[TopicSignal] = Field(default_factory=list)
    scores: TopicScores = Field(default_factory=TopicScores)
    status: Literal["inbox", "selected", "rejected"] = "inbox"
    rejection_reason: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    synthetic_test_record: bool = False
    origin: str | None = None

    @model_validator(mode="after")
    def _ensure_id(self) -> TopicCard:
        if not self.id:
            object.__setattr__(self, "id", self.slug)
        return self
