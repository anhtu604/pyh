"""Register chart bytes and explicit rights on an unapproved v2 revision."""

import re
import shutil
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp
from typing import Literal

from healthvideo.domain.asset_manifest import (
    AssetKind,
    AssetManifest,
    AssetRecord,
    _posix_relative_path,
    load_asset_manifest,
    validate_asset_manifest,
)
from healthvideo.domain.brand import LogoVariant, MascotPose, load_brand_profile
from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.license_ledger import (
    LicenseEntry,
    LicenseLedger,
    validate_license_ledger,
)
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import EvidenceHighlight, Storyboard, VisualAssetRef
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    recover_directory_promotion,
    replace_directory_atomic,
    sha256_file,
    write_yaml_atomic,
)
from healthvideo.visuals.brand import render_phy_logo
from healthvideo.visuals.charts import render_count_chart
from healthvideo.visuals.highlights import crop_highlight
from healthvideo.visuals.mascot import render_mascot, render_mascot_annotation
from healthvideo.visuals.whiteboard import (
    WhiteboardPayload,
    WhiteboardTemplate,
    render_whiteboard,
)

BRAND_PROFILE_PATH = Path(__file__).resolve().parents[3] / "profiles/brand.vi.yaml"
CHART_BINDING_INTENT = "workflow/pending-chart-binding.yaml"


def create_evidence_chart(
    project_dir: Path,
    *,
    claim_id: str,
    datum_id: str,
    asset_name: str,
    license: str,
    rights_basis: str,
    creator: str,
) -> Path:
    """Create one chart from an already recorded datum; never change project state."""
    project = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    if project.state not in {
        WorkflowState.DRAFT_READY,
        WorkflowState.AWAITING_MEDICAL_REVIEW,
    }:
        raise ValueError("chart registration requires pre-medical-review draft")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", asset_name):
        raise ValueError("asset name must be a safe public alias")
    revision = project_dir / "revisions" / project.active_revision
    if (revision / "reviews/medical-approval.yaml").exists():
        raise ValueError("medical approval already exists for this revision")
    ledger = read_yaml(revision / "evidence/ledger.yaml")
    claims = [EvidenceClaim.model_validate(item) for item in ledger.get("claims", [])]
    claim = next((item for item in claims if item.id == claim_id), None)
    if claim is None:
        raise ValueError("chart claim is not in evidence ledger")
    datum = next((item for item in claim.chart_data if item.id == datum_id), None)
    if datum is None:
        raise ValueError("chart datum is not in evidence ledger claim")
    sources = {
        SourceRecord.model_validate(item).id for item in ledger.get("records", [])
    }
    if datum.source_id not in sources or datum.source_id not in claim.sources:
        raise ValueError("chart datum source is not bound to the claim and ledger")

    path = f"assets/{asset_name}.svg"
    asset_dir = revision / "assets"
    recover_directory_promotion(asset_dir)
    if (revision / path).exists():
        raise FileExistsError(f"chart asset already exists: {path}")
    manifest = load_asset_manifest(asset_dir / "asset-manifest.yaml")
    validate_asset_manifest(revision, manifest)
    if any(record.path == path for record in manifest.assets):
        raise FileExistsError(f"chart asset already registered: {path}")
    rights_path = asset_dir / "license-ledger.yaml"
    rights = (
        LicenseLedger.model_validate(read_yaml(rights_path))
        if rights_path.exists()
        else LicenseLedger()
    )
    if rights_path.exists():
        validate_license_ledger(manifest, rights, project.active_revision)
    if any(entry.path == path for entry in rights.entries):
        raise FileExistsError(f"chart rights already registered: {path}")

    # Validate rights before touching disk; these strings are supplied, never inferred.
    chart_bytes = render_count_chart(datum)
    chart_hash = sha256(chart_bytes).hexdigest()
    record = AssetRecord(
        path=path,
        kind=AssetKind.DATA_CHART,
        semantic=True,
        classification_reason="Chart displays a source-bound medical count.",
        sha256=chart_hash,
        source=datum.source_id,
        license=license,
        creator=creator,
        revision=project.active_revision,
    )
    rights_entry = LicenseEntry(
        path=path,
        source=datum.source_id,
        creator=creator,
        license=license,
        rights_basis=rights_basis,
        revision=project.active_revision,
        sha256=chart_hash,
    )
    updated_manifest = AssetManifest(assets=(*manifest.assets, record))
    updated_rights = LicenseLedger(entries=(*rights.entries, rights_entry))
    validate_license_ledger(updated_manifest, updated_rights, project.active_revision)

    staged = Path(mkdtemp(prefix=".assets-chart-", dir=revision))
    try:
        shutil.copytree(asset_dir, staged, dirs_exist_ok=True)
        (staged / f"{asset_name}.svg").write_bytes(chart_bytes)
        write_yaml_atomic(
            staged / "asset-manifest.yaml", updated_manifest.model_dump(mode="json")
        )
        write_yaml_atomic(
            staged / "license-ledger.yaml", updated_rights.model_dump(mode="json")
        )
        if sha256_file(staged / f"{asset_name}.svg") != chart_hash:
            raise ValueError("staged chart hash mismatch")
        replace_directory_atomic(staged, asset_dir)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return asset_dir / f"{asset_name}.svg"


