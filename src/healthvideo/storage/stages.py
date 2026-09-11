"""Append-only storage for stage manifests: one immutable file per stage run."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

from healthvideo.domain.stage import StageManifest
from healthvideo.storage.immutable import write_yaml_once

_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S%f"
_INPUT_HASH_PREFIX_LENGTH = 12


def stage_manifest_path(revision_root: Path, manifest: StageManifest) -> Path:
    """Where ``manifest`` must be recorded.

    The filename encodes the UTC start time and the input-hash prefix so two
    runs of the same stage never collide, and contains no ``:`` so the path
    stays valid on Windows.
    """
    timestamp = manifest.started_at.astimezone(UTC).strftime(_TIMESTAMP_FORMAT)
    hash_prefix = manifest.input_hash[:_INPUT_HASH_PREFIX_LENGTH]
    filename = f"{timestamp}Z-{hash_prefix}.yaml"
    return revision_root / "workflow" / "stages" / manifest.stage / filename


def append_stage_manifest(revision_root: Path, manifest: StageManifest) -> Path:
    """Publish ``manifest`` as a new immutable record; never replaces one already written."""
    path = stage_manifest_path(revision_root, manifest)
    write_yaml_once(path, manifest.model_dump(mode="json"))
    return path
