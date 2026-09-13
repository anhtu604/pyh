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
from healthvideo.storage.files import (
    read_yaml,
    recover_directory_promotion,
    replace_directory_atomic,
    sha256_file,
    write_yaml_atomic,
)
from healthvideo.visuals.charts import render_count_chart


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
