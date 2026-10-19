"""Public draft submission starts from evidence, without direct state edits."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.domain.author import AuthorBrief
from healthvideo.domain.evidence import EvidenceClaim, EvidenceQuestion, SourceRecord
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.topic import TopicCard
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.author import save_author_brief
from healthvideo.workflows.create_project_v2 import create_project_v2
from healthvideo.workflows.evidence import build_evidence_ledger, record_question
from healthvideo.workflows.topic import select_topic
from tests.helpers import complete_orientation_fixture, write_explainer_fixture

SOURCE = Path("tests/fixtures/golden-project-v2/revisions/001")
NOW = datetime(2026, 9, 17, tzinfo=UTC)


def _evidence_ready(tmp_path: Path) -> Path:
    project = create_project_v2(tmp_path, "draft-test", "Draft test", now=NOW)
    manifest = read_yaml(project / "project.yaml")
    manifest["content_profile"] = "legacy"
    write_yaml_atomic(project / "project.yaml", manifest)
    select_topic(project, TopicCard.model_validate(read_yaml(SOURCE / "topic/card.yaml")))
    complete_orientation_fixture(project, now=NOW)
    save_author_brief(
        project,
        AuthorBrief.model_validate(read_yaml(SOURCE / "author/brief.yaml")),
        confirm=True,
        now=NOW,
    )
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
    shutil.copy2(SOURCE / "assets/evidence-r01.svg", asset_dir)
    return project


def _state(project: Path) -> WorkflowState:
    return ProjectManifestV2.model_validate(read_yaml(project / "project.yaml")).state


def _draft_args(project: Path) -> list[str]:
    return [
        "operator", "draft", str(project),
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

    submitted = runner.invoke(app, ["operator", "submit-medical", str(project)])
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
    result = runner.invoke(app, ["operator", "submit-medical", str(project)])
    assert result.exit_code != 0
    assert _state(project) is WorkflowState.DRAFT_READY


def test_submit_draft_at_draft_ready_replaces_storyboard(tmp_path: Path) -> None:
    from healthvideo.workflows.draft import submit_draft

    project = _evidence_ready(tmp_path)
    assert CliRunner().invoke(app, _draft_args(project)).exit_code == 0
    board = read_yaml(SOURCE / "storyboard/storyboard.yaml")
    board["scenes"][0]["narration"] += " Revised draft."
    board_file = tmp_path / "revised.yaml"
    write_yaml_atomic(board_file, board)
    submit_draft(project, SOURCE / "script/script.yaml", board_file,
                 SOURCE / "assets/asset-manifest.yaml")
    assert _state(project) is WorkflowState.DRAFT_READY
    assert read_yaml(project / "revisions/001/storyboard/storyboard.yaml")["scenes"][0]["narration"] == board["scenes"][0]["narration"]


@pytest.mark.parametrize("medical", [False, True])
def test_unsupported_anatomy_subject_refused_before_submission(tmp_path: Path, medical: bool) -> None:
    from healthvideo.workflows.draft import submit_draft, submit_medical_review

    project = _evidence_ready(tmp_path)
    if medical:
        assert CliRunner().invoke(app, _draft_args(project)).exit_code == 0
    board = read_yaml(SOURCE / "storyboard/storyboard.yaml")
    board["scenes"][0]["visual"] = "anatomy_animation"
    board["scenes"][0]["anatomy"] = {"subject": "kidney", "state": "normal", "motion": "pulse"}
    board_file = (project / "revisions/001/storyboard/storyboard.yaml" if medical
                  else tmp_path / "unsupported.yaml")
    write_yaml_atomic(board_file, board)
    before = (project / "project.yaml").read_bytes()
    with pytest.raises(ValueError, match="unsupported anatomy subject"):
        if medical:
            submit_medical_review(project)
        else:
            submit_draft(project, SOURCE / "script/script.yaml", board_file,
                         SOURCE / "assets/asset-manifest.yaml")
    assert (project / "project.yaml").read_bytes() == before
