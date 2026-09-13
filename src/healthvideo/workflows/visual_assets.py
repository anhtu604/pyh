"""Register chart bytes and explicit rights on an unapproved v2 revision."""

import re
import shutil
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp

from healthvideo.domain.asset_manifest import (
    AssetKind,
    AssetManifest,
    AssetRecord,
    load_asset_manifest,
    validate_asset_manifest,
)
from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.license_ledger import (
    LicenseEntry,
    LicenseLedger,
    validate_license_ledger,
)
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import EvidenceHighlight, Storyboard
from healthvideo.storage.files import (
    read_yaml,
    recover_directory_promotion,
    replace_directory_atomic,
    sha256_file,
    write_yaml_atomic,
)
from healthvideo.visuals.charts import render_count_chart
from healthvideo.visuals.highlights import crop_highlight


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
