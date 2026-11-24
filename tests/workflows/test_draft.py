"""Public draft submission starts from evidence, without direct state edits."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.domain.evidence import EvidenceClaim, EvidenceQuestion, SourceRecord
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.topic import TopicCard
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.create_project_v2 import create_project_v2
from healthvideo.workflows.evidence import build_evidence_ledger, record_question
from healthvideo.workflows.topic import select_topic
from tests.helpers import write_critic_review_fixture, write_explainer_fixture

SOURCE = Path("tests/fixtures/golden-project-v2/revisions/001")
NOW = datetime(2026, 9, 17, tzinfo=UTC)


def _evidence_ready(tmp_path: Path) -> Path:
    project = create_project_v2(tmp_path, "draft-test", "Draft test", now=NOW)
    manifest = read_yaml(project / "project.yaml")
    write_yaml_atomic(project / "project.yaml", manifest)
    select_topic(project, TopicCard.model_validate(read_yaml(SOURCE / "topic/card.yaml")))
    record_question(
        project,
        EvidenceQuestion(
            patient_population="Người trưởng thành",
            intervention="Giảm muối",
            outcome="Huyết áp",
            search_keywords=["sodium blood pressure"],
        ),
    )
    ledger = read_yaml(SOURCE / "evidence/ledger.yaml")
    write_explainer_fixture(project / "revisions/001", ledger["claims"][0]["id"])
    build_evidence_ledger(
        project,
        [EvidenceClaim.model_validate(item) for item in ledger["claims"]],
        [SourceRecord.model_validate(item) for item in ledger["records"]],
    )
    asset_dir = project / "revisions/001/assets"
    for asset in (SOURCE / "assets").iterdir():
        if asset.is_file():
            shutil.copy2(asset, asset_dir)
    return project


def _state(project: Path) -> WorkflowState:
    return ProjectManifestV2.model_validate(read_yaml(project / "project.yaml")).state


def _draft_args(project: Path) -> list[str]:
    return [
        "step", "draft", str(project),
        "--script", str(SOURCE / "script/script.yaml"),
        "--storyboard", str(SOURCE / "storyboard/storyboard.yaml"),
        "--assets", str(SOURCE / "assets/asset-manifest.yaml"),
    ]


def test_cli_submits_draft_then_opens_medical_gate(tmp_path: Path) -> None:
    project = _evidence_ready(tmp_path)
    runner = CliRunner()
    draft = runner.invoke(app, _draft_args(project))
    assert draft.exit_code == 0, draft.stdout
    assert _state(project) is WorkflowState.DRAFT_READY
    assert (project / "revisions/001/script/script.yaml").is_file()
    assert not (project / "revisions/001/reviews/medical-approval.yaml").exists()

    write_critic_review_fixture(project)
    submitted = runner.invoke(app, ["step", "submit-medical", str(project)])
    assert submitted.exit_code == 0, submitted.stdout
    assert _state(project) is WorkflowState.AWAITING_MEDICAL_REVIEW
    assert not (project / "revisions/001/reviews/medical-approval.yaml").exists()


def test_invalid_claim_leaves_project_unchanged(tmp_path: Path) -> None:
    project = _evidence_ready(tmp_path)
    script = read_yaml(SOURCE / "script/script.yaml")
    script["lines"][0]["claim_id"] = "UNKNOWN"
    input_file = tmp_path / "bad-script.yaml"
    write_yaml_atomic(input_file, script)
    args = _draft_args(project)
    args[args.index("--script") + 1] = str(input_file)
    result = CliRunner().invoke(app, args)
    assert result.exit_code != 0
    assert "unknown claim" in result.stdout
    assert _state(project) is WorkflowState.EVIDENCE_READY
    assert not (project / "revisions/001/script/script.yaml").exists()


def test_missing_semantic_asset_prevents_medical_submission(tmp_path: Path) -> None:
    project = _evidence_ready(tmp_path)
    runner = CliRunner()
    assert runner.invoke(app, _draft_args(project)).exit_code == 0
    (project / "revisions/001/assets/evidence-r01.svg").unlink()
    result = runner.invoke(app, ["step", "submit-medical", str(project)])
    assert result.exit_code != 0
    assert _state(project) is WorkflowState.DRAFT_READY


def test_submit_draft_at_draft_ready_replaces_storyboard(tmp_path: Path) -> None:
    from healthvideo.workflows.draft import submit_draft

    project = _evidence_ready(tmp_path)
    assert CliRunner().invoke(app, _draft_args(project)).exit_code == 0
    board = read_yaml(SOURCE / "storyboard/storyboard.yaml")
    board["scenes"][1]["anatomy"]["motion"] += " Revised draft."
    board_file = tmp_path / "revised.yaml"
    write_yaml_atomic(board_file, board)
    submit_draft(project, SOURCE / "script/script.yaml", board_file,
                 SOURCE / "assets/asset-manifest.yaml")
    assert _state(project) is WorkflowState.DRAFT_READY
    assert read_yaml(project / "revisions/001/storyboard/storyboard.yaml")["scenes"][1]["anatomy"]["motion"] == board["scenes"][1]["anatomy"]["motion"]


def test_cli_submit_medical_creates_r5_snapshot_before_gate(tmp_path: Path, monkeypatch) -> None:
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.storage.files import sha256_file
    from healthvideo.workflows.gate_review import (
        R5_CATALOG,
        R5_LICENSE_LEDGER,
        R5_USED_ASSETS,
        approve_gate,
        hash_reviewed_artifacts,
        medical_reviewed_paths,
    )
    from tests.workflows.test_produce import V2_REVIEWED_AT, _r5_project

    project = _r5_project(tmp_path, state=WorkflowState.DRAFT_READY, monkeypatch=monkeypatch)
    revision = project / "revisions/001"
    asset = revision / "assets/cell.svg"
    asset.write_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'/>")
    digest = sha256_file(asset)
    record = {
        "id": "cell",
        "file": "assets/cell.svg",
        "source_page": "https://smart.servier.com/smart_image/cell/",
        "original_url": "https://smart.servier.com/cell.svg",
        "author": "Fixture author",
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "sha256": digest,
    }
    write_yaml_atomic(revision / R5_CATALOG, {"assets": [record]})
    manifest_data = read_yaml(revision / "assets/asset-manifest.yaml")
    manifest_data["assets"].append({
        "path": "assets/cell.svg",
        "kind": "medical_diagram",
        "semantic": True,
        "creator": record["author"],
        "revision": "001",
        "source": record["source_page"],
        "license": record["license"],
        "sha256": digest,
    })
    write_yaml_atomic(revision / "assets/asset-manifest.yaml", manifest_data)
    board_data = read_yaml(revision / "storyboard/storyboard.yaml")
    board_data["scenes"][0]["shots"][0]["asset_paths"] = ["assets/cell.svg"]
    write_yaml_atomic(revision / "storyboard/storyboard.yaml", board_data)
    write_critic_review_fixture(project)

    assert not (revision / R5_USED_ASSETS).exists()
    assert not (revision / R5_LICENSE_LEDGER).exists()

    result = CliRunner().invoke(app, ["step", "submit-medical", str(project)])
    assert result.exit_code == 0, result.stdout
    assert _state(project) is WorkflowState.AWAITING_MEDICAL_REVIEW
    assert (revision / R5_USED_ASSETS).is_file()
    assert (revision / R5_LICENSE_LEDGER).is_file()

    hashes = hash_reviewed_artifacts(medical_reviewed_paths(revision))
    assert f"r5-byte:{R5_USED_ASSETS}" in hashes
    assert f"r5-byte:{R5_LICENSE_LEDGER}" in hashes
    assert f"r5-byte:{R5_CATALOG}" in hashes
    assert "r5-byte:assets/cell.svg" in hashes

    approval = approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=V2_REVIEWED_AT)
    assert approval.artifact_hashes[f"r5-byte:{R5_USED_ASSETS}"] == hashes[f"r5-byte:{R5_USED_ASSETS}"]
    assert approval.artifact_hashes[f"r5-byte:{R5_LICENSE_LEDGER}"] == hashes[f"r5-byte:{R5_LICENSE_LEDGER}"]


@pytest.mark.parametrize("medical", [False, True])
def test_unsupported_anatomy_subject_refused_before_submission(tmp_path: Path, medical: bool) -> None:
    from healthvideo.workflows.draft import submit_draft, submit_medical_review

    project = _evidence_ready(tmp_path)
    if medical:
        assert CliRunner().invoke(app, _draft_args(project)).exit_code == 0
    board = read_yaml(SOURCE / "storyboard/storyboard.yaml")
    board["scenes"][1]["visual"] = "anatomy_animation"
    board["scenes"][1]["anatomy"] = {"subject": "kidney", "state": "normal", "motion": "pulse"}
    board_file = (project / "revisions/001/storyboard/storyboard.yaml" if medical
                  else tmp_path / "unsupported.yaml")
    write_yaml_atomic(board_file, board)
    if medical:
        write_critic_review_fixture(project)
    before = (project / "project.yaml").read_bytes()
    with pytest.raises(ValueError, match="unsupported anatomy subject"):
        if medical:
            submit_medical_review(project)
        else:
            submit_draft(project, SOURCE / "script/script.yaml", board_file,
                         SOURCE / "assets/asset-manifest.yaml")
    assert (project / "project.yaml").read_bytes() == before


def test_submit_draft_preserves_validation_value_error_when_staging_cleanup_hits_permission_error(
    tmp_path: Path, monkeypatch,
) -> None:
    from healthvideo.workflows.draft import submit_draft

    project = _evidence_ready(tmp_path)
    board = read_yaml(SOURCE / "storyboard/storyboard.yaml")
    board["scenes"][1]["visual"] = "anatomy_animation"
    board["scenes"][1]["anatomy"] = {"subject": "kidney", "state": "normal", "motion": "pulse"}
    board_file = tmp_path / "unsupported.yaml"
    write_yaml_atomic(board_file, board)

    def fail_rmtree(path, *args, **kwargs):
        if kwargs.get("ignore_errors"):
            return
        raise PermissionError("WinError 5: locked staging dir")

    monkeypatch.setattr(shutil, "rmtree", fail_rmtree)
    with pytest.raises(ValueError, match="unsupported anatomy subject"):
        submit_draft(project, SOURCE / "script/script.yaml", board_file,
                     SOURCE / "assets/asset-manifest.yaml")


def test_r5_estimated_precheck_aggregates_scenes_without_tts(tmp_path, monkeypatch):
    from healthvideo.domain.script import Script
    from healthvideo.render import timing
    from healthvideo.workflows.draft import validate_estimated_layout
    from tests.render.test_quality import board, shot, window

    b = board([shot(0, 300, windows=[window(0, 250)])], 300)
    second = b.scenes[0].model_copy(update={"id": "S2", "start_frame": 300,
        "shots": tuple(s.model_copy(update={"id": "SH2"}) for s in b.scenes[0].shots)})
    b = b.model_copy(update={"scenes": (*b.scenes, second)})
    script = Script(title="Synthetic", lines=[{"id": "L1", "text": "w0 w250"}])
    monkeypatch.setattr(timing, "estimate_line_ms", lambda *args: {"L1": 20000})
    before = b.model_dump_json(), script.model_dump_json()
    with pytest.raises(ValueError) as exc:
        validate_estimated_layout(tmp_path, script, b)
    message = str(exc.value)
    assert "S1" in message and "S2" in message and "storyboard_director" in message
    assert before == (b.model_dump_json(), script.model_dump_json())


def test_r5_estimated_precheck_returns_runtime_and_preserves_sources(tmp_path, monkeypatch):
    from healthvideo.domain.script import Script
    from healthvideo.render import timing
    from healthvideo.workflows.draft import validate_estimated_layout
    from tests.render.test_quality import board, shot

    b = board([shot(0, 90, kind="story")], 90)
    script = Script(title="Synthetic", lines=[{"id": "L1", "text": "w0 Question1? Question2?"}])
    monkeypatch.setattr(timing, "estimate_line_ms", lambda *args: {"L1": 2700})
    before = b.model_dump_json(), script.model_dump_json()
    runtime = validate_estimated_layout(tmp_path, script, b)
    assert runtime.estimated is True
    assert runtime.scenes[0].resolved_shots[0].end_frame == 90
    assert before == (b.model_dump_json(), script.model_dump_json())
