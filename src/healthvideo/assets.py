"""Resolve and fingerprint project-owned evidence assets."""

from pathlib import Path, PurePosixPath

from healthvideo.domain.asset_manifest import AssetKind, AssetManifest
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


def referenced_storyboard_assets(
    revision_root: Path, storyboard: Storyboard, manifest: AssetManifest
) -> dict[str, Path]:
    """Resolve declared scene visuals and verify kind, location, and all bytes."""
    root = revision_root.resolve()
    records = {record.path: record for record in manifest.assets}
    allowed = {
        "mascot": {
            AssetKind.MASCOT_REACTION,
            AssetKind.MASCOT_MEDICAL_ANNOTATION,
        },
        "whiteboard": {
            AssetKind.BACKGROUND,
            AssetKind.TEXTURE,
            AssetKind.FLOURISH,
            AssetKind.TRANSITION,
            AssetKind.MEDICAL_DIAGRAM,
            AssetKind.MEDICAL_TEXT,
        },
    }
    resolved_assets: dict[str, Path] = {}
    for scene in storyboard.scenes:
        for reference in scene.visual_assets:
            relative = _relative_posix_path(reference.path, scene.id)
            record = records.get(relative.as_posix())
            if record is None:
                raise ValueError(
                    f"Scene {scene.id}: visual asset is not declared: {reference.path}"
                )
            if record.kind not in allowed[reference.role]:
                raise ValueError(
                    f"Scene {scene.id}: visual role {reference.role!r} does not match "
                    f"asset kind {record.kind.value!r}"
                )
            candidate = root.joinpath(*relative.parts)
            resolved = candidate.resolve(strict=False)
            if not resolved.is_relative_to(root):
                raise ValueError(f"Scene {scene.id}: visual asset escapes revision")
            if not candidate.is_file():
                raise FileNotFoundError(f"visual asset is missing: {reference.path}")
            actual = sha256_file(candidate)
            if actual != record.sha256:
                raise ValueError(
                    f"visual asset sha256 mismatch for {reference.path}: "
                    f"expected {record.sha256}, found {actual}"
                )
            resolved_assets[relative.as_posix()] = candidate
    return resolved_assets


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
