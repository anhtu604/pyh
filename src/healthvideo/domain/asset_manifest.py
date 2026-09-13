"""Semantic asset manifest and the §7 classification policy that governs it.

An asset manifest tracks every image used by a revision's storyboard and
whether it carries medical meaning (`semantic=true`) or is purely
decorative (`semantic=false`). The storyboard/editorial agent sets that
flag while drafting (step I); this module enforces the policy that governs
it and a doctor only confirms it later at M2 — this module never asks
"is this classification medically correct", only "is this classification
internally consistent and are the bytes it claims to describe real".
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.storage.files import read_yaml, sha256_file

_SHA256_HEX_PATTERN = r"^[0-9a-f]{64}$"
_REVISION_ID_PATTERN = r"^[0-9]{3}$"


class AssetKind(StrEnum):
    EVIDENCE_HIGHLIGHT = "evidence_highlight"
    DATA_CHART = "data_chart"
    MEDICAL_DIAGRAM = "medical_diagram"
    MEDICAL_TEXT = "medical_text"
    BACKGROUND = "background"
    TEXTURE = "texture"
    FLOURISH = "flourish"
    TRANSITION = "transition"
    MASCOT_REACTION = "mascot_reaction"
    MASCOT_MEDICAL_ANNOTATION = "mascot_medical_annotation"


# §7: an evidence highlight, any chart that plots data or backs a claim, a
# medical diagram, and medical text/marker overlays always change medical
# meaning — they must always be classified `semantic=true`.
SEMANTIC_REQUIRED_KINDS: frozenset[AssetKind] = frozenset(
    {
        AssetKind.EVIDENCE_HIGHLIGHT,
        AssetKind.DATA_CHART,
        AssetKind.MEDICAL_DIAGRAM,
        AssetKind.MEDICAL_TEXT,
        AssetKind.MASCOT_MEDICAL_ANNOTATION,
    }
)

# §7: only these purely decorative kinds may ever be classified
# `semantic=false`.
DECORATIVE_KINDS: frozenset[AssetKind] = frozenset(
    {
        AssetKind.BACKGROUND,
        AssetKind.TEXTURE,
        AssetKind.FLOURISH,
        AssetKind.TRANSITION,
        AssetKind.MASCOT_REACTION,
    }
)


class AssetIntegrityError(ValueError):
    """A semantic asset is missing on disk or its bytes changed since classification."""


class AssetRecord(BaseModel):
    """One tracked asset, its classification, and its provenance.

    ``path`` must already be a safe POSIX-relative path with no ``..``
    segment and no absolute root; whether it actually resolves inside a
    given revision is checked later by :func:`validate_asset_manifest`,
    which has the revision root to check it against.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(pattern=r"\S")
    kind: AssetKind
    semantic: bool
    classification_reason: str | None = None
    sha256: str = Field(pattern=_SHA256_HEX_PATTERN)
    source: str = Field(pattern=r"\S")
    license: str = Field(pattern=r"\S")
    creator: str = Field(pattern=r"\S")
    revision: str = Field(pattern=_REVISION_ID_PATTERN)
    rights_required: bool = False

    @model_validator(mode="after")
    def _validate_path_shape(self) -> AssetRecord:
        _posix_relative_path(self.path)
        return self

    @model_validator(mode="after")
    def _enforce_semantic_policy(self) -> AssetRecord:
        if self.kind is AssetKind.MASCOT_REACTION and self.semantic:
            raise ValueError("asset kind 'mascot_reaction' must be semantic=false")
        if self.kind in SEMANTIC_REQUIRED_KINDS and not self.semantic:
            raise ValueError(
                f"asset kind {self.kind.value!r} always changes medical meaning "
                "and must be classified semantic=true"
            )
        return self


class AssetManifest(BaseModel):
    """The full set of tracked assets for one revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    assets: tuple[AssetRecord, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _reject_duplicate_paths(self) -> AssetManifest:
        seen: set[str] = set()
        for asset in self.assets:
            if asset.path in seen:
                raise ValueError(f"duplicate asset path in manifest: {asset.path}")
            seen.add(asset.path)
        return self


def load_asset_manifest(path: Path) -> AssetManifest:
    """Read and validate an asset manifest from its tracked YAML file."""
    return AssetManifest.model_validate(read_yaml(path))


def validate_asset_manifest(revision_root: Path, manifest: AssetManifest) -> None:
    """Enforce path safety and byte-for-byte integrity for every asset.

    Every declared path must resolve inside ``revision_root``. Every asset
    marked ``semantic=true`` must additionally exist on disk and match its
    declared SHA-256 exactly — a decorative (``semantic=false``) asset is
    not gate-relevant and is only path-checked. A missing file or a byte
    mismatch raises :class:`AssetIntegrityError`, distinct from the plain
    ``ValueError`` raised for an unsafe path, so callers can tell "this
    asset was never here" apart from "this asset moved after classification".
    """
    root = revision_root.resolve()
    for asset in manifest.assets:
        resolved = _resolve_inside_root(root, asset.path)
        if not asset.semantic:
            continue
        if not resolved.is_file():
            raise AssetIntegrityError(
                f"semantic asset is missing on disk, expected sha256 "
                f"{asset.sha256}: {asset.path}"
            )
        actual = sha256_file(resolved)
        if actual != asset.sha256:
            raise AssetIntegrityError(
                f"semantic asset sha256 mismatch for {asset.path}: "
                f"expected {asset.sha256}, found {actual}"
            )


def validate_reclassification(previous: AssetManifest, updated: AssetManifest) -> None:
    """Reject a decorative downgrade that does not explain itself.

    Comparing an earlier manifest to a later one, any asset that used to be
    ``semantic=true`` and is now ``semantic=false`` must carry a non-blank
    ``classification_reason`` on the new record. A silent downgrade is
    rejected outright: it could otherwise hide an asset that used to carry
    medical meaning behind a decorative reclassification nobody explained.
    """
    previous_by_path = {asset.path: asset for asset in previous.assets}
    for asset in updated.assets:
        prior = previous_by_path.get(asset.path)
        if prior is None or not prior.semantic or asset.semantic:
            continue
        if not asset.classification_reason or not asset.classification_reason.strip():
            raise ValueError(
                "asset reclassified from semantic=true to semantic=false "
                f"without a classification_reason: {asset.path}"
            )


def _resolve_inside_root(root: Path, relative: str) -> Path:
    posix_path = _posix_relative_path(relative)
    candidate = root.joinpath(*posix_path.parts)
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise ValueError(f"asset path escapes the revision root: {relative}")
    return resolved


def _posix_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    parts = path.parts
    if (
        not value
        or not parts
        or value in {".", "./"}
        or "\\" in value
        or path.is_absolute()
        or ".." in parts
        or (parts and ":" in parts[0])
    ):
        raise ValueError(f"asset path must be relative POSIX with no escape: {value}")
    return path
