"""Immutable project backup and fail-closed restore (M7 design §4–§5).

Backup copies authoritative project bytes under the write lease into a new
snapshot directory; restore verifies a snapshot and promotes a verified copy
into a new destination. Neither migrates, re-signs or refreshes approvals,
changes workflow state, renders, packages or publishes.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from healthvideo.domain.asset_manifest import load_asset_manifest
from healthvideo.domain.backup import BackupManifest, canonical_relative_path
from healthvideo.domain.gate_review import (
    GateApprovalRecord,
    GateKind,
    GateRejectionRecord,
)
from healthvideo.domain.project import ProjectManifest
from healthvideo.domain.review import ReviewKind, ReviewRecord
from healthvideo.storage.backup import (
    MANIFEST_NAME,
    build_entries,
    copy_entries,
    is_link_or_reparse,
    staging_directory,
    tree_files,
    verify_snapshot_tree,
)
from healthvideo.storage.files import read_yaml, write_text_atomic
from healthvideo.storage.immutable import promote_directory_once
from healthvideo.storage.project_layout import ProjectLayout, resolve_project_layout
from healthvideo.workflows.operations import mutation_lease
from healthvideo.workflows.review import _reviewed_paths

_EXCLUDED_DIRECTORIES = frozenset(
    {".healthvideo", "__pycache__", "cache", "source-cache", "source-documents"}
)
_EXCLUDED_SUFFIXES = frozenset(
    {".tmp", ".safetensors", ".ckpt", ".pt", ".pth", ".onnx", ".gguf"}
    | {".pem", ".key", ".p12", ".pfx"}
)
# Crash-recovery intents replayed by produce, ai-clip and the medical gate: they
# are workflow state, not cache, so they (and workflow/staged-ai-clips) are kept.
_RECOVERY_JOURNALS = frozenset(
    {
        "pending-ai-clip-generation.yaml",
        "pending-chart-binding.yaml",
        "pending-hook-outro.yaml",
    }
)
# v2 medical approvals hash the repository pronunciation profile, not project bytes.
_REPOSITORY_BOUND_KEYS = frozenset({"profiles/pronunciation.vi.yaml"})

Binding = tuple[str, str, Path]


def is_backup_excluded(relative: str) -> bool:
    """Runtime, secret, model, cache, pending and source-fulltext paths never enter a snapshot."""
    parts = relative.casefold().split("/")
    name = parts[-1]
    return (
        any(part in _EXCLUDED_DIRECTORIES or ".superseded-" in part for part in parts)
        or name == ".env"
        or name.startswith(".env.")
        or (name.startswith("pending-") and name not in _RECOVERY_JOURNALS)
        or Path(name).suffix in _EXCLUDED_SUFFIXES
    )


def create_backup(
    project_dir: Path, backup_root: Path, *, backup_id: str, now: datetime
) -> Path:
    """Snapshot authoritative bytes into ``backup_root/backup_id``; never overwrite."""
    destination = backup_root / backup_id
    if destination.exists():
        raise FileExistsError(f"backup already exists: {destination}")
    if not (project_dir / "project.yaml").is_file():
        raise FileNotFoundError(f"project manifest not found: {project_dir}")
    with mutation_lease(project_dir, "backup create"):
        layout = resolve_project_layout(project_dir)
        files = tree_files(project_dir, skip=is_backup_excluded)
        manifest = BackupManifest(
            backup_id=backup_id,
            project_schema_version=layout.schema_version,
            slug=layout.manifest.slug,
            active_revision=_active_revision(layout),
            created_at=now,
            entries=build_entries(
                project_dir, [project_dir.joinpath(*path.split("/")) for path in files]
            ),
        )
        with staging_directory(destination) as staging:
            copy_entries(project_dir, staging, manifest.entries)
            verify_snapshot_tree(staging, manifest.entries)
            validate_project_tree(staging)
            payload = json.dumps(
                manifest.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            write_text_atomic(staging / MANIFEST_NAME, f"{payload}\n")
            promote_directory_once(staging, destination)
    return destination


def restore_backup(snapshot_dir: Path, destination_dir: Path) -> Path:
    """Verify a snapshot completely, then promote a verified copy into a new directory."""
    if destination_dir.exists():
        raise FileExistsError(f"restore destination already exists: {destination_dir}")
    manifest_path = snapshot_dir / MANIFEST_NAME
    if is_link_or_reparse(manifest_path):
        raise ValueError(f"refusing link or reparse point: {MANIFEST_NAME}")
    manifest = BackupManifest.model_validate_json(manifest_path.read_bytes())
    forbidden = [entry.path for entry in manifest.entries if is_backup_excluded(entry.path)]
    if forbidden:
        raise ValueError(f"snapshot contains forbidden entries: {', '.join(forbidden)}")
    verify_snapshot_tree(snapshot_dir, manifest.entries)
    layout = validate_project_tree(snapshot_dir)
    if (layout.schema_version, layout.manifest.slug, _active_revision(layout)) != (
        manifest.project_schema_version,
        manifest.slug,
        manifest.active_revision,
    ):
        raise ValueError("snapshot project identity does not match its backup manifest")
    with staging_directory(destination_dir) as staging:
        copy_entries(snapshot_dir, staging, manifest.entries)
        verify_snapshot_tree(staging, manifest.entries)
        promote_directory_once(staging, destination_dir)
    return destination_dir


def validate_project_tree(project_dir: Path) -> ProjectLayout:
    """Parse the v1/v2 layout and approval records; refuse forbidden or missing bindings.

    Approvals are checked for structure and for the presence of what they bind,
    never for currency: an intact stale approval stays stale and is accepted.
    """
    root = project_dir.resolve()
    layout = resolve_project_layout(root)
    if isinstance(layout.manifest, ProjectManifest):
        bound, referenced = _v1_bindings(root, layout.manifest), []
    else:
        bound, referenced = _v2_bindings(root)
    for path in [*referenced, *(path for _, _, path in bound)]:
        relative = canonical_relative_path(path.relative_to(root).as_posix())
        if is_backup_excluded(relative):
            raise ValueError(
                f"authoritative artifact references forbidden path: {relative}"
            )
    for record, key, path in bound:
        if not path.is_file():
            raise FileNotFoundError(f"approval {record} binds missing artifact: {key}")
    return layout


def _active_revision(layout: ProjectLayout) -> str | None:
    return getattr(layout.manifest, "active_revision", None)


def _inside(root: Path, relative: str) -> Path:
    return root.joinpath(*canonical_relative_path(relative).split("/"))


def _v1_bindings(root: Path, project: ProjectManifest) -> list[Binding]:
    bindings: list[Binding] = []
    for kind in ReviewKind:
        reviewed = _reviewed_paths(root, project, kind)
        for record_path in sorted((root / "reviews").glob(f"{kind.value}-*.yaml")):
            name = record_path.relative_to(root).as_posix()
            record = ReviewRecord.model_validate(read_yaml(record_path))
            if record.kind is not kind:
                raise ValueError(f"approval {name} records gate {record.kind.value}")
            for key in record.artifact_hashes:
                if key in reviewed:
                    path = reviewed[key]
                elif key.startswith("asset:"):
                    path = _inside(root, key.removeprefix("asset:"))
                else:
                    raise FileNotFoundError(
                        f"approval {name} binds an artifact that cannot be located: {key}"
                    )
                bindings.append((name, key, path))
    return bindings


def _v2_bindings(root: Path) -> tuple[list[Binding], list[Path]]:
    bindings: list[Binding] = []
    referenced: list[Path] = []
    revisions = sorted(path for path in (root / "revisions").iterdir() if path.is_dir())
    for revision in revisions:
        asset_manifest = revision / "assets" / "asset-manifest.yaml"
        if asset_manifest.is_file():
            referenced += [
                _inside(revision, asset.path)
                for asset in load_asset_manifest(asset_manifest).assets
            ]
        for kind in GateKind:
            reviews = revision / "reviews"
            for rejection in sorted((reviews / kind.value).glob("*.yaml")):
                _require_kind(
                    GateRejectionRecord.model_validate(read_yaml(rejection)).kind,
                    kind,
                    rejection.relative_to(root).as_posix(),
                )
            approval = reviews / f"{kind.value}-approval.yaml"
            if not approval.is_file():
                continue
            name = approval.relative_to(root).as_posix()
            record = GateApprovalRecord.model_validate(read_yaml(approval))
            _require_kind(record.kind, kind, name)
            bindings += [
                (name, key, _inside(revision, key.removeprefix("asset:")))
                for key in record.artifact_hashes
                if key not in _REPOSITORY_BOUND_KEYS
            ]
    return bindings, referenced


def _require_kind(actual: GateKind, expected: GateKind, name: str) -> None:
    if actual is not expected:
        raise ValueError(f"review record {name} records gate {actual.value}")
