"""Domain models for evidence claims, source records, and literature search artifacts (§9)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _sanitize_error_summary(value: object) -> object:
    """Keep provider errors single-line, printable, and safe to persist in YAML."""
    if not isinstance(value, str):
        return value
    printable = "".join(character if character.isprintable() else " " for character in value)
    return " ".join(printable.split())[:500]


class ProviderOutcome(BaseModel):
    """One provider result, preserving failures separately from zero results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=100)
    query_id: str = Field(min_length=1, max_length=128)
    status: Literal["completed", "zero_results", "failed"]
    result_count: int | None = Field(default=None, ge=0)
    failure_class: str | None = Field(default=None, max_length=100)
    error_summary: str | None = Field(default=None, max_length=500)

    @field_validator("error_summary", mode="before")
    @classmethod
    def _sanitize_error_summary(cls, value: object) -> object:
        return _sanitize_error_summary(value)

    @model_validator(mode="after")
    def _validate_status_details(self) -> ProviderOutcome:
        if not self.provider.strip() or not self.query_id.strip():
            raise ValueError("provider and query_id must be nonblank")
        if self.status == "failed":
            if not self.failure_class or not self.failure_class.strip():
                raise ValueError("failed provider outcome requires failure_class")
            if not self.error_summary or not self.error_summary.strip():
                raise ValueError("failed provider outcome requires error_summary")
            if self.result_count is not None:
                raise ValueError("failed provider outcome cannot report result_count")
        elif self.failure_class is not None or self.error_summary is not None:
            raise ValueError("non-failed provider outcome cannot include failure details")
        elif self.status == "zero_results" and self.result_count != 0:
            raise ValueError("zero_results provider outcome requires result_count=0")
        elif self.status == "completed" and (
            self.result_count is None or self.result_count <= 0
        ):
            raise ValueError("completed provider outcome requires positive result_count")
        return self


# ponytail: Substring matching can flag negations and miss paraphrases; medical review is still required.
MECHANISM_EFFECT_KEYWORDS = ("giảm nguy cơ", "hiệu quả", "nên dùng", "có ích")


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


class ClaimSupport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    quote: str = Field(min_length=1)

    @field_validator("source_id", "locator")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("support source_id and locator must be nonblank")
        return value

    @field_validator("quote")
    @classmethod
    def _short_quote(cls, value: str) -> str:
        if not value.strip() or len(value.split()) > 25:
            raise ValueError("support quote must contain 1–25 words")
        return value


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0"
    id: str
    text_public: str
    text_technical: str
    type: Literal["evidence", "interpretation", "professional_opinion", "mechanism"]
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
    support: list[ClaimSupport] = Field(default_factory=list)
    # Doctor-owned: claims stating the limits/exceptions of this claim. A vertical
    # clip that shows this claim must also show every caveat claim (spec §4.2).
    caveat_claim_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_support(self) -> EvidenceClaim:
        # Quote matching needs the ignored cache, so it runs on write and review
        # (validate_support_records), never on load: a cleared cache must not brick a ledger.
        for item in self.support:
            if item.source_id not in self.sources:
                raise ValueError(f"Claim {self.id}: support source {item.source_id} not in sources")
        return self

    @model_validator(mode="after")
    def _validate_mechanism(self) -> EvidenceClaim:
        if self.type != "mechanism":
            return self
        if not self.sources:
            raise ValueError(
                "mechanism requires a source; use type professional_opinion for expert opinion"
            )
        if any(keyword in self.text_public.casefold() for keyword in MECHANISM_EFFECT_KEYWORDS):
            raise ValueError("mechanism cannot claim intervention effects; use type evidence")
        return self

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
    queries: list[dict[str, object]] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid", frozen=True)

    database: str
    query: str
    searched_at: datetime
    total_results: int = 0
    retrieved_count: int = 0
    provider_outcomes: tuple[ProviderOutcome, ...] = ()


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
    pub_type: str = ""


class SourceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    decision: Literal["included", "excluded"]
    reason: str
