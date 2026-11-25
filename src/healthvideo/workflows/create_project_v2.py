"""Transactional creation of revisioned schema-2.0 projects."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from tempfile import mkdtemp

from healthvideo.domain.project_v2 import ProjectManifestV2
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout

REVISION_DIRECTORIES = (
    "topic",
    "evidence",
    "script",
    "storyboard",
    "handoffs",
    "reviews",
    "audio",
    "assets",
    "renders",
    "publish",
)


def create_project_v2(root: Path, slug: str, title: str, *, now: datetime) -> Path:
    """Create a schema-2.0 project and publish its initial revision once."""
    # Keep the creation API stable; the selected topic card supplies the title.
    del now, title
    manifest = ProjectManifestV2(slug=slug, content_profile="explain_first_v1")
    project_dir = root / manifest.slug
    root.mkdir(parents=True, exist_ok=True)
    if project_dir.exists():
        raise FileExistsError(f"Project already exists: {project_dir}")

    staging_dir = Path(mkdtemp(prefix=f".{manifest.slug}.tmp-", dir=root))
    revision_root = staging_dir / "revisions" / manifest.active_revision
    try:
        for directory in REVISION_DIRECTORIES:
            (revision_root / directory).mkdir(parents=True)

        write_yaml_atomic(staging_dir / "project.yaml", manifest.model_dump(mode="json"))
        # Legacy roots remain readable; configured factories pin only accepted versions.
        from healthvideo.workflows.factory_standards import (
            STANDARDS_FILE,
            STYLE_SPEC_FILE,
            pin_standards,
        )
        if (
            root.name == 'projects'
            or (root.parent / STANDARDS_FILE).exists()
            or (root.parent / STYLE_SPEC_FILE).exists()
        ):
            # R5 is the current standard; a new project has no approvals to supersede,
            # so it pins R5 here instead of needing the PIN-gated adopt-r5 later.
            pin_standards(root.parent, staging_dir, quality_profile="r5_v1")
        _validate_staging(staging_dir, manifest)
        if project_dir.exists():
            raise FileExistsError(f"Project already exists: {project_dir}")
        staging_dir.rename(project_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    return project_dir


def _validate_staging(
    staging_dir: Path, manifest: ProjectManifestV2
) -> None:
    """Re-read the persisted manifest before publishing their directory."""
    loaded_manifest = ProjectManifestV2.model_validate(read_yaml(staging_dir / "project.yaml"))
    if loaded_manifest != manifest:
        raise ValueError("staged project manifest does not match the requested project")
    resolve_project_layout(staging_dir)
