import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from healthvideo.domain.asset_manifest import (
    AssetIntegrityError,
    AssetKind,
    load_asset_manifest,
    validate_asset_manifest,
)
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.license_ledger import LicenseLedger, validate_license_ledger
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.workflows import visual_assets
from healthvideo.workflows.gate_review import (
    approve_gate,
    hash_reviewed_artifacts,
    medical_reviewed_paths,
)
from healthvideo.workflows.visual_assets import (
    create_evidence_chart,
    create_evidence_highlight_asset,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(Path("tests/fixtures/golden-project-v2"), root)
    data = read_yaml(root / "project.yaml")
    data["state"] = "draft_ready"
    write_yaml_atomic(root / "project.yaml", data)
    ledger_path = root / "revisions/001/evidence/ledger.yaml"
    ledger = read_yaml(ledger_path)
    ledger["claims"][0]["chart_data"] = [
        {
            "id": "bp-count",
            "source_id": "R01",
            "label": "Mẫu thử tổng hợp",
            "value": 12,
            "denominator": 40,
            "unit": "người",
            "ci_low": 10,
            "ci_high": 15,
        }
    ]
    write_yaml_atomic(ledger_path, ledger)
    return root


def make_chart(project: Path, **changes: str) -> Path:
    args = {
        "claim_id": "C01",
        "datum_id": "bp-count",
        "asset_name": "chart-count",
        "license": "synthetic_test_only",
        "rights_basis": "fixture nội bộ",
        "creator": "repository_fixture",
    }
    args.update(changes)
    return create_evidence_chart(project, **args)


def test_register_chart_and_rights_without_state_change(project: Path) -> None:
    before = (project / "project.yaml").read_bytes()
    chart = make_chart(project)
    revision = project / "revisions/001"
    manifest = load_asset_manifest(revision / "assets/asset-manifest.yaml")
    record = next(a for a in manifest.assets if a.path == "assets/chart-count.svg")
    assert record.kind is AssetKind.DATA_CHART and record.semantic
    assert record.sha256 == sha256_file(chart)
    rights = LicenseLedger.model_validate(
        read_yaml(revision / "assets/license-ledger.yaml")
    )
    match = next(e for e in rights.entries if e.path == record.path)
    assert (match.sha256, match.revision, match.source) == (record.sha256, "001", "R01")
    assert (project / "project.yaml").read_bytes() == before
    assert f"asset:{record.path}" in medical_reviewed_paths(revision)
    assert "assets/license-ledger.yaml" in medical_reviewed_paths(revision)
    before_hashes = hash_reviewed_artifacts(medical_reviewed_paths(revision))
    rights_path = revision / "assets/license-ledger.yaml"
    rights_path.write_text(
        rights_path.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8"
    )
    # Comments are not semantic YAML; an actual rights change must invalidate the gate.
    rights_data = read_yaml(rights_path)
    rights_data["entries"][0]["rights_basis"] = "different claimed basis"
    write_yaml_atomic(rights_path, rights_data)
    assert hash_reviewed_artifacts(medical_reviewed_paths(revision)) != before_hashes
    rights_data["entries"][0]["license"] = "different license"
    with pytest.raises(ValueError, match="license"):
        validate_license_ledger(
            manifest, LicenseLedger.model_validate(rights_data), "001"
        )
    validate_asset_manifest(revision, manifest)
    chart.write_text("tampered", encoding="utf-8")
    with pytest.raises(AssetIntegrityError):
        validate_asset_manifest(revision, manifest)


def test_refuses_overwrite_or_missing_source_and_rights(project: Path) -> None:
    chart = make_chart(project)
    with pytest.raises(FileExistsError):
        make_chart(project)
    assert chart.is_file()
    for changes in (
        {"claim_id": "missing"},
        {"datum_id": "missing"},
        {"license": " "},
        {"rights_basis": " "},
    ):
        with pytest.raises(ValueError):
            make_chart(project, asset_name="other", **changes)
    assert not (chart.parent / "other.svg").exists()


def test_rejects_unbound_source_and_unsafe_name(project: Path) -> None:
    ledger_path = project / "revisions/001/evidence/ledger.yaml"
    ledger = read_yaml(ledger_path)
    ledger["claims"][0]["chart_data"][0]["source_id"] = "not-in-claim"
    write_yaml_atomic(ledger_path, ledger)
    with pytest.raises(ValueError, match="source"):
        make_chart(project)
    with pytest.raises(ValueError, match="name"):
        make_chart(project, asset_name="../../escape")
    assert not (project / "revisions/001/assets/chart-count.svg").exists()


def test_v1_project_is_untouched(tmp_path: Path) -> None:
    root = tmp_path / "v1"
    shutil.copytree(Path("tests/fixtures/golden-project"), root)
    before = (root / "project.yaml").read_bytes()
    with pytest.raises(ValueError):
        make_chart(root)
    assert (root / "project.yaml").read_bytes() == before
    assert not (root / "assets/chart-count.svg").exists()


def test_refuses_post_approval_mutation(project: Path) -> None:
    data = read_yaml(project / "project.yaml")
    data["state"] = "medically_approved"
    write_yaml_atomic(project / "project.yaml", data)
    with pytest.raises(ValueError, match="medical"):
        make_chart(project)


def test_medical_gate_refuses_chart_without_license_ledger(project: Path) -> None:
    make_chart(project)
    revision = project / "revisions/001"
    (revision / "assets/license-ledger.yaml").unlink()
    data = read_yaml(project / "project.yaml")
    data["state"] = "awaiting_medical_review"
    write_yaml_atomic(project / "project.yaml", data)
    with pytest.raises(FileNotFoundError, match="license ledger"):
        approve_gate(
            project, GateKind.MEDICAL, reviewer="test doctor", now=datetime.now(UTC)
        )
    assert not (revision / "reviews/medical-approval.yaml").exists()


def test_recovers_interrupted_assets_promotion_before_reading(project: Path) -> None:
    revision = project / "revisions/001"
    asset_dir = revision / "assets"
    backup = revision / ".assets.superseded-interrupted"
    asset_dir.rename(backup)
    chart = make_chart(project)
    assert chart.is_file()
    assert (asset_dir / "evidence-r01.svg").is_file()
    assert not backup.exists()


def test_ambiguous_backups_remain_blocking(project: Path) -> None:
    revision = project / "revisions/001"
    (revision / "assets").rename(revision / ".assets.superseded-one")
    (revision / ".assets.superseded-two").mkdir()
    with pytest.raises(FileExistsError, match="multiple"):
        make_chart(project)
    assert (revision / ".assets.superseded-one").exists()
    assert (revision / ".assets.superseded-two").exists()


def test_tampered_existing_license_ledger_refuses_new_chart(project: Path) -> None:
    chart = make_chart(project)
    asset_dir = chart.parent
    manifest_path = asset_dir / "asset-manifest.yaml"
    before = manifest_path.read_bytes()
    rights_path = asset_dir / "license-ledger.yaml"
    rights = read_yaml(rights_path)
    rights["entries"][0]["license"] = "tampered"
    write_yaml_atomic(rights_path, rights)
    with pytest.raises(ValueError, match="license"):
        make_chart(project, asset_name="chart-two")
    assert manifest_path.read_bytes() == before
    assert not (asset_dir / "chart-two.svg").exists()


def test_register_cropped_highlight_with_source_page_rights(
    project: Path, tmp_path: Path
) -> None:
    revision = project / "revisions/001"
    storyboard_path = revision / "storyboard/storyboard.yaml"
    storyboard = read_yaml(storyboard_path)
    highlight = storyboard["scenes"][2]["evidence_highlight"]
    highlight.update(
        {
            "image": "assets/paper-excerpt.png",
            "source_id": "R01",
            "page": 2,
            "x": 0.4,
            "y": 0.4,
            "width": 0.1,
            "height": 0.1,
        }
    )
    write_yaml_atomic(storyboard_path, storyboard)
    source = tmp_path / "full-page.png"
    Image.new("RGB", (100, 100), "white").save(source)
    before = (project / "project.yaml").read_bytes()
    output = create_evidence_highlight_asset(
        project,
        scene_id="S03",
        page_image=source,
        asset_name="paper-excerpt",
        license="synthetic_test_only",
        rights_basis="fixture nội bộ",
        creator="repository_fixture",
    )
    with Image.open(output) as cropped:
        assert cropped.width < 50 and cropped.height < 50
    manifest = load_asset_manifest(revision / "assets/asset-manifest.yaml")
    record = next(a for a in manifest.assets if a.path == "assets/paper-excerpt.png")
    assert record.kind is AssetKind.EVIDENCE_HIGHLIGHT and record.semantic
    assert record.source == "R01" and record.sha256 == sha256_file(output)
    rights = LicenseLedger.model_validate(
        read_yaml(revision / "assets/license-ledger.yaml")
    )
    assert any(
        e.path == record.path and e.sha256 == record.sha256 for e in rights.entries
    )
    assert str(source) not in (revision / "assets/asset-manifest.yaml").read_text(
        encoding="utf-8"
    )
    assert (project / "project.yaml").read_bytes() == before


def test_highlight_rejects_oversized_excerpt(project: Path, tmp_path: Path) -> None:
    revision = project / "revisions/001"
    storyboard_path = revision / "storyboard/storyboard.yaml"
    storyboard = read_yaml(storyboard_path)
    highlight = storyboard["scenes"][2]["evidence_highlight"]
    highlight.update(
        {"image": "assets/paper-excerpt.png", "source_id": "R01", "page": 2}
    )
    write_yaml_atomic(storyboard_path, storyboard)
    source = tmp_path / "full-page.png"
    Image.new("RGB", (100, 100), "white").save(source)
    with pytest.raises(ValueError, match="crop|excerpt"):
        create_evidence_highlight_asset(
            project,
            scene_id="S03",
            page_image=source,
            asset_name="paper-excerpt",
            license="synthetic_test_only",
            rights_basis="fixture nội bộ",
            creator="repository_fixture",
        )
    assert not (revision / "assets/paper-excerpt.png").exists()


def test_highlight_source_marker_and_rights_are_required(
    project: Path, tmp_path: Path
) -> None:
    revision = project / "revisions/001"
    storyboard_path = revision / "storyboard/storyboard.yaml"
    storyboard = read_yaml(storyboard_path)
    highlight = storyboard["scenes"][2]["evidence_highlight"]
    highlight.update(
        {
            "image": "assets/paper-excerpt.png",
            "source_id": "R01",
            "page": 2,
            "x": 0.4,
            "y": 0.4,
            "width": 0.1,
            "height": 0.1,
        }
    )
    source = tmp_path / "full-page.png"
    Image.new("RGB", (100, 100), "white").save(source)
    args = {
        "scene_id": "S03",
        "page_image": source,
        "asset_name": "paper-excerpt",
        "license": "synthetic_test_only",
        "rights_basis": "fixture nội bộ",
        "creator": "repository_fixture",
    }
    storyboard["scenes"][2]["source_marker"] = "[2]"
    write_yaml_atomic(storyboard_path, storyboard)
    with pytest.raises(ValueError, match="marker"):
        create_evidence_highlight_asset(project, **args)
    storyboard["scenes"][2]["source_marker"] = "[1]"
    highlight["source_id"] = "unknown"
    write_yaml_atomic(storyboard_path, storyboard)
    with pytest.raises(ValueError, match="source"):
        create_evidence_highlight_asset(project, **args)
    highlight["source_id"] = "R01"
    write_yaml_atomic(storyboard_path, storyboard)
    with pytest.raises(ValueError, match="explicit"):
        create_evidence_highlight_asset(project, **(args | {"rights_basis": " "}))
    assert not (revision / "assets/paper-excerpt.png").exists()


def test_registered_highlight_requires_rights_at_medical_gate(
    project: Path, tmp_path: Path
) -> None:
    revision = project / "revisions/001"
    storyboard_path = revision / "storyboard/storyboard.yaml"
    storyboard = read_yaml(storyboard_path)
    storyboard["scenes"][2]["evidence_highlight"].update(
        {
            "image": "assets/paper-excerpt.png",
            "source_id": "R01",
            "page": 2,
            "x": 0.4,
            "y": 0.4,
            "width": 0.1,
            "height": 0.1,
        }
    )
    write_yaml_atomic(storyboard_path, storyboard)
    source = tmp_path / "full-page.png"
    Image.new("RGB", (100, 100), "white").save(source)
    output = create_evidence_highlight_asset(
        project,
        scene_id="S03",
        page_image=source,
        asset_name="paper-excerpt",
        license="synthetic_test_only",
        rights_basis="fixture nội bộ",
        creator="repository_fixture",
    )
    updated = read_yaml(storyboard_path)["scenes"][2]["evidence_highlight"]
    assert updated["crop_x"] < updated["x"]
    assert updated["crop_width"] < 0.5
    with Image.open(output) as cropped:
        assert (updated["crop_pixel_width"], updated["crop_pixel_height"]) == cropped.size
    manifest = load_asset_manifest(revision / "assets/asset-manifest.yaml")
    assert next(
        a for a in manifest.assets if a.path == "assets/paper-excerpt.png"
    ).rights_required
    (revision / "assets/license-ledger.yaml").unlink()
    state = read_yaml(project / "project.yaml")
    state["state"] = "awaiting_medical_review"
    write_yaml_atomic(project / "project.yaml", state)
    with pytest.raises(FileNotFoundError, match="license ledger"):
        approve_gate(
            project, GateKind.MEDICAL, reviewer="test doctor", now=datetime.now(UTC)
        )
    output.write_bytes(b"changed")
    with pytest.raises(AssetIntegrityError):
        validate_asset_manifest(revision, manifest)


def test_highlight_retry_repairs_storyboard_after_asset_promotion(
    project: Path, tmp_path: Path
) -> None:
    revision = project / "revisions/001"
    storyboard_path = revision / "storyboard/storyboard.yaml"
    storyboard = read_yaml(storyboard_path)
    storyboard["scenes"][2]["evidence_highlight"].update(
        {
            "image": "assets/paper-excerpt.png",
            "source_id": "R01",
            "page": 2,
            "x": 0.4,
            "y": 0.4,
            "width": 0.1,
            "height": 0.1,
        }
    )
    write_yaml_atomic(storyboard_path, storyboard)
    source = tmp_path / "full-page.png"
    Image.new("RGB", (100, 100), "white").save(source)
    args = {
        "scene_id": "S03",
        "page_image": source,
        "asset_name": "paper-excerpt",
        "license": "synthetic_test_only",
        "rights_basis": "fixture nội bộ",
        "creator": "repository_fixture",
    }
    output = create_evidence_highlight_asset(project, **args)
    crop_hash = sha256_file(output)
    write_yaml_atomic(
        storyboard_path, storyboard
    )  # interrupted before storyboard write
    with pytest.raises(ValueError, match="crop provenance"):
        state = read_yaml(project / "project.yaml")
        state["state"] = "awaiting_medical_review"
        write_yaml_atomic(project / "project.yaml", state)
        approve_gate(
            project, GateKind.MEDICAL, reviewer="test doctor", now=datetime.now(UTC)
        )
    assert create_evidence_highlight_asset(project, **args) == output
    assert sha256_file(output) == crop_hash
    assert read_yaml(storyboard_path)["scenes"][2]["evidence_highlight"]["crop_x"] < 0.4


def test_highlight_retry_after_promotion_failure_is_gate_safe(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    revision = project / "revisions/001"
    storyboard_path = revision / "storyboard/storyboard.yaml"
    storyboard = read_yaml(storyboard_path)
    storyboard["scenes"][2]["evidence_highlight"].update(
        {
            "image": "assets/paper-excerpt.png",
            "source_id": "R01",
            "page": 2,
            "x": 0.4,
            "y": 0.4,
            "width": 0.1,
            "height": 0.1,
        }
    )
    write_yaml_atomic(storyboard_path, storyboard)
    source = tmp_path / "full-page.png"
    Image.new("RGB", (100, 100), "white").save(source)
    args = {
        "scene_id": "S03",
        "page_image": source,
        "asset_name": "paper-excerpt",
        "license": "synthetic_test_only",
        "rights_basis": "fixture nội bộ",
        "creator": "repository_fixture",
    }
    real_promote = visual_assets.replace_directory_atomic

    def fail_once(*_args: object) -> None:
        raise OSError("simulated promotion failure")

    monkeypatch.setattr(visual_assets, "replace_directory_atomic", fail_once)
    with pytest.raises(OSError, match="simulated"):
        create_evidence_highlight_asset(project, **args)
    assert read_yaml(storyboard_path)["scenes"][2]["evidence_highlight"]["crop_x"] < 0.4
    assert not (revision / "assets/paper-excerpt.png").exists()
    state = read_yaml(project / "project.yaml")
    state["state"] = "awaiting_medical_review"
    write_yaml_atomic(project / "project.yaml", state)
    with pytest.raises(ValueError, match="crop provenance"):
        approve_gate(
            project, GateKind.MEDICAL, reviewer="test doctor", now=datetime.now(UTC)
        )
    monkeypatch.setattr(visual_assets, "replace_directory_atomic", real_promote)
    output = create_evidence_highlight_asset(project, **args)
    assert output.is_file()
    rights = LicenseLedger.model_validate(
        read_yaml(revision / "assets/license-ledger.yaml")
    )
    assert len([e for e in rights.entries if e.path == "assets/paper-excerpt.png"]) == 1
