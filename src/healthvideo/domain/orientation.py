"""Validated, non-decisional artifacts for pre-brief editorial orientation."""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.domain.evidence import CandidateSource

_SHA256_HEX_PATTERN = r"^[0-9a-f]{64}$"
_RUN_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
_REVISION_ID_PATTERN = r"^[0-9]{3}$"


class OrientationScope(BaseModel):
    """The question and boundaries for a light, pre-brief source search."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    topic_question: str = Field(min_length=1, max_length=1_000)
    intended_audience: str = Field(min_length=1, max_length=500)
    scope: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_nonblank_boundaries(self) -> "OrientationScope":
        if not self.topic_question.strip() or not self.intended_audience.strip():
            raise ValueError("orientation question and audience must be nonblank")
        if any(not item.strip() for item in [*self.scope, *self.exclusions]):
            raise ValueError("orientation scope and exclusions must be nonblank")
        return self


class ProviderOutcome(BaseModel):
    """One provider result, preserving failures separately from zero results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=100)
    query_id: str = Field(min_length=1, max_length=128)
    status: Literal["completed", "zero_results", "failed"]
    result_count: int | None = Field(default=None, ge=0)
    failure_class: str | None = Field(default=None, max_length=100)
    error_summary: str | None = Field(default=None, max_length=1_000)

    @model_validator(mode="after")
    def _validate_status_details(self) -> "ProviderOutcome":
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
        elif self.status == "completed" and self.result_count is None:
            raise ValueError("completed provider outcome requires result_count")
        return self


class SourceBackedContext(BaseModel):
    """A neutral context point that names both sources and its limitation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=2_000)
    limitation: str = Field(min_length=1, max_length=2_000)
    source_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _require_nonblank_content(self) -> "SourceBackedContext":
        if not self.text.strip() or not self.limitation.strip():
            raise ValueError("source-backed context and limitation must be nonblank")
        if any(not source_id.strip() for source_id in self.source_ids):
            raise ValueError("source-backed context source IDs must be nonblank")
        return self


class EditorialOption(BaseModel):
    """A neutral, doctor-facing angle; it is never a doctor decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    framing: str = Field(min_length=1, max_length=2_000)
    context_source_ids: list[str] = Field(default_factory=list)
    questions_for_doctor: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def _require_nonblank_editorial_text(self) -> "EditorialOption":
        values = [self.id, self.title, self.framing, *self.context_source_ids]
        if any(not value.strip() for value in values):
            raise ValueError("editorial option fields and context source IDs must be nonblank")
        if any(not question.strip() for question in self.questions_for_doctor):
            raise ValueError("questions_for_doctor must be nonblank")
        return self


class CompletedOrientation(BaseModel):
    """A run-scoped orientation record, deliberately excluding later workflow work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    run_id: str = Field(pattern=_RUN_ID_PATTERN)
    revision: str = Field(default="001", pattern=_REVISION_ID_PATTERN)
    topic_input_hash: str = Field(pattern=_SHA256_HEX_PATTERN)
    included_source_ids: list[str] = Field(min_length=1)
    context_points: list[SourceBackedContext] = Field(min_length=1)
    unresolved_questions: list[str] = Field(default_factory=list)
    communication_risks: list[str] = Field(default_factory=list)
    options: list[EditorialOption]
    provider_outcomes: list[ProviderOutcome] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_internal_references(self) -> "CompletedOrientation":
        if not 2 <= len(self.options) <= 3:
            raise ValueError("completed orientation requires two or three editorial options")
        if any(not source_id.strip() for source_id in self.included_source_ids):
            raise ValueError("included source IDs must be nonblank")
        if len(self.included_source_ids) != len(set(self.included_source_ids)):
            raise ValueError("duplicate included source ID")
        option_ids = [option.id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("duplicate editorial option ID")
        if any(not item.strip() for item in self.unresolved_questions):
            raise ValueError("unresolved questions must be nonblank")
        if any(not item.strip() for item in self.communication_risks):
            raise ValueError("communication risks must be nonblank")

        included = set(self.included_source_ids)
        for context in self.context_points:
            unknown = set(context.source_ids) - included
            if unknown:
                raise ValueError("source-backed context references an unincluded source")
        for option in self.options:
            unknown = set(option.context_source_ids) - included
            if unknown:
                raise ValueError("editorial option context source must be included")
        return self

    def validate_candidate_binding(self, candidates: Sequence[CandidateSource]) -> None:
        """Prove included source IDs resolve to unique candidates in this run."""
        candidate_ids = [candidate.source_id for candidate in candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("duplicate candidate source ID in orientation run")
        candidate_by_id = {candidate.source_id: candidate for candidate in candidates}
        for source_id in self.included_source_ids:
            candidate = candidate_by_id.get(source_id)
            if candidate is None:
                raise ValueError(f"included candidate is missing: {source_id}")
            if not candidate.database.strip() or not candidate.title.strip():
                raise ValueError(f"included candidate lacks provenance: {source_id}")
