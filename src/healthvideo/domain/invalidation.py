"""Deterministic, fail-closed gate-invalidation policy (§7 invalidation engine).

Editors and later stages keep changing artifacts after a gate has been
approved. This module answers one narrow question, purely from data: given
the artifacts that changed since the last approval, how far back through the
pipeline does that change reach — does it merely require a package rebuild,
does it require the production side state, or does it force a full return
through the medical gate?

The policy is expressed as lookup tables, not a long ``if``/``elif`` chain,
mirroring how Tasks 2 and 3 built ``MAIN_RULES``/``SIDE_ENTRY_RULES`` in
``state_graph.py``. It never touches the filesystem and never calls the
state graph directly — callers combine its verdict with ``transition_v2``
themselves.

Fail-closed is the load-bearing property here: any artifact path this
engine does not recognise, and any malformed or empty ``publish/metadata.yaml``
pointer set, resolves to :attr:`InvalidationLevel.MEDICAL` — the most severe
level — never to a lower one. A gap in this table must never be silently
read as "safe".
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path, PurePosixPath

from healthvideo.domain.asset_manifest import AssetManifest, AssetRecord
from healthvideo.domain.project_v2 import WorkflowState


class InvalidationLevel(IntEnum):
    """How far back through the pipeline a change invalidates approvals.

    Ordered by increasing severity: ``NONE < PACKAGE < VIDEO < MEDICAL``.
    ``MEDICAL`` is the most severe level and forces a return through the
    medical gate.
    """

    NONE = 0
    PACKAGE = 1
    VIDEO = 2
    MEDICAL = 3


@dataclass(frozen=True)
class ArtifactChange:
    """One artifact that changed since the last approval.

    ``json_pointers`` names the specific fields that changed within a
    YAML/JSON artifact. An empty frozenset means "the whole file changed"
    or the artifact type does not use pointers (e.g. a binary/audio file).
    """

    path: Path
    json_pointers: frozenset[str]


@dataclass(frozen=True)
class InvalidationDecision:
    """The worst-case invalidation verdict across a set of artifact changes.

    ``target_state`` is the side state the workflow must return to; it is
    ``None`` at :attr:`InvalidationLevel.NONE` and
    :attr:`InvalidationLevel.PACKAGE`, since neither level changes the gate.
    """

    level: InvalidationLevel
    target_state: WorkflowState | None
    reason_codes: frozenset[str]


# §7: the only publish/metadata.yaml JSON pointers that merely require a
# package rebuild. Every other pointer on that file -- caption, hashtag,
# disclaimer, source list, thumbnail text, pinned comment, an empty pointer
# set (whole file changed), or a malformed pointer -- fails closed to
# InvalidationLevel.MEDICAL below.
PUBLISH_METADATA_PACKAGE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "/posting/platform",
        "/posting/account_handle",
        "/posting/scheduled_at",
        "/posting/visibility",
        "/posting/allow_comments",
        "/posting/allow_duet",
        "/posting/allow_stitch",
        "/tracking/campaign_id",
    }
)

_PUBLISH_METADATA_PATH = PurePosixPath("publish/metadata.yaml")

# §7: evidence, script and storyboard are the medical source-of-truth
# artifacts; audio, timing and render artifacts are pure production output
# and never carry medical meaning by construction. Semantic/decorative
# asset changes are resolved separately, against the asset manifest, before
# this table is ever consulted.
_GATE_PREFIX_LEVELS: Mapping[str, InvalidationLevel] = {
    "evidence": InvalidationLevel.MEDICAL,
    "script": InvalidationLevel.MEDICAL,
    "storyboard": InvalidationLevel.MEDICAL,
    "audio": InvalidationLevel.VIDEO,
    "timing": InvalidationLevel.VIDEO,
    "renders": InvalidationLevel.VIDEO,
}

_TARGET_STATE_BY_LEVEL: Mapping[InvalidationLevel, WorkflowState] = {
    InvalidationLevel.MEDICAL: WorkflowState.NEEDS_MEDICAL_REVISION,
    InvalidationLevel.VIDEO: WorkflowState.NEEDS_PRODUCTION_REVISION,
}


def evaluate_invalidation(
    changes: Iterable[ArtifactChange], asset_manifest: AssetManifest
) -> InvalidationDecision:
    """Return the single worst-case invalidation decision for ``changes``.

    Every change is classified independently; the returned decision reflects
    the maximum severity found across all of them -- never the first match,
    never the last -- with ``reason_codes`` limited to the changes that
    actually reached that maximum. An empty ``changes`` iterable returns
    :attr:`InvalidationLevel.NONE` with no target state and no reasons.
    """
    assets_by_path = {asset.path: asset for asset in asset_manifest.assets}
    classified = [_classify_change(change, assets_by_path) for change in changes]

    if not classified:
        return InvalidationDecision(InvalidationLevel.NONE, None, frozenset())

    max_level = max(level for level, _reason in classified)
    reason_codes = frozenset(
        reason for level, reason in classified if level is max_level
    )
    return InvalidationDecision(
        max_level, _TARGET_STATE_BY_LEVEL.get(max_level), reason_codes
    )


def _classify_change(
    change: ArtifactChange, assets_by_path: Mapping[str, AssetRecord]
) -> tuple[InvalidationLevel, str]:
    posix_path = change.path.as_posix()

    asset = assets_by_path.get(posix_path)
    if asset is not None:
        if asset.semantic:
            return InvalidationLevel.MEDICAL, "semantic_asset_changed"
        return InvalidationLevel.VIDEO, "decorative_asset_changed"

    if PurePosixPath(posix_path) == _PUBLISH_METADATA_PATH:
        if (
            change.json_pointers
            and change.json_pointers <= PUBLISH_METADATA_PACKAGE_ALLOWLIST
        ):
            return InvalidationLevel.PACKAGE, "publish_metadata_allowlisted"
        return InvalidationLevel.MEDICAL, "publish_metadata_requires_medical_review"

    parts = PurePosixPath(posix_path).parts
    prefix = parts[0] if parts else ""
    level = _GATE_PREFIX_LEVELS.get(prefix)
    if level is not None:
        return level, f"{prefix}_artifact_changed"

    return InvalidationLevel.MEDICAL, "unknown_artifact_path"
