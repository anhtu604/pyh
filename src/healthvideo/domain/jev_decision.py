from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HASH_REGEX = r"^[0-9a-f]{64}$"
_DECISION_ID_REGEX = r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$"
_FORBIDDEN_KEY_PATTERN = re.compile(
    r"(?:token|secret|password|api[_-]?key|raw[_-]?(?:provider[_-]?)?response)",
    re.IGNORECASE,
)


class JevDecisionKind(StrEnum):
    TOPIC_TRIAGE = "topic_triage"
    CLAIM_TRIAGE = "claim_triage"
    SECOND_MODEL_ROUTING = "second_model_routing"


class TopicPriorityBand(StrEnum):
    HIGH = "high"
    STANDARD = "standard"
    LOW = "low"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class ClaimCheckFlag(StrEnum):
    CITATION_CHECK = "citation_check"
    ABSOLUTE_LANGUAGE_CHECK = "absolute_language_check"
    POPULATION_APPLICABILITY_CHECK = "population_applicability_check"
    CLEAR_FOR_REVIEW = "clear_for_review"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class SecondModelRecommendation(StrEnum):
    NOT_RECOMMENDED = "not_recommended"
    CONSIDER_REVIEW = "consider_review"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class TopicRiskFlag(StrEnum):
    NOVEL_UNVERIFIED_CLAIM = "novel_unverified_claim"
    HIGH_HARM_POTENTIAL = "high_harm_potential"
    VULNERABLE_POPULATION = "vulnerable_population"
    COMMERCIAL_BIAS = "commercial_bias"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class TopicTriageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str = Field(min_length=1)
    title: str = Field(min_length=1)
    question: str = ""
    target_audience: str = ""
    preventive_value: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_readiness: float = Field(default=0.5, ge=0.0, le=1.0)
    clarity: float = Field(default=0.5, ge=0.0, le=1.0)
    harm_risk: float = Field(default=0.5, ge=0.0, le=1.0)
    production_cost: float = Field(default=0.5, ge=0.0, le=1.0)


class ClaimTriageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(min_length=1)
    text_public: str = Field(min_length=1)
    text_technical: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    certainty: str = Field(min_length=1)
    source_count: int = Field(ge=0)
    source_types: list[str] = Field(default_factory=list)


class SecondModelRoutingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_slug: str = Field(min_length=1)
    revision: str = Field(pattern=r"^[0-9]{3}$")
    source_state: str = Field(min_length=1)
    claim_count: int = Field(ge=0)
    unrated_certainty_count: int = Field(ge=0)
    low_certainty_count: int = Field(ge=0)
    has_doctor_notes: bool = False


class JevAdvisoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    decision_id: str = Field(pattern=_DECISION_ID_REGEX)
    decision_kind: JevDecisionKind
    normalized_choice: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    model_identifier: str = Field(min_length=1)
    input_hash: str = Field(pattern=_HASH_REGEX)
    created_at: datetime
    reason: str = Field(min_length=1, max_length=500)
    policy_threshold: float = Field(default=0.90, ge=0.0, le=1.0)
    flags: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("created_at")
    @classmethod
    def validate_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @field_validator("metadata")
    @classmethod
    def validate_clean_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        for key in value:
            if _FORBIDDEN_KEY_PATTERN.search(key):
                raise ValueError(f"metadata contains sensitive or forbidden key: {key!r}")
        return value

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= self.policy_threshold
