"""Domain models and license/provenance validation for the reusable medical animation library."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ANIM_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PMID_RE = re.compile(r"^\d+$")
_PMCID_RE = re.compile(r"^PMC\d+$")
_DOI_RE = re.compile(r"^10\.\S+/\S+$")

_ASSET_EXTENSIONS: frozenset[str] = frozenset({".svg", ".png", ".jpg", ".jpeg", ".webp"})
_PREVIEW_EXTENSIONS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".webp"})

MedAnimCategory = Literal[
    "pathophysiology",
    "physiology",
    "microbiology",
    "pathology",
    "anatomy",
]

ALLOWED_MEDANIM_LICENSES: frozenset[str] = frozenset(
    {"Public Domain", "CC0", "CC BY 3.0", "CC BY 4.0"}
)

_LICENSE_CANONICAL_MAP: dict[str, str] = {
    "public domain": "Public Domain",
    "public-domain": "Public Domain",
    "cc0": "CC0",
    "cc-0": "CC0",
    "cc0 1.0": "CC0",
    "cc0-1.0": "CC0",
    "cc0 1.0 universal": "CC0",
    "cc by 3.0": "CC BY 3.0",
    "cc-by-3.0": "CC BY 3.0",
    "cc by 3.0 unported": "CC BY 3.0",
    "cc by 4.0": "CC BY 4.0",
    "cc-by-4.0": "CC BY 4.0",
    "cc by 4.0 international": "CC BY 4.0",
}


def normalize_medanim_license(raw: str) -> str:
    """Validate and canonicalize an open media license; forbid SA/NC/ND/copyleft."""
    cleaned = " ".join(str(raw or "").strip().split())
    if not cleaned:
        raise ValueError("Asset license must be explicit and nonblank")
    lowered = cleaned.casefold()
    for forbidden in ("by-sa", "sharealike", "share-alike", "-nc", "noncommercial", "non-commercial", "-nd", "noderiv", "no-deriv"):
        if forbidden in lowered:
            raise ValueError(
                f"Forbidden asset license {cleaned!r}: CC BY-SA, NC, and ND are not permitted; "
                "allowed licenses are Public Domain, CC0, CC BY 3.0, CC BY 4.0"
            )
    canonical = _LICENSE_CANONICAL_MAP.get(lowered)
    if canonical is None:
        raise ValueError(
            f"Unsupported asset license {cleaned!r}; allowed licenses are "
            "Public Domain, CC0, CC BY 3.0, CC BY 4.0"
        )
    return canonical


def validate_safe_relative_path(value: str, *, allowed_extensions: frozenset[str] | None = None) -> str:
    """Validate a safe POSIX relative file path with no traversal, drive, or absolute prefix."""
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"Path must be a nonblank trimmed POSIX relative path: {value!r}")
    if "\\" in value or value.startswith("/"):
        raise ValueError(f"Path must be relative POSIX without backslashes: {value!r}")
    posix = PurePosixPath(value)
    parts = posix.parts
    if not parts or value in {".", "./"} or posix.is_absolute() or ".." in parts or ":" in parts[0]:
        raise ValueError(f"Path escapes library root: {value!r}")
    if posix.as_posix() != value:
        raise ValueError(f"Path must use canonical POSIX relative spelling: {value!r}")
    if allowed_extensions is not None and posix.suffix.lower() not in allowed_extensions:
        raise ValueError(
            f"Unsupported file extension {posix.suffix!r} for {value!r}; expected {sorted(allowed_extensions)}"
        )
    return value


def _validate_http_url(value: str, *, field_name: str) -> str:
    cleaned = value.strip()
    parsed = urlsplit(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError(f"{field_name} must be a valid HTTP(S) URL without credentials: {value!r}")
    return cleaned


def _nonblank(value: str, *, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must be nonblank")
    return cleaned


class MedAnimCompositions(BaseModel):
    """Remotion composition IDs registered in video/src/Root.tsx."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    landscape: str = Field(min_length=1)
    portrait: str | None = None

    @field_validator("landscape")
    @classmethod
    def _valid_landscape(cls, value: str) -> str:
        return _nonblank(value, field_name="compositions.landscape")

    @field_validator("portrait")
    @classmethod
    def _valid_portrait(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _nonblank(value, field_name="compositions.portrait")


class MedAnimSource(BaseModel):
    """Peer-reviewed Europe PMC source entry supporting medical claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=80)
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None
    citation: str = Field(min_length=1)
    checked_in: str = Field(min_length=1)
    url: str | None = None
    scope: str | None = None

    @field_validator("id", "citation", "checked_in")
    @classmethod
    def _require_nonblank(cls, value: str) -> str:
        return _nonblank(value, field_name="source field")

    @field_validator("pmid", mode="before")
    @classmethod
    def _clean_pmid(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if not _PMID_RE.fullmatch(text):
            raise ValueError(f"Invalid PMID {text!r}: must contain digits only")
        return text

    @field_validator("pmcid")
    @classmethod
    def _clean_pmcid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if not _PMCID_RE.fullmatch(text):
            raise ValueError(f"Invalid PMCID {text!r}: expected 'PMC<digits>'")
        return text

    @field_validator("doi")
    @classmethod
    def _clean_doi(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if not _DOI_RE.fullmatch(text):
            raise ValueError(f"Invalid DOI {text!r}")
        return text

    @field_validator("url")
    @classmethod
    def _clean_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_http_url(value, field_name="source.url")

    @model_validator(mode="after")
    def _require_identifier(self) -> MedAnimSource:
        if not (self.pmid or self.pmcid or self.doi):
            raise ValueError(f"Source {self.id!r} must provide at least one of pmid, pmcid, or doi")
        return self


class MedAnimQuote(BaseModel):
    """Verbatim source excerpt (<= 25 words) with exact locator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    scope: str | None = None

    @field_validator("source_id", "locator")
    @classmethod
    def _require_nonblank(cls, value: str) -> str:
        return _nonblank(value, field_name="quote field")

    @field_validator("quote")
    @classmethod
    def _check_quote_word_limit(cls, value: str) -> str:
        cleaned = value.strip()
        words = cleaned.split()
        if not words or len(words) > 25:
            raise ValueError(f"Verbatim quote must contain 1..25 words (got {len(words)})")
        return cleaned


class MedAnimStep(BaseModel):
    """One narrated visual mechanism step with grounded scientific claim and quotes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=40)
    narration: str = Field(min_length=1)
    visual: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    quotes: list[MedAnimQuote] = Field(min_length=1)
    t_start: float | None = Field(default=None, ge=0.0)
    t_end: float | None = Field(default=None, gt=0.0)

    @field_validator("id", "narration", "visual", "claim")
    @classmethod
    def _require_nonblank(cls, value: str) -> str:
        return _nonblank(value, field_name="step field")

    @model_validator(mode="after")
    def _check_times(self) -> MedAnimStep:
        if self.t_start is not None and self.t_end is not None and self.t_end <= self.t_start:
            raise ValueError(f"Step {self.id!r}: t_end must exceed t_start")
        return self


class MedAnimAsset(BaseModel):
    """One licensed visual asset bound by SHA-256 and provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    file: str = Field(min_length=1)
    source_page: str = Field(min_length=1)
    original_url: str = Field(min_length=1)
    author: str = Field(min_length=1)
    license: str = Field(min_length=1)
    sha256: str = Field(pattern=_SHA256_RE.pattern)
    role: str | None = None
    license_url: str | None = None
    attribution: str | None = None

    @field_validator("file")
    @classmethod
    def _valid_file(cls, value: str) -> str:
        return validate_safe_relative_path(value, allowed_extensions=_ASSET_EXTENSIONS)

    @field_validator("source_page")
    @classmethod
    def _valid_source_page(cls, value: str) -> str:
        return _validate_http_url(value, field_name="asset.source_page")

    @field_validator("original_url")
    @classmethod
    def _valid_original_url(cls, value: str) -> str:
        return _validate_http_url(value, field_name="asset.original_url")

    @field_validator("license_url")
    @classmethod
    def _valid_license_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_http_url(value, field_name="asset.license_url")

    @field_validator("author")
    @classmethod
    def _valid_author(cls, value: str) -> str:
        return _nonblank(value, field_name="asset.author")

    @field_validator("license")
    @classmethod
    def _valid_license(cls, value: str) -> str:
        return normalize_medanim_license(value)


class MedAnimMedicalAudit(BaseModel):
    """Pre-gate verification recorded by an internal medical/anatomy auditor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    checked_claims: bool
    checked_anatomy: bool
    auditor_role: str = Field(min_length=1)
    audited_at: datetime
    passed: bool
    notes: str = ""

    @field_validator("auditor_role")
    @classmethod
    def _valid_role(cls, value: str) -> str:
        return _nonblank(value, field_name="medical_audit.auditor_role")

    @field_validator("audited_at")
    @classmethod
    def _require_tz(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("medical_audit.audited_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _require_checks_when_passed(self) -> MedAnimMedicalAudit:
        if self.passed and not (self.checked_claims and self.checked_anatomy):
            raise ValueError("medical_audit.passed=true requires both checked_claims and checked_anatomy to be true")
        return self


class MedAnimEntry(BaseModel):
    """Schema for library/medanim/<anim_id>/animation.yaml."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    id: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=1)
    category: MedAnimCategory
    summary: str = Field(min_length=1)
    target_duration_seconds: float = Field(gt=0.0)
    compositions: MedAnimCompositions
    sources: list[MedAnimSource] = Field(min_length=1)
    steps: list[MedAnimStep] = Field(min_length=1)
    assets: list[MedAnimAsset] = Field(min_length=1)
    medical_audit: MedAnimMedicalAudit
    open_issues: list[dict[str, Any]] = Field(default_factory=list)
    preview_frames: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ANIM_ID_RE.fullmatch(value):
            raise ValueError(f"Invalid animation id {value!r}: expected lowercase kebab-case slug")
        return value

    @field_validator("title", "summary")
    @classmethod
    def _valid_text(cls, value: str) -> str:
        return _nonblank(value, field_name="animation metadata")

    @field_validator("preview_frames")
    @classmethod
    def _valid_previews(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        cleaned: list[str] = []
        for item in value:
            rel = validate_safe_relative_path(item, allowed_extensions=_PREVIEW_EXTENSIONS)
            if rel in seen:
                raise ValueError(f"Duplicate preview frame path: {rel!r}")
            seen.add(rel)
            cleaned.append(rel)
        return cleaned

    @model_validator(mode="after")
    def _check_cross_references(self) -> MedAnimEntry:
        source_ids: set[str] = set()
        for src in self.sources:
            if src.id in source_ids:
                raise ValueError(f"Duplicate source id: {src.id!r}")
            source_ids.add(src.id)

        step_ids: set[str] = set()
        for step in self.steps:
            if step.id in step_ids:
                raise ValueError(f"Duplicate step id: {step.id!r}")
            step_ids.add(step.id)
            for quote in step.quotes:
                if quote.source_id not in source_ids:
                    raise ValueError(
                        f"Step {step.id!r} references unknown source_id {quote.source_id!r}"
                    )

        asset_files: set[str] = set()
        for asset in self.assets:
            if asset.file in asset_files:
                raise ValueError(f"Duplicate asset file in animation.yaml: {asset.file!r}")
            asset_files.add(asset.file)
        return self


class MedAnimApprovalRecord(BaseModel):
    """Immutable doctor approval written to library/medanim/<anim_id>/doctor-approval.yaml."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    decision: Literal["approved"] = "approved"
    anim_id: str = Field(min_length=2, max_length=80)
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    content_sha256: str = Field(pattern=_SHA256_RE.pattern)
    asset_sha256: dict[str, str] = Field(min_length=1)
    note: str = ""

    @field_validator("anim_id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ANIM_ID_RE.fullmatch(value):
            raise ValueError(f"Invalid anim_id {value!r}")
        return value

    @field_validator("reviewer")
    @classmethod
    def _valid_reviewer(cls, value: str) -> str:
        return _nonblank(value, field_name="reviewer")

    @field_validator("reviewed_at")
    @classmethod
    def _require_tz(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        return value

    @field_validator("asset_sha256")
    @classmethod
    def _valid_asset_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        for path, digest in value.items():
            validate_safe_relative_path(path, allowed_extensions=_ASSET_EXTENSIONS)
            if not _SHA256_RE.fullmatch(digest):
                raise ValueError(f"Invalid asset sha256 for {path!r}")
        return value


class MedAnimRejectionRecord(BaseModel):
    """Immutable doctor rejection written to library/medanim/<anim_id>/reviews/<ts>-rejected.yaml."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    decision: Literal["rejected"] = "rejected"
    anim_id: str = Field(min_length=2, max_length=80)
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    reason: str = Field(min_length=1)
    content_sha256: str = Field(pattern=_SHA256_RE.pattern)
    asset_sha256: dict[str, str] = Field(default_factory=dict)

    @field_validator("anim_id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ANIM_ID_RE.fullmatch(value):
            raise ValueError(f"Invalid anim_id {value!r}")
        return value

    @field_validator("reviewer", "reason")
    @classmethod
    def _valid_text(cls, value: str) -> str:
        return _nonblank(value, field_name="rejection field")

    @field_validator("reviewed_at")
    @classmethod
    def _require_tz(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        return value

    @field_validator("asset_sha256")
    @classmethod
    def _valid_asset_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        for path, digest in value.items():
            validate_safe_relative_path(path, allowed_extensions=_ASSET_EXTENSIONS)
            if not _SHA256_RE.fullmatch(digest):
                raise ValueError(f"Invalid asset sha256 for {path!r}")
        return value
