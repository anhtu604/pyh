"""Domain models for evidence claims, source records, and literature search artifacts (§9)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChartDatum(BaseModel):
    """An explicitly recorded count, never extracted or estimated by the renderer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["count_of_total"] = "count_of_total"
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    source_id: str = Field(min_length=1)
    label: str = Field(min_length=1, max_length=120)
    value: int = Field(strict=True, ge=0)
    denominator: int = Field(gt=0, le=1_000_000_000)
    unit: str = Field(min_length=1, max_length=40)
    ci_low: int | None = Field(default=None, strict=True, ge=0)
    ci_high: int | None = Field(default=None, strict=True, ge=0)

    @field_validator("source_id", "label", "unit")
    @classmethod
    def _nonblank_xml_text(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("chart labels and source must be nonblank XML text")
        return value

    @model_validator(mode="after")
    def _check_bounds(self) -> ChartDatum:
        if not 0 <= self.value <= self.denominator:
            raise ValueError("chart value must lie within its denominator")
        if (self.ci_low is None) != (self.ci_high is None):
            raise ValueError("chart CI requires both bounds")
        if (
            self.ci_low is not None
            and self.ci_high is not None
            and not 0 <= self.ci_low <= self.value <= self.ci_high <= self.denominator
        ):
            raise ValueError("chart CI must contain the value within the denominator")
        return self


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0"
    id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    study_design: str = ""
    sample_size: int | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    url: str | None = None
    journal: str = ""
    retraction_status: Literal[
        "clean", "retracted", "expression_of_concern", "unverified"
    ] = "unverified"
    conflict_of_interest: str = ""
    key_findings: str = ""
    synthetic_test_record: bool = False


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0"
    id: str
    text_public: str
    text_technical: str
    type: Literal["evidence", "interpretation", "professional_opinion"]
    sources: list[str] = Field(default_factory=list)
    certainty: Literal["high", "moderate", "low", "very_low", "unrated"] = "unrated"
    population: str = ""
    applicability: str = ""
    evidence_direction: Literal["supporting", "conflicting", "inconclusive"] = (
        "supporting"
    )
    doctor_notes: str = ""
    synthetic_test_record: bool = False
    chart_data: list[ChartDatum] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_chart_data(self) -> EvidenceClaim:
        ids = [datum.id for datum in self.chart_data]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate chart datum ID in claim")
        return self


class EvidenceQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    patient_population: str
    intervention: str
    comparison: str = ""
    outcome: str
    search_keywords: list[str] = Field(default_factory=list)
    language: str = "vi"


class SearchLogRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    database: str
    query: str
    searched_at: datetime
    total_results: int = 0
    retrieved_count: int = 0


class CandidateSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    database: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    pmid: str | None = None
    abstract: str = ""
    venue: str = ""


class SourceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    decision: Literal["included", "excluded"]
    reason: str
