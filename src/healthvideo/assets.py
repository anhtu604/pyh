"""Resolve and fingerprint project-owned evidence assets."""

from pathlib import Path, PurePosixPath

from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import sha256_file


def referenced_evidence_assets(
    project_dir: Path, storyboard: Storyboard
) -> dict[str, Path]:
    """Return safe project-relative evidence asset paths keyed by POSIX path."""
    project_root = project_dir.resolve()
    assets: dict[str, Path] = {}
    for scene in storyboard.scenes:
        highlight = scene.evidence_highlight
        if highlight is None:
            continue
        relative = _relative_posix_path(highlight.image, scene.id)
        candidate = project_root.joinpath(*relative.parts)
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(project_root):
            raise ValueError(
                f"Scene {scene.id}: evidence asset must remain inside the project"
            )
        assets[relative.as_posix()] = candidate
    return assets


def evidence_asset_hashes(project_dir: Path, storyboard: Storyboard) -> dict[str, str]:
    """Hash every referenced evidence asset, refusing missing files."""
    paths = referenced_evidence_assets(project_dir, storyboard)
    missing = [relative for relative, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Referenced evidence assets are missing: " + ", ".join(sorted(missing))
        )
    return {relative: sha256_file(path) for relative, path in paths.items()}


def _relative_posix_path(value: str, scene_id: str) -> PurePosixPath:
    path = PurePosixPath(value)
    parts = path.parts
    if (
        not value
        or not parts
        or value in {".", "./"}
        or "\\" in value
        or path.is_absolute()
        or ".." in parts
        or ":" in parts[0]
    ):
        raise ValueError(
            f"Scene {scene_id}: evidence asset path must be relative POSIX"
        )
    return path
