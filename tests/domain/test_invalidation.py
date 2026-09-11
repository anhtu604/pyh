from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from healthvideo.domain.asset_manifest import AssetKind, AssetManifest, AssetRecord
from healthvideo.domain.invalidation import (
    PUBLISH_METADATA_PACKAGE_ALLOWLIST,
    ArtifactChange,
    InvalidationLevel,
    evaluate_invalidation,
)
from healthvideo.domain.project_v2 import WorkflowState

SYNTHETIC_SHA256 = "a" * 64
SEMANTIC_ASSET_PATH = "assets/evidence-r01.svg"
DECORATIVE_ASSET_PATH = "assets/bg-01.svg"


def _asset_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": SEMANTIC_ASSET_PATH,
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


@pytest.fixture
def asset_manifest() -> AssetManifest:
    """One semantic asset and one decorative asset, mirroring the golden v2 fixture."""
    return AssetManifest(
        assets=(
            AssetRecord(**_asset_payload()),
            AssetRecord(
                **_asset_payload(
                    path=DECORATIVE_ASSET_PATH,
                    kind=AssetKind.BACKGROUND,
                    semantic=False,
                    classification_reason=None,
                )
            ),
        )
    )


def _change(path: str, pointers: frozenset[str] = frozenset()) -> ArtifactChange:
    return ArtifactChange(path=Path(path), json_pointers=pointers)


# ---------------------------------------------------------------------------
# Plan's RED matrix (Task 7, Step 1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "pointers", "expected"),
    [
        ("evidence/ledger.yaml", frozenset(), InvalidationLevel.MEDICAL),
        ("script/script.yaml", frozenset(), InvalidationLevel.MEDICAL),
        ("audio/narration.wav", frozenset(), InvalidationLevel.VIDEO),
        (
            "publish/metadata.yaml",
            frozenset({"/posting/visibility"}),
            InvalidationLevel.PACKAGE,
        ),
        (
            "publish/metadata.yaml",
            frozenset({"/posting/caption_text"}),
            InvalidationLevel.MEDICAL,
        ),
        ("unknown/file.yaml", frozenset(), InvalidationLevel.MEDICAL),
    ],
)
def test_invalidation_matrix(
    path: str, pointers: frozenset[str], expected: InvalidationLevel, asset_manifest: AssetManifest
) -> None:
    result = evaluate_invalidation(
        [ArtifactChange(path=Path(path), json_pointers=pointers)], asset_manifest
    )
    assert result.level is expected


# ---------------------------------------------------------------------------
# Semantic / decorative asset changes
# ---------------------------------------------------------------------------


def test_semantic_asset_change_forces_medical_review(asset_manifest: AssetManifest) -> None:
    result = evaluate_invalidation([_change(SEMANTIC_ASSET_PATH)], asset_manifest)
    assert result.level is InvalidationLevel.MEDICAL
    assert result.target_state is WorkflowState.NEEDS_MEDICAL_REVISION


def test_decorative_asset_change_forces_production_revision(
    asset_manifest: AssetManifest,
) -> None:
    result = evaluate_invalidation([_change(DECORATIVE_ASSET_PATH)], asset_manifest)
    assert result.level is InvalidationLevel.VIDEO
    assert result.target_state is WorkflowState.NEEDS_PRODUCTION_REVISION


# ---------------------------------------------------------------------------
# storyboard.yaml (matrix only covers evidence/script explicitly)
# ---------------------------------------------------------------------------


def test_storyboard_change_forces_medical_review(asset_manifest: AssetManifest) -> None:
    result = evaluate_invalidation(
        [_change("storyboard/storyboard.yaml")], asset_manifest
    )
    assert result.level is InvalidationLevel.MEDICAL
    assert result.target_state is WorkflowState.NEEDS_MEDICAL_REVISION


# ---------------------------------------------------------------------------
# publish/metadata.yaml allowlist -- exact list from the plan
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pointer", sorted(PUBLISH_METADATA_PACKAGE_ALLOWLIST))
def test_every_allowlisted_metadata_pointer_only_requires_package_rebuild(
    pointer: str, asset_manifest: AssetManifest
) -> None:
    result = evaluate_invalidation(
        [_change("publish/metadata.yaml", frozenset({pointer}))], asset_manifest
    )
    assert result.level is InvalidationLevel.PACKAGE
    assert result.target_state is None


@pytest.mark.parametrize(
    "pointer",
    [
        "/posting/caption_text",
        "/posting/hashtags",
        "/posting/disclaimer",
        "/posting/source_list",
        "/posting/thumbnail_text",
        "/posting/pinned_comment",
    ],
)
def test_non_allowlisted_metadata_pointers_force_medical_review(
    pointer: str, asset_manifest: AssetManifest
) -> None:
    result = evaluate_invalidation(
        [_change("publish/metadata.yaml", frozenset({pointer}))], asset_manifest
    )
    assert result.level is InvalidationLevel.MEDICAL
    assert result.target_state is WorkflowState.NEEDS_MEDICAL_REVISION


