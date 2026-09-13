from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from healthvideo.domain.asset_manifest import (
    DECORATIVE_KINDS,
    SEMANTIC_REQUIRED_KINDS,
    AssetIntegrityError,
    AssetKind,
    AssetManifest,
    AssetRecord,
    load_asset_manifest,
    validate_asset_manifest,
    validate_reclassification,
)
from healthvideo.storage.files import read_yaml, sha256_file

GOLDEN_ASSET_MANIFEST = Path(
    "tests/fixtures/golden-project-v2/revisions/001/assets/asset-manifest.yaml"
)
GOLDEN_REVISION_ROOT = GOLDEN_ASSET_MANIFEST.parents[1]
SYNTHETIC_SHA256 = "a" * 64


def asset_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": "assets/evidence-r01.svg",
        "kind": AssetKind.EVIDENCE_HIGHLIGHT,
        "semantic": True,
        "classification_reason": "Evidence highlight changes the medical meaning.",
        "sha256": SYNTHETIC_SHA256,
        "source": "synthetic_test_fixture",
        "license": "synthetic_test_only",
        "creator": "repository_fixture",
        "revision": "001",
    }
    payload.update(overrides)
    return payload


def copy_golden_v2_revision(root: Path) -> Path:
    """Copy the tracked revision 001 directory so tests can mutate it freely."""
    destination = root / "golden-v2-revision-001"
    shutil.copytree(GOLDEN_REVISION_ROOT, destination)
    return destination


# ---------------------------------------------------------------------------
# Semantic classification policy (§7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(SEMANTIC_REQUIRED_KINDS))
def test_medical_asset_kinds_cannot_be_marked_decorative(kind: AssetKind) -> None:
    with pytest.raises(ValidationError, match="semantic=true"):
        AssetRecord(**asset_payload(kind=kind, semantic=False))


@pytest.mark.parametrize("kind", sorted(SEMANTIC_REQUIRED_KINDS))
def test_medical_asset_kinds_accept_semantic_true(kind: AssetKind) -> None:
    record = AssetRecord(**asset_payload(kind=kind, semantic=True))
    assert record.kind is kind
    assert record.semantic is True


def test_mascot_reaction_must_be_decorative() -> None:
    with pytest.raises(ValidationError, match="mascot_reaction.*semantic=false"):
        AssetRecord(**asset_payload(kind="mascot_reaction", semantic=True))


def test_mascot_annotation_must_be_semantic() -> None:
    with pytest.raises(ValidationError, match="semantic=true"):
        AssetRecord(
            **asset_payload(kind="mascot_medical_annotation", semantic=False)
        )


@pytest.mark.parametrize("kind", sorted(DECORATIVE_KINDS))
def test_decorative_kinds_may_be_marked_non_semantic(kind: AssetKind) -> None:
    record = AssetRecord(
        **asset_payload(
            path="assets/bg-01.svg",
            kind=kind,
            semantic=False,
            classification_reason=None,
        )
    )
    assert record.kind is kind
    assert record.semantic is False


@pytest.mark.parametrize(
    "kind", sorted(DECORATIVE_KINDS - {AssetKind.MASCOT_REACTION})
)
def test_decorative_kinds_may_still_be_marked_semantic(kind: AssetKind) -> None:
    record = AssetRecord(**asset_payload(path="assets/bg-01.svg", kind=kind, semantic=True))
    assert record.semantic is True


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_path",
    [
        "/absolute/evidence.svg",
        "../escape.svg",
        "assets/../../escape.svg",
        "assets\\evidence.svg",
        "",
        "   ",
        "C:/evidence.svg",
    ],
)
def test_asset_record_rejects_unsafe_paths(bad_path: str) -> None:
    with pytest.raises(ValidationError):
        AssetRecord(**asset_payload(path=bad_path))


def test_validate_asset_manifest_rejects_path_that_escapes_revision_root(
    tmp_path: Path,
) -> None:
    """A manifest built without going through AssetRecord's own validators
    (e.g. read back from a source that skipped validation) must still be
    refused by validate_asset_manifest itself — the gate cannot rely solely
    on validation having already happened upstream."""
    revision = tmp_path / "revision"
    (revision / "assets").mkdir(parents=True)
    (revision / "assets" / "in-scope.svg").write_bytes(b"<svg/>")
    outside = tmp_path / "outside.svg"
    outside.write_bytes(b"<svg/>")

    manifest = AssetManifest.model_construct(
        assets=(
            AssetRecord.model_construct(
                path="assets/../../outside.svg",
                kind=AssetKind.BACKGROUND,
                semantic=False,
                classification_reason=None,
                sha256=SYNTHETIC_SHA256,
                source="s",
                license="l",
                creator="c",
                revision="001",
            ),
        )
    )

    with pytest.raises(ValueError, match="relative POSIX with no escape"):
        validate_asset_manifest(revision, manifest)


# ---------------------------------------------------------------------------
# Duplicate paths
# ---------------------------------------------------------------------------


def test_manifest_rejects_duplicate_asset_paths() -> None:
    duplicate = AssetRecord(**asset_payload())
    with pytest.raises(ValidationError, match="duplicate asset path"):
        AssetManifest(assets=(duplicate, duplicate))


