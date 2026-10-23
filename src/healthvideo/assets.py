"""Resolve and fingerprint project-owned evidence assets."""

from pathlib import Path, PurePosixPath

from healthvideo.domain.asset_manifest import AssetKind, AssetManifest
from healthvideo.domain.license_ledger import (
    LicenseLedger,
    validate_crop_license,
    validate_license_ledger,
)
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml, sha256_file


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
    validate_evidence_highlights(revision_root, storyboard, manifest)
    records = {PurePosixPath(record.path).as_posix(): record for record in manifest.assets}
    allowed = {
        "brand": {AssetKind.FLOURISH},
        "mascot": {
            AssetKind.MASCOT_REACTION,
            AssetKind.MASCOT_MEDICAL_ANNOTATION,
        },
        "whiteboard": {
            AssetKind.ILLUSTRATION,
            AssetKind.BACKGROUND,
            AssetKind.TEXTURE,
            AssetKind.FLOURISH,
            AssetKind.TRANSITION,
            AssetKind.MEDICAL_DIAGRAM,
            AssetKind.MEDICAL_TEXT,
        },
        "chart": {AssetKind.DATA_CHART},
    }
    resolved_assets: dict[str, Path] = {}
    referenced_roles: dict[str, str] = {}
    referenced_counts: dict[str, int] = {}
    for scene in storyboard.scenes:
        for label in (*scene.labels, *scene.annotations):
            target = records.get(_relative_posix_path(label.asset_path, scene.id).as_posix())
            if target is not None and target.kind is AssetKind.ILLUSTRATION:
                raise ValueError(
                    f"Scene {scene.id}: AI illustration cannot carry anatomical labels, captions or data: "
                    f"{label.asset_path}; draw text using Remotion or use an anatomical SVG"
                )
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
                if record.kind is AssetKind.ILLUSTRATION:
                    # A reviewed recipe is materialized in produce; never rewrite that manifest.
                    referenced_roles[relative.as_posix()] = reference.role
                    referenced_counts[relative.as_posix()] = referenced_counts.get(relative.as_posix(), 0) + 1
                    continue
                raise FileNotFoundError(f"visual asset is missing: {reference.path}")
            actual = sha256_file(candidate)
            if record.sha256 is not None and actual != record.sha256:
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
    return resolved_assets


def validate_evidence_highlights(
    revision_root: Path, storyboard: Storyboard, manifest: AssetManifest,
) -> None:
    """Only registered raster excerpts may be presented as source images.

    Originality remains an explicit operator declaration in the license ledger;
    technical checks bind that declaration to a source, crop and exact PNG bytes.
    """
    highlights = [scene for scene in storyboard.scenes if scene.evidence_highlight is not None]
    if not highlights:
        return
    from PIL import Image

    records = {asset.path: asset for asset in manifest.assets}
    rights_path = revision_root / "assets/license-ledger.yaml"
    if not rights_path.is_file():
        raise ValueError("evidence_highlight requires source crop in license ledger; use source_card for interpretation")
    rights = LicenseLedger.model_validate(read_yaml(rights_path))
    # Draft validation uses a temporary sibling directory; its name is not a revision ID.
    revisions = {asset.revision for asset in manifest.assets}
    if len(revisions) != 1:
        raise ValueError("source crop assets must belong to one revision")
    validate_license_ledger(manifest, rights, next(iter(revisions)))
    covered = {entry.path for entry in rights.entries}
    for scene in highlights:
        highlight = scene.evidence_highlight
        assert highlight is not None
        relative = _relative_posix_path(highlight.image, scene.id)
        asset = records.get(relative.as_posix())
        if (
            relative.suffix.lower() not in {".png", ".jpg", ".jpeg"}
            or highlight.source_id is None or highlight.page is None
            or highlight.crop_x is None or highlight.crop_y is None
            or highlight.crop_width is None or highlight.crop_height is None
            or highlight.crop_pixel_width is None or highlight.crop_pixel_height is None
            or asset is None or asset.kind is not AssetKind.EVIDENCE_HIGHLIGHT
            or not asset.rights_required or asset.source != highlight.source_id
            or asset.path not in covered
        ):
            raise ValueError(f"Scene {scene.id}: evidence_highlight requires registered source crop provenance; use source_card")
        # Keep the doctor's explicit rights declaration mandatory, while using
        # Europe PMC's actual license to reject unsupported OA-only reuse.
        from healthvideo.domain.evidence import SourceRecord
        from healthvideo.evidence.fulltext import load_fulltext

        ledger_path = revision_root / "evidence/ledger.yaml"
        ledger = read_yaml(ledger_path) if ledger_path.is_file() else {}
        source = next((SourceRecord.model_validate(row) for row in ledger.get("records", [])
                       if row["id"] == highlight.source_id), None)
        fulltext = load_fulltext(highlight.source_id, source) if source else None
        entry = next(entry for entry in rights.entries if entry.path == asset.path)
        source_license = (
            fulltext.license if fulltext and fulltext.origin == "open_access"
            else entry.source_license
        )
        validate_crop_license(entry.license, source_license)
        root = revision_root.resolve()
        path = root.joinpath(*relative.parts).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Scene {scene.id}: evidence asset must remain inside the project")
        if sha256_file(path) != asset.sha256:
            raise ValueError(f"Scene {scene.id}: source crop sha256 mismatch")
        with Image.open(path) as image:
            if image.format not in {"PNG", "JPEG"} or image.size != (
                highlight.crop_pixel_width, highlight.crop_pixel_height
            ) or getattr(image, "n_frames", 1) != 1:
                raise ValueError(f"Scene {scene.id}: source crop image dimensions or format mismatch")
            image.verify()


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
