"""Transactional creation of revisioned schema-2.0 projects."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from tempfile import mkdtemp

from healthvideo.domain.author import AuthorBrief
from healthvideo.domain.project_v2 import ProjectManifestV2
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout

REVISION_DIRECTORIES = (
    "topic",
    "author",
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
    del now
    manifest = ProjectManifestV2(slug=slug)
    project_dir = root / manifest.slug
    root.mkdir(parents=True, exist_ok=True)
    if project_dir.exists():
        raise FileExistsError(f"Project already exists: {project_dir}")

    staging_dir = Path(mkdtemp(prefix=f".{manifest.slug}.tmp-", dir=root))
    revision_root = staging_dir / "revisions" / manifest.active_revision
    try:
        for directory in REVISION_DIRECTORIES:
            (revision_root / directory).mkdir(parents=True)

        brief = AuthorBrief(title=title)
        write_yaml_atomic(
            revision_root / "author" / "brief.yaml", brief.model_dump(mode="json")
        )
        write_yaml_atomic(staging_dir / "project.yaml", manifest.model_dump(mode="json"))
        _validate_staging(staging_dir, manifest, brief)
        if project_dir.exists():
            raise FileExistsError(f"Project already exists: {project_dir}")
        staging_dir.rename(project_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    return project_dir


def _validate_staging(
    staging_dir: Path, manifest: ProjectManifestV2, brief: AuthorBrief
) -> None:
    """Re-read the two persisted documents before publishing their directory."""
    loaded_manifest = ProjectManifestV2.model_validate(read_yaml(staging_dir / "project.yaml"))
    if loaded_manifest != manifest:
        raise ValueError("staged project manifest does not match the requested project")
    loaded_brief = AuthorBrief.model_validate(
        read_yaml(
            staging_dir
            / "revisions"
            / manifest.active_revision
            / "author"
            / "brief.yaml"
        )
    )
    if loaded_brief != brief:
        raise ValueError("staged author brief does not match the requested title")
    resolve_project_layout(staging_dir)