def bind_chart_asset(
    project_dir: Path, *, scene_id: str, asset_path: str
) -> None:
    """Bind an existing declared M6.1 chart to one storyboard chart scene."""
    recover_chart_asset_binding(project_dir)
    project = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    if project.state not in {
        WorkflowState.DRAFT_READY,
        WorkflowState.AWAITING_MEDICAL_REVIEW,
    }:
        raise ValueError("chart binding requires a pre-medical-review draft")
    revision = project_dir / "revisions" / project.active_revision
    if (revision / "reviews/medical-approval.yaml").exists():
        raise ValueError("chart binding refuses a medically approved revision")
    _posix_relative_path(asset_path)
    storyboard_path = revision / "storyboard/storyboard.yaml"
    old_storyboard = Storyboard.model_validate(read_yaml(storyboard_path))
    scene = next((item for item in old_storyboard.scenes if item.id == scene_id), None)
    if scene is None or scene.visual != "chart":
        raise ValueError("chart binding target must be an existing chart scene")

    asset_dir = revision / "assets"
    recover_directory_promotion(asset_dir)
    old_manifest = load_asset_manifest(asset_dir / "asset-manifest.yaml")
    validate_asset_manifest(revision, old_manifest)
    matches = [item for item in old_manifest.assets if item.path == asset_path]
    if len(matches) != 1 or matches[0].kind is not AssetKind.DATA_CHART:
        raise ValueError("chart binding requires exactly one declared DATA_CHART")
    record = matches[0]
    if not record.semantic:
        raise ValueError("chart binding requires semantic DATA_CHART")
    rights_path = asset_dir / "license-ledger.yaml"
    if not rights_path.is_file():
        raise ValueError("chart binding requires matching source and usage rights")
    rights = LicenseLedger.model_validate(read_yaml(rights_path))
    validate_license_ledger(old_manifest, rights, project.active_revision)

    asset_refs = [
        (item.id, ref)
        for item in old_storyboard.scenes
        for ref in item.visual_assets
        if ref.path == asset_path
    ]
    scene_chart_refs = [ref for ref in scene.visual_assets if ref.role == "chart"]
    expected_ref = VisualAssetRef(path=asset_path, role="chart")
    if record.storyboard_role == "chart":
        if asset_refs == [(scene_id, expected_ref)] and scene_chart_refs == [
            expected_ref
        ]:
            return
        raise ValueError("chart asset is owned or referenced by a different scene")
    if record.storyboard_role is not None or asset_refs or scene_chart_refs:
        raise ValueError("chart asset has conflicting ownership or reference")

    desired_record = record.model_copy(update={"storyboard_role": "chart"})
    desired_manifest = AssetManifest(
        assets=tuple(
            desired_record if item.path == asset_path else item
            for item in old_manifest.assets
        )
    )
    desired_storyboard = _desired_chart_storyboard(
        old_storyboard, scene_id=scene_id, asset_path=asset_path
    )
    intent = {
        "schema_version": "1.0",
        "scene_id": scene_id,
        "asset_path": asset_path,
        "rights_hash": canonical_json_hash(rights.model_dump(mode="json")),
        "old_manifest": old_manifest.model_dump(mode="json"),
        "desired_manifest": desired_manifest.model_dump(mode="json"),
        "old_storyboard": old_storyboard.model_dump(mode="json"),
        "desired_storyboard": desired_storyboard.model_dump(mode="json"),
        "old_manifest_hash": canonical_json_hash(old_manifest.model_dump(mode="json")),
        "desired_manifest_hash": canonical_json_hash(
            desired_manifest.model_dump(mode="json")
        ),
        "old_storyboard_hash": canonical_json_hash(
            old_storyboard.model_dump(mode="json")
        ),
        "desired_storyboard_hash": canonical_json_hash(
            desired_storyboard.model_dump(mode="json")
        ),
    }
    intent_path = revision / CHART_BINDING_INTENT
    write_yaml_atomic(intent_path, intent)
    recover_chart_asset_binding(project_dir)


