"""Domain models for evidence claims, source records, and literature search artifacts (§9)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    retraction_status: Literal["clean", "retracted", "expression_of_concern", "unverified"] = (
        "unverified"
    )
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
    evidence_direction: Literal["supporting", "conflicting", "inconclusive"] = "supporting"
    doctor_notes: str = ""
    synthetic_test_record: bool = False


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