# ---------------------------------------------------------------------------
# Byte integrity gate
# ---------------------------------------------------------------------------


def test_manifest_rejects_missing_or_changed_asset_bytes(tmp_path: Path) -> None:
    revision = copy_golden_v2_revision(tmp_path)
    manifest = load_asset_manifest(revision / "assets" / "asset-manifest.yaml")
    (revision / manifest.assets[0].path).write_bytes(b"changed")
    with pytest.raises(AssetIntegrityError, match="sha256"):
        validate_asset_manifest(revision, manifest)


def test_manifest_rejects_asset_missing_from_disk(tmp_path: Path) -> None:
    revision = copy_golden_v2_revision(tmp_path)
    manifest = load_asset_manifest(revision / "assets" / "asset-manifest.yaml")
    (revision / manifest.assets[0].path).unlink()
    with pytest.raises(AssetIntegrityError, match="sha256"):
        validate_asset_manifest(revision, manifest)


def test_validate_asset_manifest_passes_for_matching_bytes(tmp_path: Path) -> None:
    revision = tmp_path / "revision"
    (revision / "assets").mkdir(parents=True)
    asset_path = revision / "assets" / "evidence-r01.svg"
    asset_path.write_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")
    digest = sha256_file(asset_path)

    manifest = AssetManifest(
        assets=(
            AssetRecord(
                **asset_payload(
                    path="assets/evidence-r01.svg",
                    sha256=digest,
                )
            ),
        )
    )

    validate_asset_manifest(revision, manifest)


def test_validate_asset_manifest_skips_byte_check_for_decorative_assets(
    tmp_path: Path,
) -> None:
    revision = tmp_path / "revision"
    revision.mkdir(parents=True)

    manifest = AssetManifest(
        assets=(
            AssetRecord(
                **asset_payload(
                    path="assets/missing-background.svg",
                    kind=AssetKind.BACKGROUND,
                    semantic=False,
                    classification_reason=None,
                )
            ),
        )
    )

    validate_asset_manifest(revision, manifest)


# ---------------------------------------------------------------------------
# Reclassification helper
# ---------------------------------------------------------------------------


def test_validate_reclassification_rejects_downgrade_without_reason() -> None:
    previous = AssetManifest(
        assets=(
            AssetRecord(
                **asset_payload(
                    path="assets/bg-01.svg",
                    kind=AssetKind.BACKGROUND,
                    semantic=True,
                )
            ),
        )
    )
    updated = AssetManifest(
        assets=(
            AssetRecord(
                **asset_payload(
                    path="assets/bg-01.svg",
                    kind=AssetKind.BACKGROUND,
                    semantic=False,
                    classification_reason=None,
                )
            ),
        )
    )

    with pytest.raises(ValueError, match="classification_reason"):
        validate_reclassification(previous, updated)


def test_validate_reclassification_allows_downgrade_with_reason() -> None:
    previous = AssetManifest(
        assets=(
            AssetRecord(
                **asset_payload(
                    path="assets/bg-01.svg",
                    kind=AssetKind.BACKGROUND,
                    semantic=True,
                )
            ),
        )
    )
    updated = AssetManifest(
        assets=(
            AssetRecord(
                **asset_payload(
                    path="assets/bg-01.svg",
                    kind=AssetKind.BACKGROUND,
                    semantic=False,
                    classification_reason="Editorial review confirmed this is purely decorative.",
                )
            ),
        )
    )

    validate_reclassification(previous, updated)


def test_validate_reclassification_allows_upgrade_without_reason() -> None:
    previous = AssetManifest(
        assets=(
            AssetRecord(
                **asset_payload(
                    path="assets/bg-01.svg",
                    kind=AssetKind.BACKGROUND,
                    semantic=False,
                    classification_reason=None,
                )
            ),
        )
    )
    updated = AssetManifest(
        assets=(
            AssetRecord(
                **asset_payload(
                    path="assets/bg-01.svg",
                    kind=AssetKind.BACKGROUND,
                    semantic=True,
                )
            ),
        )
    )

    validate_reclassification(previous, updated)


def test_validate_reclassification_ignores_new_or_removed_assets() -> None:
    previous = AssetManifest(assets=())
    updated = AssetManifest(
        assets=(
            AssetRecord(
                **asset_payload(
                    path="assets/bg-01.svg",
                    kind=AssetKind.BACKGROUND,
                    semantic=False,
                    classification_reason=None,
                )
            ),
        )
    )

    validate_reclassification(previous, updated)


# ---------------------------------------------------------------------------
# Golden fixture: the tracked YAML must load and validate byte-identical
# ---------------------------------------------------------------------------


def test_task1_golden_asset_manifest_loads_without_rewrite() -> None:
    path = GOLDEN_ASSET_MANIFEST
    before = path.read_bytes()

    manifest = AssetManifest.model_validate(read_yaml(path))
    validate_asset_manifest(path.parents[1], manifest)

    assert path.read_bytes() == before
    assert manifest.assets[0].path == "assets/evidence-r01.svg"
    assert manifest.assets[0].kind is AssetKind.EVIDENCE_HIGHLIGHT
    assert manifest.assets[0].semantic is True