def recover_chart_asset_binding(project_dir: Path) -> None:
    """Converge one recognized chart-binding intent or refuse conflicting edits."""
    project_data = read_yaml(project_dir / "project.yaml")
    if project_data.get("schema_version") != "2.0":
        return
    project = ProjectManifestV2.model_validate(project_data)
    revision = project_dir / "revisions" / project.active_revision
    intent_path = revision / CHART_BINDING_INTENT
    if not intent_path.is_file():
        return
    if project.state not in {
        WorkflowState.DRAFT_READY,
        WorkflowState.AWAITING_MEDICAL_REVIEW,
    } or (revision / "reviews/medical-approval.yaml").exists():
        raise ValueError("pending chart binding cannot recover after medical review")

    intent = read_yaml(intent_path)
    old_manifest = AssetManifest.model_validate(intent.get("old_manifest"))
    desired_manifest = AssetManifest.model_validate(intent.get("desired_manifest"))
    old_storyboard = Storyboard.model_validate(intent.get("old_storyboard"))
    desired_storyboard = Storyboard.model_validate(intent.get("desired_storyboard"))
    scene_id = str(intent.get("scene_id", ""))
    asset_path = str(intent.get("asset_path", ""))
    expected_storyboard = _desired_chart_storyboard(
        old_storyboard, scene_id=scene_id, asset_path=asset_path
    )
    old_record = next(
        (item for item in old_manifest.assets if item.path == asset_path), None
    )
    desired_record = next(
        (item for item in desired_manifest.assets if item.path == asset_path), None
    )
    if (
        intent.get("schema_version") != "1.0"
        or old_record is None
        or old_record.kind is not AssetKind.DATA_CHART
        or not old_record.semantic
        or old_record.storyboard_role is not None
        or desired_record != old_record.model_copy(update={"storyboard_role": "chart"})
        or desired_storyboard != expected_storyboard
        or intent.get("old_manifest_hash")
        != canonical_json_hash(old_manifest.model_dump(mode="json"))
        or intent.get("desired_manifest_hash")
        != canonical_json_hash(desired_manifest.model_dump(mode="json"))
        or intent.get("old_storyboard_hash")
        != canonical_json_hash(old_storyboard.model_dump(mode="json"))
        or intent.get("desired_storyboard_hash")
        != canonical_json_hash(desired_storyboard.model_dump(mode="json"))
    ):
        raise ValueError("pending chart binding intent is invalid or conflicting")

    asset_dir = revision / "assets"
    recover_directory_promotion(asset_dir)
    current_manifest = load_asset_manifest(asset_dir / "asset-manifest.yaml")
    current_storyboard = Storyboard.model_validate(
        read_yaml(revision / "storyboard/storyboard.yaml")
    )
    rights_path = asset_dir / "license-ledger.yaml"
    if not rights_path.is_file():
        raise ValueError("pending chart binding rights conflict")
    rights = LicenseLedger.model_validate(read_yaml(rights_path))
    if intent.get("rights_hash") != canonical_json_hash(rights.model_dump(mode="json")):
        raise ValueError("pending chart binding rights conflict")
    validate_license_ledger(current_manifest, rights, project.active_revision)
    validate_asset_manifest(revision, current_manifest)

    current_manifest_hash = canonical_json_hash(current_manifest.model_dump(mode="json"))
    current_storyboard_hash = canonical_json_hash(
        current_storyboard.model_dump(mode="json")
    )
    old_manifest_hash = intent["old_manifest_hash"]
    desired_manifest_hash = intent["desired_manifest_hash"]
    old_storyboard_hash = intent["old_storyboard_hash"]
    desired_storyboard_hash = intent["desired_storyboard_hash"]
    if (
        current_manifest_hash == old_manifest_hash
        and current_storyboard_hash == desired_storyboard_hash
    ):
        raise ValueError("pending chart binding conflict: storyboard promoted first")
    if current_manifest_hash == old_manifest_hash and current_storyboard_hash == old_storyboard_hash:
        _promote_chart_manifest(revision, desired_manifest)
        current_manifest_hash = desired_manifest_hash
    if (
        current_manifest_hash == desired_manifest_hash
        and current_storyboard_hash == old_storyboard_hash
    ):
        _write_chart_storyboard(
            revision / "storyboard/storyboard.yaml", desired_storyboard
        )
        current_storyboard_hash = desired_storyboard_hash
    if not (
        current_manifest_hash == desired_manifest_hash
        and current_storyboard_hash == desired_storyboard_hash
    ):
        raise ValueError("pending chart binding conflict with unrelated edits")
    intent_path.unlink()


