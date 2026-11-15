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


class RubricScore100(BaseModel):
    """100-point editorial scoring matching Google Sheet THANG_DIEM (A>=80, B=65-79, C<65)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    viral_engagement: int = Field(default=0, ge=0, le=40)
    urgency_prevention: int = Field(default=0, ge=0, le=25)
    evidence_readiness: int = Field(default=0, ge=0, le=20)
    short_feasibility: int = Field(default=0, ge=0, le=15)

    @property
    def total(self) -> int:
        return (
            self.viral_engagement
            + self.urgency_prevention
            + self.evidence_readiness
            + self.short_feasibility
        )

    @property
    def tier(self) -> Literal["A", "B", "C"]:
        score = self.total
        if score >= 80:
            return "A"
        if score >= 65:
            return "B"
        return "C"

    def to_topic_scores(self) -> TopicScores:
        """Convert 100-point rubric into normalized 0..1 TopicScores."""
        return TopicScores(
            novelty=round(min(1.0, self.viral_engagement / 40.0), 3),
            preventive_value=round(min(1.0, self.urgency_prevention / 25.0), 3),
            evidence_readiness=round(min(1.0, self.evidence_readiness / 20.0), 3),
            clarity=round(min(1.0, self.short_feasibility / 15.0), 3),
            harm_risk=0.2 if self.urgency_prevention >= 18 else 0.4,
            production_cost=round(max(0.1, 1.0 - (self.short_feasibility / 15.0) * 0.7), 3),
        )


class TopicDossier(BaseModel):
    """Rich topic dossier preserved from Google Sheet or Researcher discovery."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)
    origin: str = "google_sheet"
    source_tab: str = ""
    source_row: int | None = None
    recorded_date: str = ""
    claim_or_headline: str = ""
    source_signal: str = ""
    source_url: str = ""
    pmid_doi: str = ""
    preliminary_verdict: str = ""
    nuance_notes: str = ""
    doctor_review_points: str = ""
    neutral_hook: str = ""
    recommended_format: Literal["youtube_long", "vertical_clip", "both"] = "both"
    target_seconds: int = Field(default=75, ge=30, le=1800)
    rubric: RubricScore100 = Field(default_factory=RubricScore100)
    rubric_total: int = Field(default=0, ge=0, le=100)
    tier: Literal["A", "B", "C"] = "C"
    status: Literal["inbox", "selected", "rejected"] = "inbox"
    rejection_reason: str | None = None
    synced_at: datetime | None = None

    @model_validator(mode="after")
    def _sync_rubric(self) -> TopicDossier:
        self.rubric_total = self.rubric.total
        self.tier = self.rubric.tier
        return self
