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
from healthvideo.domain.brand import MascotPose
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.license_ledger import LicenseLedger, validate_license_ledger
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.visuals.whiteboard import WhiteboardPayload, WhiteboardTemplate
from healthvideo.workflows import visual_assets
from healthvideo.workflows.gate_review import (
    approve_gate,
    hash_reviewed_artifacts,
    medical_reviewed_paths,
)
from healthvideo.workflows.visual_assets import (
    bind_chart_asset,
    create_evidence_chart,
    create_evidence_highlight_asset,
    create_mascot_annotation_asset,
    create_mascot_reaction_asset,
    create_whiteboard_asset,
    recover_chart_asset_binding,
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


def test_register_mascot_reaction_and_semantic_annotation(project: Path) -> None:
    revision = project / "revisions/001"
    before = (project / "project.yaml").read_bytes()
    reaction = create_mascot_reaction_asset(
        project, scene_id="S01", asset_name="phy-welcome", pose=MascotPose.WELCOME
    )
    annotation = create_mascot_annotation_asset(
        project,
        scene_id="S01",
        asset_name="phy-note",
        pose=MascotPose.EXPLAIN,
        annotation="Ăn mặn có thể làm huyết áp tăng.",
        claim_id="C01",
        source_id="R01",
        source_marker="[1]",
    )
    manifest = load_asset_manifest(revision / "assets/asset-manifest.yaml")
    records = {item.path: item for item in manifest.assets}
    assert records["assets/phy-welcome.svg"].kind is AssetKind.MASCOT_REACTION
    assert records["assets/phy-welcome.svg"].semantic is False
    assert records["assets/phy-welcome.svg"].storyboard_role == "mascot"
    assert records["assets/phy-welcome.svg"].classification_reason == (
        "Fixed mascot reaction with no content fields."
    )
    assert records["assets/phy-note.svg"].kind is AssetKind.MASCOT_MEDICAL_ANNOTATION
    assert records["assets/phy-note.svg"].semantic is True
    assert records["assets/phy-note.svg"].classification_reason == (
        "Mascot carries source-bound medical annotation."
    )
    assert reaction.is_file() and annotation.is_file()
    storyboard = Storyboard.model_validate(read_yaml(revision / "storyboard/storyboard.yaml"))
    assert [ref.path for ref in storyboard.scenes[0].visual_assets] == [
        "assets/phy-welcome.svg",
        "assets/phy-note.svg",
    ]
    assert (project / "project.yaml").read_bytes() == before


def test_mascot_annotation_rejects_invalid_binding(project: Path) -> None:
    with pytest.raises(ValueError, match="claim|source|marker"):
        create_mascot_annotation_asset(
            project,
            scene_id="S01",
            asset_name="bad-note",
            pose=MascotPose.EXPLAIN,
            annotation="Không được đăng ký.",
            claim_id="missing",
            source_id="R01",
            source_marker="[1]",
        )
    assert not (project / "revisions/001/assets/bad-note.svg").exists()


def test_register_decorative_and_semantic_whiteboards(project: Path) -> None:
    revision = project / "revisions/001"
    decorative = create_whiteboard_asset(
        project,
        scene_id="S01",
        asset_name="phy-connector",
        template=WhiteboardTemplate.CONNECTOR,
        payload=WhiteboardPayload(),
        semantic=False,
    )
    semantic = create_whiteboard_asset(
        project,
        scene_id="S01",
        asset_name="phy-callout",
        template=WhiteboardTemplate.CALLOUT,
        payload=WhiteboardPayload(labels=("Giảm muối",)),
        semantic=True,
        claim_id="C01",
        source_id="R01",
        source_marker="[1]",
    )
    manifest = load_asset_manifest(revision / "assets/asset-manifest.yaml")
    records = {item.path: item for item in manifest.assets}
    assert records["assets/phy-connector.svg"].kind is AssetKind.FLOURISH
    assert records["assets/phy-connector.svg"].semantic is False
    assert records["assets/phy-connector.svg"].classification_reason == (
        "Fixed decorative whiteboard geometry."
    )
    assert records["assets/phy-callout.svg"].kind is AssetKind.MEDICAL_TEXT
    assert records["assets/phy-callout.svg"].semantic is True
    assert records["assets/phy-callout.svg"].classification_reason == (
        "Source-bound semantic whiteboard content."
    )
    assert decorative.is_file() and semantic.is_file()


@pytest.mark.parametrize(
    ("semantic", "binding"),
    [
        (True, {}),
        (False, {"claim_id": "C01", "source_id": "R01", "source_marker": "[1]"}),
    ],
)
def test_whiteboard_requires_explicit_semantic_classification(
    project: Path, semantic: bool, binding: dict[str, str]
) -> None:
    with pytest.raises(ValueError, match="semantic|decorative"):
        create_whiteboard_asset(
            project,
            scene_id="S01",
            asset_name="bad-whiteboard",
            template=WhiteboardTemplate.CALLOUT,
            payload=WhiteboardPayload(labels=("Không đăng ký",)),
            semantic=semantic,
            **binding,
        )


def test_mascot_retry_after_asset_promotion_failure_is_gate_safe(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    revision = project / "revisions/001"
    original = visual_assets.replace_directory_atomic

    def fail_once(*args, **kwargs):
        raise OSError("synthetic interruption")

    monkeypatch.setattr(visual_assets, "replace_directory_atomic", fail_once)
    with pytest.raises(OSError, match="interruption"):
        create_mascot_reaction_asset(
            project,
            scene_id="S01",
            asset_name="phy-welcome",
            pose=MascotPose.WELCOME,
        )
    state = read_yaml(project / "project.yaml")
    state["state"] = "awaiting_medical_review"
    write_yaml_atomic(project / "project.yaml", state)
    with pytest.raises(ValueError, match="not declared"):
        approve_gate(
            project, GateKind.MEDICAL, reviewer="test doctor", now=datetime.now(UTC)
        )
    monkeypatch.setattr(visual_assets, "replace_directory_atomic", original)
    output = create_mascot_reaction_asset(
        project,
        scene_id="S01",
        asset_name="phy-welcome",
        pose=MascotPose.WELCOME,
    )
    assert output.is_file()
    storyboard = Storyboard.model_validate(
        read_yaml(revision / "storyboard/storyboard.yaml")
    )
    assert sum(
        ref.path == "assets/phy-welcome.svg"
        for ref in storyboard.scenes[0].visual_assets
    ) == 1


@pytest.mark.parametrize("asset_kind", ["reaction", "annotation", "whiteboard"])
def test_medical_gate_rejects_registered_visual_after_ref_is_removed(
    project: Path, asset_kind: str
) -> None:
    if asset_kind == "reaction":
        create_mascot_reaction_asset(
            project, scene_id="S01", asset_name="orphan", pose=MascotPose.WELCOME
        )
    elif asset_kind == "annotation":
        create_mascot_annotation_asset(
            project,
            scene_id="S01",
            asset_name="orphan",
            pose=MascotPose.EXPLAIN,
            annotation="Giảm muối.",
            claim_id="C01",
            source_id="R01",
            source_marker="[1]",
        )
    else:
        create_whiteboard_asset(
            project,
            scene_id="S01",
            asset_name="orphan",
            template=WhiteboardTemplate.CONNECTOR,
            payload=WhiteboardPayload(),
            semantic=False,
        )
    storyboard_path = project / "revisions/001/storyboard/storyboard.yaml"
    storyboard = read_yaml(storyboard_path)
    storyboard["scenes"][0]["visual_assets"] = []
    write_yaml_atomic(storyboard_path, storyboard)
    state = read_yaml(project / "project.yaml")
    state["state"] = "awaiting_medical_review"
    write_yaml_atomic(project / "project.yaml", state)

    with pytest.raises(ValueError, match="not referenced"):
        approve_gate(
            project, GateKind.MEDICAL, reviewer="test doctor", now=datetime.now(UTC)
        )


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


def test_bind_existing_chart_to_chart_scene_and_identical_retry(project: Path) -> None:
    chart = make_chart(project)
    revision = project / "revisions/001"

    bind_chart_asset(project, scene_id="S04", asset_path="assets/chart-count.svg")
    first_storyboard = (revision / "storyboard/storyboard.yaml").read_bytes()
    first_manifest = (revision / "assets/asset-manifest.yaml").read_bytes()
    bind_chart_asset(project, scene_id="S04", asset_path="assets/chart-count.svg")

    board = Storyboard.model_validate(
        read_yaml(revision / "storyboard/storyboard.yaml")
    )
    scene = next(item for item in board.scenes if item.id == "S04")
    assert scene.visual_assets == (
        visual_assets.VisualAssetRef(path="assets/chart-count.svg", role="chart"),
    )
    record = next(
        item
        for item in load_asset_manifest(revision / "assets/asset-manifest.yaml").assets
        if item.path == "assets/chart-count.svg"
    )
    assert record.storyboard_role == "chart"
    assert chart.is_file()
    assert (revision / "storyboard/storyboard.yaml").read_bytes() == first_storyboard
    assert (revision / "assets/asset-manifest.yaml").read_bytes() == first_manifest


def test_chart_binding_recovers_manifest_first_interruption(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_chart(project)
    revision = project / "revisions/001"
    original = visual_assets._write_chart_storyboard

    def interrupt(*args, **kwargs):
        raise OSError("synthetic chart binding interruption")

    monkeypatch.setattr(visual_assets, "_write_chart_storyboard", interrupt)
    with pytest.raises(OSError, match="interruption"):
        bind_chart_asset(
            project, scene_id="S04", asset_path="assets/chart-count.svg"
        )
    record = next(
        item
        for item in load_asset_manifest(revision / "assets/asset-manifest.yaml").assets
        if item.path == "assets/chart-count.svg"
    )
    assert record.storyboard_role == "chart"
    assert not any(
        ref.role == "chart"
        for scene in Storyboard.model_validate(
            read_yaml(revision / "storyboard/storyboard.yaml")
        ).scenes
        for ref in scene.visual_assets
    )
    assert (revision / "workflow/pending-chart-binding.yaml").is_file()

    monkeypatch.setattr(visual_assets, "_write_chart_storyboard", original)
    recover_chart_asset_binding(project)

    board = Storyboard.model_validate(
        read_yaml(revision / "storyboard/storyboard.yaml")
    )
    assert next(item for item in board.scenes if item.id == "S04").visual_assets[0].role == (
        "chart"
    )
    assert not (revision / "workflow/pending-chart-binding.yaml").exists()


def test_chart_binding_pending_intent_refuses_unrelated_edit(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_chart(project)
    revision = project / "revisions/001"

    def interrupt(*args, **kwargs):
        raise OSError("synthetic chart binding interruption")

    monkeypatch.setattr(visual_assets, "_write_chart_storyboard", interrupt)
    with pytest.raises(OSError):
        bind_chart_asset(
            project, scene_id="S04", asset_path="assets/chart-count.svg"
        )
    board_path = revision / "storyboard/storyboard.yaml"
    data = read_yaml(board_path)
    data["title"] = "operator edit"
    write_yaml_atomic(board_path, data)

    with pytest.raises(ValueError, match="conflict"):
        recover_chart_asset_binding(project)
    assert (revision / "workflow/pending-chart-binding.yaml").is_file()


def test_medical_gate_recovers_pending_chart_binding_before_validation(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_chart(project)
    original = visual_assets._write_chart_storyboard

    def interrupt(*args, **kwargs):
        raise OSError("synthetic chart binding interruption")

    monkeypatch.setattr(visual_assets, "_write_chart_storyboard", interrupt)
    with pytest.raises(OSError):
        bind_chart_asset(
            project, scene_id="S04", asset_path="assets/chart-count.svg"
        )
    monkeypatch.setattr(visual_assets, "_write_chart_storyboard", original)
    state = read_yaml(project / "project.yaml")
    state["state"] = "awaiting_medical_review"
    write_yaml_atomic(project / "project.yaml", state)

    approve_gate(
        project, GateKind.MEDICAL, reviewer="test doctor", now=datetime.now(UTC)
    )

    revision = project / "revisions/001"
    assert not (revision / "workflow/pending-chart-binding.yaml").exists()
    assert (revision / "reviews/medical-approval.yaml").is_file()


def test_chart_binding_refuses_changed_target_path_state_kind_and_rights(
    project: Path,
) -> None:
    make_chart(project)
    revision = project / "revisions/001"
    with pytest.raises(ValueError, match="chart scene"):
        bind_chart_asset(project, scene_id="S01", asset_path="assets/chart-count.svg")
    with pytest.raises(ValueError, match="relative POSIX"):
        bind_chart_asset(project, scene_id="S04", asset_path="../chart-count.svg")

    manifest_path = revision / "assets/asset-manifest.yaml"
    original_manifest = read_yaml(manifest_path)
    wrong_kind = read_yaml(manifest_path)
    chart_record = next(
        item for item in wrong_kind["assets"] if item["path"] == "assets/chart-count.svg"
    )
    chart_record["kind"] = "medical_text"
    write_yaml_atomic(manifest_path, wrong_kind)
    with pytest.raises(ValueError, match="DATA_CHART"):
        bind_chart_asset(project, scene_id="S04", asset_path="assets/chart-count.svg")
    write_yaml_atomic(manifest_path, original_manifest)

    rights_path = revision / "assets/license-ledger.yaml"
    rights = read_yaml(rights_path)
    rights["entries"][0]["rights_basis"] = ""
    write_yaml_atomic(rights_path, rights)
    with pytest.raises(ValueError, match="rights|source"):
        bind_chart_asset(project, scene_id="S04", asset_path="assets/chart-count.svg")


def test_chart_binding_refuses_post_approval_and_different_scene_retry(
    project: Path,
) -> None:
    make_chart(project)
    bind_chart_asset(project, scene_id="S04", asset_path="assets/chart-count.svg")
    revision = project / "revisions/001"
    board_path = revision / "storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["scenes"][2]["visual"] = "chart"
    write_yaml_atomic(board_path, board)
    with pytest.raises(ValueError, match="owned|referenced|different"):
        bind_chart_asset(project, scene_id="S03", asset_path="assets/chart-count.svg")

    state = read_yaml(project / "project.yaml")
    state["state"] = "medically_approved"
    write_yaml_atomic(project / "project.yaml", state)
    with pytest.raises(ValueError, match="pre-medical"):
        bind_chart_asset(project, scene_id="S04", asset_path="assets/chart-count.svg")


def test_chart_binding_allows_distinct_owned_charts_in_distinct_scenes(
    project: Path,
) -> None:
    make_chart(project)
    make_chart(project, asset_name="chart-two")
    board_path = project / "revisions/001/storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["scenes"][2]["visual"] = "chart"
    write_yaml_atomic(board_path, board)

    bind_chart_asset(project, scene_id="S04", asset_path="assets/chart-count.svg")
    bind_chart_asset(project, scene_id="S03", asset_path="assets/chart-two.svg")

    parsed = Storyboard.model_validate(read_yaml(board_path))
    assert {
        (scene.id, ref.path)
        for scene in parsed.scenes
        for ref in scene.visual_assets
        if ref.role == "chart"
    } == {
        ("S03", "assets/chart-two.svg"),
        ("S04", "assets/chart-count.svg"),
    }


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
