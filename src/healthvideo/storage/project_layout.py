from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from healthvideo.domain.project_v2 import ProjectManifestV2
from healthvideo.storage.files import read_yaml


@dataclass(frozen=True)
class ProjectLayout:
    project_dir: Path
    artifact_root: Path
    schema_version: Literal["2.0"]
    manifest: ProjectManifestV2


def resolve_project_layout(project_dir: Path) -> ProjectLayout:
    """Validate a v2 manifest and locate its active revision."""
    manifest_data = read_yaml(project_dir / "project.yaml")
    schema_version = manifest_data.get("schema_version")

    if schema_version == "2.0":
        manifest = ProjectManifestV2.model_validate(manifest_data)
        artifact_root = project_dir / "revisions" / manifest.active_revision
        if not artifact_root.is_dir():
            raise FileNotFoundError(f"Active revision does not exist: {artifact_root}")
        return ProjectLayout(
            project_dir=project_dir,
            artifact_root=artifact_root,
            schema_version="2.0",
            manifest=manifest,
        )
    raise ValueError(f"Unsupported project schema version: {schema_version!r}")