def _desired_chart_storyboard(
    storyboard: Storyboard, *, scene_id: str, asset_path: str
) -> Storyboard:
    data = storyboard.model_dump(mode="json")
    scene = next((item for item in data["scenes"] if item["id"] == scene_id), None)
    if scene is None or scene["visual"] != "chart":
        raise ValueError("pending chart binding target is not a chart scene")
    refs = scene.setdefault("visual_assets", [])
    if any(ref["path"] == asset_path or ref["role"] == "chart" for ref in refs):
        raise ValueError("pending chart binding target has conflicting visual assets")
    refs.append(VisualAssetRef(path=asset_path, role="chart").model_dump(mode="json"))
    return Storyboard.model_validate(data)


def _promote_chart_manifest(revision: Path, manifest: AssetManifest) -> None:
    asset_dir = revision / "assets"
    staged = Path(mkdtemp(prefix=".assets-chart-bind-", dir=revision))
    try:
        shutil.copytree(asset_dir, staged, dirs_exist_ok=True)
        write_yaml_atomic(
            staged / "asset-manifest.yaml", manifest.model_dump(mode="json")
        )
        validate_asset_manifest(revision, manifest)
        replace_directory_atomic(staged, asset_dir)
    finally:
        if staged.exists():
            shutil.rmtree(staged)


def _write_chart_storyboard(path: Path, storyboard: Storyboard) -> None:
    write_yaml_atomic(path, storyboard.model_dump(mode="json"))