def test_mixed_allowlisted_and_non_allowlisted_pointers_force_medical_review(
    asset_manifest: AssetManifest,
) -> None:
    result = evaluate_invalidation(
        [
            _change(
                "publish/metadata.yaml",
                frozenset({"/posting/visibility", "/posting/caption_text"}),
            )
        ],
        asset_manifest,
    )
    assert result.level is InvalidationLevel.MEDICAL


@pytest.mark.parametrize(
    "pointers",
    [
        frozenset(),
        frozenset({"posting/visibility"}),  # malformed: no leading slash
        frozenset({""}),
    ],
)
def test_empty_or_malformed_metadata_pointer_sets_force_medical_review(
    pointers: frozenset[str], asset_manifest: AssetManifest
) -> None:
    result = evaluate_invalidation(
        [_change("publish/metadata.yaml", pointers)], asset_manifest
    )
    assert result.level is InvalidationLevel.MEDICAL


# ---------------------------------------------------------------------------
# Fail-closed default for anything this engine does not recognise
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "unknown/file.yaml",
        "handoffs/note.yaml",
        "assets/untracked-image.svg",
        "",
    ],
)
def test_unrecognized_paths_fail_closed_to_medical(
    path: str, asset_manifest: AssetManifest
) -> None:
    result = evaluate_invalidation([_change(path)], asset_manifest)
    assert result.level is InvalidationLevel.MEDICAL
    assert result.target_state is WorkflowState.NEEDS_MEDICAL_REVISION


# ---------------------------------------------------------------------------
# Multiple simultaneous changes: worst-case (max severity), not first/last
# ---------------------------------------------------------------------------


def test_multiple_changes_take_the_highest_severity_when_worst_is_last(
    asset_manifest: AssetManifest,
) -> None:
    changes = [
        _change("publish/metadata.yaml", frozenset({"/posting/visibility"})),  # package
        _change("audio/narration.wav"),  # video
        _change("evidence/ledger.yaml"),  # medical
    ]
    result = evaluate_invalidation(changes, asset_manifest)
    assert result.level is InvalidationLevel.MEDICAL


def test_multiple_changes_take_the_highest_severity_when_worst_is_first(
    asset_manifest: AssetManifest,
) -> None:
    changes = [
        _change("evidence/ledger.yaml"),  # medical
        _change("audio/narration.wav"),  # video
        _change("publish/metadata.yaml", frozenset({"/posting/visibility"})),  # package
    ]
    result = evaluate_invalidation(changes, asset_manifest)
    assert result.level is InvalidationLevel.MEDICAL


def test_multiple_video_level_changes_do_not_escalate_to_medical(
    asset_manifest: AssetManifest,
) -> None:
    changes = [_change("audio/narration.wav"), _change(DECORATIVE_ASSET_PATH)]
    result = evaluate_invalidation(changes, asset_manifest)
    assert result.level is InvalidationLevel.VIDEO
    assert result.target_state is WorkflowState.NEEDS_PRODUCTION_REVISION


def test_reason_codes_reflect_only_the_changes_at_the_max_severity(
    asset_manifest: AssetManifest,
) -> None:
    changes = [
        _change("publish/metadata.yaml", frozenset({"/posting/visibility"})),  # package
        _change("evidence/ledger.yaml"),  # medical
        _change("script/script.yaml"),  # medical
    ]
    result = evaluate_invalidation(changes, asset_manifest)
    assert result.level is InvalidationLevel.MEDICAL
    assert "publish_metadata_allowlisted" not in result.reason_codes
    assert len(result.reason_codes) == 2


# ---------------------------------------------------------------------------
# No changes at all -> no invalidation
# ---------------------------------------------------------------------------


def test_no_changes_returns_none_level_and_no_target_state(
    asset_manifest: AssetManifest,
) -> None:
    result = evaluate_invalidation([], asset_manifest)
    assert result.level is InvalidationLevel.NONE
    assert result.target_state is None
    assert result.reason_codes == frozenset()


# ---------------------------------------------------------------------------
# Ordering and immutability contract
# ---------------------------------------------------------------------------


def test_invalidation_level_is_ordered_by_increasing_severity() -> None:
    assert (
        InvalidationLevel.NONE
        < InvalidationLevel.PACKAGE
        < InvalidationLevel.VIDEO
        < InvalidationLevel.MEDICAL
    )


def test_invalidation_decision_is_frozen(asset_manifest: AssetManifest) -> None:
    result = evaluate_invalidation([_change("evidence/ledger.yaml")], asset_manifest)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.level = InvalidationLevel.NONE  # type: ignore[misc]


def test_artifact_change_is_frozen() -> None:
    change = _change("evidence/ledger.yaml")
    with pytest.raises(dataclasses.FrozenInstanceError):
        change.path = Path("other.yaml")  # type: ignore[misc]
