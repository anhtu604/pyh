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
        "brand": {AssetKind.FLOURISH},
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
        "chart": {AssetKind.DATA_CHART},
        "ai_clip": {AssetKind.AI_CLIP},
    }
    resolved_assets: dict[str, Path] = {}
    referenced_roles: dict[str, str] = {}
    referenced_counts: dict[str, int] = {}
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
            if reference.role == "brand" and (
                scene.visual != "brand_outro"
                or record.storyboard_role != "brand"
                or record.semantic
            ):
                raise ValueError(f"Scene {scene.id}: brand logo ownership or classification mismatch")
            if reference.role == "chart" and (
                scene.visual != "chart"
                or not record.semantic
                or record.storyboard_role != "chart"
            ):
                raise ValueError(
                    f"Scene {scene.id}: chart ownership or classification mismatch"
                )
            if reference.role == "ai_clip":
                if scene.visual != "ai_clip" or record.storyboard_role != "ai_clip":
                    raise ValueError(
                        f"Scene {scene.id}: ai_clip ownership or visual mismatch"
                    )
                if record.semantic and (
                    not scene.claim_id
                    or not scene.source_marker
                    or not scene.source_marker.strip()
                ):
                    raise ValueError(
                        f"Scene {scene.id}: semantic ai_clip requires claim_id "
                        "and source_marker"
                    )
                if not record.semantic and (
                    scene.claim_id is not None or scene.source_marker is not None
                ):
                    raise ValueError(
                        f"Scene {scene.id}: decorative ai_clip cannot carry "
                        "claim_id or source_marker"
                    )
            if scene.visual == "brand_outro" and reference.role == "mascot" and (
                record.kind is not AssetKind.MASCOT_REACTION
                or record.semantic
                or record.storyboard_role != "mascot"
            ):
                raise ValueError(f"Scene {scene.id}: outro mascot must be decorative reaction")
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
            referenced_roles[relative.as_posix()] = reference.role
            referenced_counts[relative.as_posix()] = (
                referenced_counts.get(relative.as_posix(), 0) + 1
            )
        if storyboard.visual_budget_profile == "m6_5_v1" and scene.visual == "chart":
            chart_refs = [ref for ref in scene.visual_assets if ref.role == "chart"]
            if len(chart_refs) != 1:
                raise ValueError(
                    f"Scene {scene.id}: M6.5 chart scene requires exactly one chart asset"
                )
        if (
            storyboard.visual_budget_profile == "m6_5_v1"
            and scene.visual == "ai_clip"
        ):
            clip_refs = [ref for ref in scene.visual_assets if ref.role == "ai_clip"]
            if len(clip_refs) != 1:
                raise ValueError(
                    f"Scene {scene.id}: M6.5 ai_clip scene requires exactly one "
                    "ai_clip asset"
                )
    for record in manifest.assets:
        if record.storyboard_role is None:
            continue
        actual_role = referenced_roles.get(record.path)
        if actual_role is None:
            raise ValueError(f"visual asset is not referenced by storyboard: {record.path}")
        if actual_role != record.storyboard_role:
            raise ValueError(
                f"visual asset storyboard role mismatch for {record.path}: "
                f"expected {record.storyboard_role!r}, found {actual_role!r}"
            )
        if record.storyboard_role == "chart" and referenced_counts[record.path] != 1:
            raise ValueError(
                f"chart asset must be referenced by exactly one scene: {record.path}"
            )
        if record.storyboard_role == "ai_clip" and referenced_counts[record.path] != 1:
            raise ValueError(
                "AI clip asset must be referenced by exactly one scene: "
                f"{record.path}"
            )
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