def create_evidence_highlight_asset(
    project_dir: Path,
    *,
    scene_id: str,
    page_image: Path,
    asset_name: str,
    license: str,
    rights_basis: str,
    creator: str,
) -> Path:
    """Register only a bounded excerpt; input page remains outside the project."""
    project = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    if project.state not in {
        WorkflowState.DRAFT_READY,
        WorkflowState.AWAITING_MEDICAL_REVIEW,
    }:
        raise ValueError("highlight registration requires pre-medical-review draft")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", asset_name):
        raise ValueError("asset name must be a safe public alias")
    if page_image.resolve().is_relative_to(project_dir.resolve()):
        raise ValueError("full page image must remain outside the project")
    revision = project_dir / "revisions" / project.active_revision
    if (revision / "reviews/medical-approval.yaml").exists():
        raise ValueError("medical approval already exists for this revision")
    storyboard = Storyboard.model_validate(
        read_yaml(revision / "storyboard/storyboard.yaml")
    )
    scene = next((item for item in storyboard.scenes if item.id == scene_id), None)
    if (
        scene is None
        or scene.visual != "evidence_highlight"
        or scene.evidence_highlight is None
    ):
        raise ValueError("scene must be an evidence highlight")
    highlight = scene.evidence_highlight
    path = f"assets/{asset_name}.png"
    if highlight.image != path or highlight.source_id is None or highlight.page is None:
        raise ValueError("scene highlight needs matching crop path, source_id and page")
    if len(highlight.quote) > 500:
        raise ValueError("excerpt quote must be short")
    ledger = read_yaml(revision / "evidence/ledger.yaml")
    claims = [EvidenceClaim.model_validate(item) for item in ledger.get("claims", [])]
    claim = next((item for item in claims if item.id == scene.claim_id), None)
    sources = {
        SourceRecord.model_validate(item).id for item in ledger.get("records", [])
    }
    if (
        claim is None
        or highlight.source_id not in sources
        or highlight.source_id not in claim.sources
    ):
        raise ValueError("highlight source is not bound to claim and ledger")
    # Package citation contract maps one marker to all sources on a claim.
    # A singular paper crop is unambiguous only when that mapping has one source.
    if len(claim.sources) != 1:
        raise ValueError("highlight marker must resolve to one source")
    script = Script.model_validate(read_yaml(revision / "script/script.yaml"))
    if (
        not scene.source_marker
        or not re.fullmatch(r"\[[1-9][0-9]*\]", scene.source_marker)
        or not any(
            line.claim_id == scene.claim_id
            and line.source_marker == scene.source_marker
            for line in script.lines
        )
    ):
        raise ValueError("highlight marker has no script claim/source mapping")

    asset_dir = revision / "assets"
    recover_directory_promotion(asset_dir)
    manifest = load_asset_manifest(asset_dir / "asset-manifest.yaml")
    validate_asset_manifest(revision, manifest)
    rights_path = asset_dir / "license-ledger.yaml"
    rights = (
        LicenseLedger.model_validate(read_yaml(rights_path))
        if rights_path.exists()
        else LicenseLedger()
    )
    if rights_path.exists():
        validate_license_ledger(manifest, rights, project.active_revision)
    crop_bytes, crop_rect = crop_highlight(page_image, highlight)
    EvidenceHighlight.model_validate(
        highlight.model_copy(
            update=dict(
                zip(
                    (
                        "crop_x",
                        "crop_y",
                        "crop_width",
                        "crop_height",
                        "crop_pixel_width",
                        "crop_pixel_height",
                    ),
                    crop_rect,
                    strict=True,
                )
            )
        ).model_dump()
    )
    crop_hash = sha256(crop_bytes).hexdigest()
    existing_record = next(
        (item for item in manifest.assets if item.path == path), None
    )
    existing_rights = next((item for item in rights.entries if item.path == path), None)
    if (
        existing_record is not None
        or existing_rights is not None
        or (revision / path).exists()
    ):
        if highlight.crop_x is not None:
            raise FileExistsError(f"highlight asset already registered: {path}")
        if (
            existing_record is None
            or existing_rights is None
            or existing_record.kind is not AssetKind.EVIDENCE_HIGHLIGHT
            or not existing_record.rights_required
            or existing_record.sha256 != crop_hash
            or existing_record.source != highlight.source_id
            or existing_record.license != license
            or existing_record.creator != creator
            or existing_rights.rights_basis != rights_basis
            or not (revision / path).is_file()
        ):
            raise FileExistsError(
                f"highlight asset already exists with different provenance: {path}"
            )
        _write_highlight_crop_metadata(revision, scene_id, highlight, crop_rect)
        return asset_dir / f"{asset_name}.png"
    record = AssetRecord(
        path=path,
        kind=AssetKind.EVIDENCE_HIGHLIGHT,
        semantic=True,
        classification_reason="Cropped, source-bound paper excerpt.",
        sha256=crop_hash,
        source=highlight.source_id,
        license=license,
        creator=creator,
        revision=project.active_revision,
        rights_required=True,
    )
    entry = LicenseEntry(
        path=path,
        source=highlight.source_id,
        creator=creator,
        license=license,
        rights_basis=rights_basis,
        revision=project.active_revision,
        sha256=crop_hash,
    )
    updated_manifest = AssetManifest(assets=(*manifest.assets, record))
    updated_rights = LicenseLedger(entries=(*rights.entries, entry))
    validate_license_ledger(updated_manifest, updated_rights, project.active_revision)
    staged = Path(mkdtemp(prefix=".assets-highlight-", dir=revision))
    try:
        shutil.copytree(asset_dir, staged, dirs_exist_ok=True)
        (staged / f"{asset_name}.png").write_bytes(crop_bytes)
        write_yaml_atomic(
            staged / "asset-manifest.yaml", updated_manifest.model_dump(mode="json")
        )
        write_yaml_atomic(
            staged / "license-ledger.yaml", updated_rights.model_dump(mode="json")
        )
        if sha256_file(staged / f"{asset_name}.png") != crop_hash:
            raise ValueError("staged highlight hash mismatch")
        _write_highlight_crop_metadata(revision, scene_id, highlight, crop_rect)
        replace_directory_atomic(staged, asset_dir)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return asset_dir / f"{asset_name}.png"


