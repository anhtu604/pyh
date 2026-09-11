"""Copy-on-write creation of immutable workflow revisions."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from healthvideo.domain.project_v2 import ProjectManifestV2
from healthvideo.domain.revision import RevisionRecord
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.immutable import promote_directory_once, write_yaml_once

REVISION_SOURCE_DIRS = (
    "topic",
    "author",
    "evidence",
    "script",
    "storyboard",
    "assets",
)


def create_revision(project_dir: Path, reason: str, *, now: datetime) -> str:
    """Copy the active revision into a new immutable revision and switch to it.

    Only ``topic/``, ``author/``, ``evidence/``, ``script/``, ``storyboard/``
    and ``assets/`` are carried forward; audit trails such as ``handoffs/``,
    ``reviews/``, ``audio/``, ``renders/`` and ``publish/`` belong to a
    specific past run and are never copied into a new revision.

    The new revision is built in a staging directory that is a sibling of the
    final path, validated in place, then promoted with a single rename that
    never replaces an existing revision. Only after that promotion succeeds
    is ``project.yaml``'s ``active_revision`` updated. If anything fails
    before promotion, exactly the staging directory created here is removed
    and both ``project.yaml`` and the parent revision are left byte-unchanged.
    """
    manifest_path = project_dir / "project.yaml"
    manifest_data = read_yaml(manifest_path)
    schema_version = manifest_data.get("schema_version")
    if schema_version != "2.0":
        raise ValueError(
            f"Project schema {schema_version!r} cannot create a revision; "
            "run `healthvideo project migrate` first."
        )
    manifest = ProjectManifestV2.model_validate(manifest_data)

    parent_revision = manifest.active_revision
    new_revision = f"{int(parent_revision) + 1:03d}"
    revisions_dir = project_dir / "revisions"
    parent_root = revisions_dir / parent_revision
    destination = revisions_dir / new_revision
    staging_dir = revisions_dir / f".{new_revision}-stage-{uuid4()}"

    record = RevisionRecord(
        revision=new_revision,
        parent_revision=parent_revision,
        reason=reason,
        created_at=now,
    )

    staging_dir.mkdir(parents=True)
    try:
        _copy_revision_sources(parent_root, staging_dir)
        write_yaml_once(staging_dir / "workflow.yaml", record.model_dump(mode="json"))
        _validate_staged_revision(parent_root, staging_dir, record)
        promote_directory_once(staging_dir, destination)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    updated_manifest = dict(manifest_data)
    updated_manifest["active_revision"] = new_revision
    write_yaml_atomic(manifest_path, updated_manifest)
    return new_revision


def _copy_revision_sources(parent_root: Path, staging_dir: Path) -> None:
    for name in REVISION_SOURCE_DIRS:
        source = parent_root / name
        if source.is_dir():
            shutil.copytree(source, staging_dir / name)


def _validate_staged_revision(
    parent_root: Path, staging_dir: Path, record: RevisionRecord
) -> None:
    """Re-read every path the transaction just wrote before it is promoted."""
    loaded = RevisionRecord.model_validate(read_yaml(staging_dir / "workflow.yaml"))
    if loaded != record:
        raise ValueError(
            "staged workflow.yaml does not match the intended revision record"
        )
    for name in REVISION_SOURCE_DIRS:
        source = parent_root / name
        if not source.is_dir():
            continue
        staged = staging_dir / name
        if not staged.is_dir():
            raise ValueError(f"staged revision is missing copied directory: {name}")
        for source_file in source.rglob("*"):
            if not source_file.is_file():
                continue
            relative = source_file.relative_to(source)
            staged_file = staged / relative
            if not staged_file.is_file():
                raise ValueError(
                    f"staged revision is missing copied file: "
                    f"{name}/{relative.as_posix()}"
                )
            if staged_file.read_bytes() != source_file.read_bytes():
                raise ValueError(
                    "staged revision copy does not match source bytes: "
                    f"{name}/{relative.as_posix()}"
                )