def _write_highlight_crop_metadata(
    revision: Path,
    scene_id: str,
    highlight: EvidenceHighlight,
    crop_rect: tuple[float, float, float, float, int, int],
) -> None:
    updated = highlight.model_copy(
        update=dict(
            zip(
                (
                    "crop_x",
                    "crop_y",
                    "crop_width",
                    "crop_height",
                    "crop_pixel_width",
                    "crop_pixel_height",
                ),
                crop_rect,
                strict=True,
            )
        )
    )
    type(highlight).model_validate(updated.model_dump())
    storyboard_path = revision / "storyboard/storyboard.yaml"
    storyboard_data = read_yaml(storyboard_path)
    for scene_data in storyboard_data["scenes"]:
        if scene_data["id"] == scene_id:
            scene_data["evidence_highlight"].update(
                dict(
                    zip(
                        (
                            "crop_x",
                            "crop_y",
                            "crop_width",
                            "crop_height",
                            "crop_pixel_width",
                            "crop_pixel_height",
                        ),
                        crop_rect,
                        strict=True,
                    )
                )
            )
            break
    write_yaml_atomic(storyboard_path, storyboard_data)


def create_mascot_reaction_asset(
    project_dir: Path,
    *,
    scene_id: str,
    asset_name: str,
    pose: MascotPose,
) -> Path:
    """Create a declared decorative PHY guide pose without content inputs."""
    brand = load_brand_profile(BRAND_PROFILE_PATH)
    return _register_generated_svg(
        project_dir,
        scene_id=scene_id,
        asset_name=asset_name,
        svg_bytes=render_mascot(brand, pose),
        kind=AssetKind.MASCOT_REACTION,
        semantic=False,
        pose=pose,
        source="built_in:phy-mascot",
        creator=brand.assets.creator,
        license=brand.assets.license,
        rights_basis=brand.assets.license,
        role="mascot",
        classification_reason="Fixed mascot reaction with no content fields.",
    )


def create_brand_logo_asset(
    project_dir: Path, *, scene_id: str, asset_name: str, variant: LogoVariant
) -> Path:
    """Register a fixed decorative PHY logo on the approved outro scene path."""
    project = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    revision = project_dir / "revisions" / project.active_revision
    if (revision / "workflow/pending-hook-outro.yaml").exists():
        raise ValueError("cannot register logo while outro authoring is pending")
    script = Script.model_validate(read_yaml(revision / "script/script.yaml"))
    board = Storyboard.model_validate(read_yaml(revision / "storyboard/storyboard.yaml"))
    scene = next((item for item in board.scenes if item.id == scene_id), None)
    if script.format_profile != "hook_outro_v1" or scene is None or scene.visual != "brand_outro":
        raise ValueError("brand logo requires an M6.4 brand_outro scene")
    brand = load_brand_profile(BRAND_PROFILE_PATH)
    return _register_generated_svg(
        project_dir, scene_id=scene_id, asset_name=asset_name,
        svg_bytes=render_phy_logo(brand, variant), kind=AssetKind.FLOURISH,
        semantic=False, pose=None, source="built_in:phy-logo",
        creator=brand.assets.creator, license=brand.assets.license,
        rights_basis=brand.assets.license, role="brand",
        classification_reason="Fixed decorative PHY logo geometry.",
    )


def create_mascot_annotation_asset(
    project_dir: Path,
    *,
    scene_id: str,
    asset_name: str,
    pose: MascotPose,
    annotation: str,
    claim_id: str,
    source_id: str,
    source_marker: str,
) -> Path:
    """Create a separately classified semantic mascot annotation."""
    _validate_semantic_binding(
        project_dir,
        scene_id=scene_id,
        claim_id=claim_id,
        source_id=source_id,
        source_marker=source_marker,
    )
    brand = load_brand_profile(BRAND_PROFILE_PATH)
    return _register_generated_svg(
        project_dir,
        scene_id=scene_id,
        asset_name=asset_name,
        svg_bytes=render_mascot_annotation(brand, pose, annotation),
        kind=AssetKind.MASCOT_MEDICAL_ANNOTATION,
        semantic=True,
        pose=pose,
        source=source_id,
        creator=brand.assets.creator,
        license=brand.assets.license,
        rights_basis=brand.assets.license,
        role="mascot",
        classification_reason="Mascot carries source-bound medical annotation.",
    )


def create_whiteboard_asset(
    project_dir: Path,
    *,
    scene_id: str,
    asset_name: str,
    template: WhiteboardTemplate,
    payload: WhiteboardPayload,
    semantic: bool,
    claim_id: str | None = None,
    source_id: str | None = None,
    source_marker: str | None = None,
) -> Path:
    """Create a finite whiteboard asset with explicit classification."""
    if semantic:
        if claim_id is None or source_id is None or source_marker is None:
            raise ValueError("semantic whiteboard requires claim, source, and marker")
        _validate_semantic_binding(
            project_dir,
            scene_id=scene_id,
            claim_id=claim_id,
            source_id=source_id,
            source_marker=source_marker,
        )
    elif any(value is not None for value in (claim_id, source_id, source_marker)):
        raise ValueError("decorative whiteboard cannot carry semantic binding")
    brand = load_brand_profile(BRAND_PROFILE_PATH)
    return _register_generated_svg(
        project_dir,
        scene_id=scene_id,
        asset_name=asset_name,
        svg_bytes=render_whiteboard(brand, template, payload),
        kind=AssetKind.MEDICAL_TEXT if semantic else AssetKind.FLOURISH,
        semantic=semantic,
        pose=None,
        source=source_id or "built_in:phy-whiteboard",
        creator=brand.assets.creator,
        license=brand.assets.license,
        rights_basis=brand.assets.license,
        role="whiteboard",
        classification_reason=(
            "Source-bound semantic whiteboard content."
            if semantic
            else "Fixed decorative whiteboard geometry."
        ),
    )


def _validate_semantic_binding(
    project_dir: Path,
    *,
    scene_id: str,
    claim_id: str,
    source_id: str,
    source_marker: str,
) -> None:
    project = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    revision = project_dir / "revisions" / project.active_revision
    storyboard = Storyboard.model_validate(
        read_yaml(revision / "storyboard/storyboard.yaml")
    )
    scene = next((item for item in storyboard.scenes if item.id == scene_id), None)
    ledger = read_yaml(revision / "evidence/ledger.yaml")
    claim = next(
        (
            EvidenceClaim.model_validate(item)
            for item in ledger.get("claims", [])
            if item.get("id") == claim_id
        ),
        None,
    )
    sources = {
        SourceRecord.model_validate(item).id for item in ledger.get("records", [])
    }
    script = Script.model_validate(read_yaml(revision / "script/script.yaml"))
    if (
        scene is None
        or scene.claim_id != claim_id
        or scene.source_marker != source_marker
        or claim is None
        or source_id not in sources
        or source_id not in claim.sources
        or not any(
            line.claim_id == claim_id and line.source_marker == source_marker
            for line in script.lines
        )
    ):
        raise ValueError("mascot annotation claim, source, and marker must be bound")


def _register_generated_svg(
    project_dir: Path,
    *,
    scene_id: str,
    asset_name: str,
    svg_bytes: bytes,
    kind: AssetKind,
    semantic: bool,
    pose: MascotPose | None,
    source: str,
    creator: str,
    license: str,
    rights_basis: str,
    role: Literal["whiteboard", "mascot", "brand"],
    classification_reason: str,
) -> Path:
    project = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    if project.state not in {
        WorkflowState.DRAFT_READY,
        WorkflowState.AWAITING_MEDICAL_REVIEW,
    }:
        raise ValueError("visual registration requires pre-medical-review draft")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", asset_name):
        raise ValueError("asset name must be a safe public alias")
    revision = project_dir / "revisions" / project.active_revision
    if (revision / "reviews/medical-approval.yaml").exists():
        raise ValueError("medical approval already exists for this revision")
    storyboard_path = revision / "storyboard/storyboard.yaml"
    storyboard = Storyboard.model_validate(read_yaml(storyboard_path))
    scene = next((item for item in storyboard.scenes if item.id == scene_id), None)
    if scene is None:
        raise ValueError("visual asset scene does not exist")
    path = f"assets/{asset_name}.svg"
    reference = VisualAssetRef(path=path, role=role, pose=pose)
    existing_ref = next((item for item in scene.visual_assets if item.path == path), None)
    if existing_ref is not None and existing_ref != reference:
        raise FileExistsError(f"visual asset already referenced differently: {path}")

    asset_dir = revision / "assets"
    recover_directory_promotion(asset_dir)
    manifest = load_asset_manifest(asset_dir / "asset-manifest.yaml")
    validate_asset_manifest(revision, manifest)
    rights_path = asset_dir / "license-ledger.yaml"
    rights = (
        LicenseLedger.model_validate(read_yaml(rights_path))
        if rights_path.exists()
        else LicenseLedger()
    )
    if rights_path.exists():
        validate_license_ledger(manifest, rights, project.active_revision)
    digest = sha256(svg_bytes).hexdigest()
    record = AssetRecord(
        path=path,
        kind=kind,
        semantic=semantic,
        classification_reason=classification_reason,
        sha256=digest,
        source=source,
        license=license,
        creator=creator,
        revision=project.active_revision,
        rights_required=True,
        storyboard_role=role,
    )
    entry = LicenseEntry(
        path=path,
        source=source,
        creator=creator,
        license=license,
        rights_basis=rights_basis,
        revision=project.active_revision,
        sha256=digest,
    )
    old_record = next((item for item in manifest.assets if item.path == path), None)
    old_entry = next((item for item in rights.entries if item.path == path), None)
    if old_record is not None or old_entry is not None or (revision / path).exists():
        if (
            old_record != record
            or old_entry != entry
            or not (revision / path).is_file()
            or sha256_file(revision / path) != digest
        ):
            raise FileExistsError(f"visual asset exists with different provenance: {path}")
        if existing_ref is None:
            _append_visual_ref(storyboard_path, scene_id, reference)
        return revision / path

    if existing_ref is None:
        _append_visual_ref(storyboard_path, scene_id, reference)
    updated_manifest = AssetManifest(assets=(*manifest.assets, record))
    updated_rights = LicenseLedger(entries=(*rights.entries, entry))
    validate_license_ledger(updated_manifest, updated_rights, project.active_revision)
    staged = Path(mkdtemp(prefix=".assets-visual-", dir=revision))
    try:
        shutil.copytree(asset_dir, staged, dirs_exist_ok=True)
        (staged / f"{asset_name}.svg").write_bytes(svg_bytes)
        write_yaml_atomic(
            staged / "asset-manifest.yaml", updated_manifest.model_dump(mode="json")
        )
        write_yaml_atomic(
            staged / "license-ledger.yaml", updated_rights.model_dump(mode="json")
        )
        replace_directory_atomic(staged, asset_dir)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return revision / path


def _append_visual_ref(
    storyboard_path: Path, scene_id: str, reference: VisualAssetRef
) -> None:
    data = read_yaml(storyboard_path)
    for scene in data["scenes"]:
        if scene["id"] == scene_id:
            refs = scene.setdefault("visual_assets", [])
            if not any(item["path"] == reference.path for item in refs):
                refs.append(reference.model_dump(mode="json", exclude_none=True))
            break
    Storyboard.model_validate(data)
    write_yaml_atomic(storyboard_path, data)
