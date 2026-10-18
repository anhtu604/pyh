"""Task 4 profile selection, evidence preconditions and draft error blocking."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.explainer import Explainer
from healthvideo.domain.hook_outro import OUTRO_TEXT
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.script import Script
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.domain.storyboard import Storyboard
from healthvideo.qa.script import review_script
from healthvideo.storage.explainer import write_explainer
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.workflows.create_project_v2 import create_project_v2
from healthvideo.workflows.draft import submit_draft, submit_medical_review
from healthvideo.workflows.evidence import build_evidence_ledger
from healthvideo.workflows.operator import get_next_action
from tests.domain.test_explainer import explainer_data

GOLDEN = Path("tests/fixtures/golden-project-v2")


def _project(tmp_path: Path, profile: str, state: str = "research_in_progress") -> Path:
    project = tmp_path / "project"
    shutil.copytree(GOLDEN, project)
    data = read_yaml(project / "project.yaml")
    data.update(content_profile=profile, state=state)
    write_yaml_atomic(project / "project.yaml", data)
    return project


def _explainer(project: Path, claim_id: str = "R-TEST-01") -> None:
    data = explainer_data()
    for layer in data["layers"]:
        layer["claim_ids"] = [claim_id]
    write_explainer(project / "revisions/001", Explainer.model_validate(data))


def _claim() -> EvidenceClaim:
    return EvidenceClaim(id="R-TEST-01", type="professional_opinion",
                         text_public="Illustrative test statement only",
                         text_technical="Illustration only, not a medical claim")


def test_new_projects_default_to_explain_first(tmp_path: Path) -> None:
    project = create_project_v2(tmp_path, "test-project", "Illustration",
                                now=datetime(2026, 10, 18, tzinfo=UTC))
    manifest = resolve_project_layout(project).manifest
    assert manifest.content_profile == "explain_first_v1"


@pytest.mark.parametrize("fixture", ["golden-project", "golden-project-v2"])
def test_old_fixtures_read_without_changing_any_bytes(fixture: str) -> None:
    project = Path("tests/fixtures") / fixture
    before = {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}
    manifest = resolve_project_layout(project).manifest
    if isinstance(manifest, ProjectManifestV2):
        assert manifest.content_profile == "legacy"
    get_next_action(project)
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize("profile", ["legacy", "explain_first_v1"])
def test_state_graph_requires_explainer_only_for_explain_first(profile: str) -> None:
    project = ProjectManifestV2.model_validate({
        "slug": "test-project", "state": "research_in_progress", "content_profile": profile,
    })
    context = TransitionContext("001", "a" * 64, frozenset({"evidence/ledger.yaml"}))
    if profile == "explain_first_v1":
        with pytest.raises(ValueError, match="explainer"):
            transition_v2(project, WorkflowState.EVIDENCE_READY, context)
        assert project.state == WorkflowState.RESEARCH_IN_PROGRESS
        context = TransitionContext("001", "a" * 64, frozenset({
            "evidence/ledger.yaml", "explainer/explainer.yaml",
        }))
    assert transition_v2(project, WorkflowState.EVIDENCE_READY, context).state == "evidence_ready"


@pytest.mark.parametrize("problem", ["missing", "invalid", "unknown_claim"])
def test_evidence_rejects_bad_explainer_without_changing_state(tmp_path: Path, problem: str) -> None:
    project = _project(tmp_path, "explain_first_v1")
    before = (project / "project.yaml").read_bytes()
    if problem == "invalid":
        write_yaml_atomic(project / "revisions/001/explainer/explainer.yaml", {})
    elif problem == "unknown_claim":
        _explainer(project, "R-TEST-UNKNOWN")
    with pytest.raises(ValueError, match="explainer|Explainer|R-TEST-UNKNOWN"):
        build_evidence_ledger(project, [_claim()], [])
    assert (project / "project.yaml").read_bytes() == before


@pytest.mark.parametrize("profile", ["legacy", "explain_first_v1"])
def test_evidence_advances_with_profile_requirements(tmp_path: Path, profile: str) -> None:
    project = _project(tmp_path, profile)
    if profile == "explain_first_v1":
        _explainer(project)
    _, manifest = build_evidence_ledger(project, [_claim()], [])
    assert manifest.state == WorkflowState.EVIDENCE_READY


@pytest.mark.parametrize("state", ["author_brief_ready", "research_in_progress"])
def test_operator_and_cli_remind_to_create_missing_explainer(tmp_path: Path, state: str) -> None:
    from typer.testing import CliRunner

    from healthvideo.cli import app

    project = _project(tmp_path, "explain_first_v1", state)
    assert "explainer" in get_next_action(project).message
    result = CliRunner().invoke(app, ["operator", "status", str(project)])
    assert result.exit_code == 0, result.stdout
    assert "explainer" in result.stdout


@pytest.mark.parametrize("profile", ["legacy", "explain_first_v1"])
@pytest.mark.parametrize("problem", ["missing", "long_sentence", "order", "layer", "term", "warning"])
def test_draft_blocks_errors_only_for_explain_first(
    tmp_path: Path, profile: str, problem: str,
) -> None:
    project = _project(tmp_path, profile, "evidence_ready")
    revision = project / "revisions/001"
    if problem != "missing":
        _explainer(project, "C01")
    data = read_yaml(revision / "script/script.yaml")
    data["format_profile"] = "explain_first_v1"
    if problem in {"order", "layer", "term", "warning"}:
        data["lines"][0]["arc_beat"] = 3
    if problem == "long_sentence":
        data["lines"][0]["text"] = " ".join(["illustration"] * 33)
    elif problem == "order":
        data["lines"][1]["arc_beat"] = 2
    elif problem == "layer":
        data["lines"][0]["explainer_layer_id"] = "L-TEST-UNKNOWN"
    elif problem == "term":
        data["lines"][0]["text"] = "test term 1"
    if data.get("format_profile") == "explain_first_v1":
        data["lines"][-1].update(text=OUTRO_TEXT, purpose="outro", claim_id=None,
                                 source_marker=None)
        board = read_yaml(revision / "storyboard/storyboard.yaml")
        for line, scene in zip(data["lines"], board["scenes"], strict=True):
            scene.update(script_line_id=line["id"], narration=line["text"])
        board["scenes"][-1].update(visual="brand_outro", claim_id=None, source_marker=None,
                                  visual_assets=[{"path": "assets/test-logo.svg", "role": "brand"}])
        logo = revision / "assets/test-logo.svg"
        logo.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
        assets = read_yaml(revision / "assets/asset-manifest.yaml")
        assets["assets"].append({
            "path": "assets/test-logo.svg", "kind": "flourish", "semantic": False,
            "classification_reason": "Decorative test logo", "sha256": sha256_file(logo),
            "source": "synthetic_test_fixture", "license": "synthetic_test_only",
            "creator": "test", "revision": "001", "storyboard_role": "brand",
        })
        write_yaml_atomic(revision / "storyboard/storyboard.yaml", board)
        write_yaml_atomic(revision / "assets/asset-manifest.yaml", assets)
    if problem == "warning":
        issues = review_script(Script.model_validate(data), [
            EvidenceClaim.model_validate(item)
            for item in read_yaml(revision / "evidence/ledger.yaml")["claims"]
        ], [], explainer=Explainer.model_validate(explainer_data()))
        assert issues and all(issue.severity == "warning" for issue in issues)
    script_file = tmp_path / "script.yaml"
    write_yaml_atomic(script_file, data)
    before = {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}

    def submit() -> ProjectManifestV2:
        return submit_draft(project, script_file, revision / "storyboard/storyboard.yaml",
                            revision / "assets/asset-manifest.yaml")

    if profile == "explain_first_v1" and problem != "warning":
        expected = {
            "missing": "requires explainer/explainer.yaml",
            "long_sentence": "long_spoken_sentence",
            "order": "arc_beat_order",
            "layer": "unknown_explainer_layer",
            "term": "term_before_introduction",
        }
        with pytest.raises(ValueError, match=expected[problem]):
            submit()
        assert {path: path.read_bytes() for path in before} == before
        assert not list(revision.parent.glob(".001.draft-*"))
    else:
        assert submit().state == WorkflowState.DRAFT_READY


@pytest.mark.parametrize("submission", ["draft", "medical_review"])
def test_explain_first_rejects_legacy_script_without_changes(
    tmp_path: Path, submission: str,
) -> None:
    state = "evidence_ready" if submission == "draft" else "draft_ready"
    project = _project(tmp_path, "explain_first_v1", state)
    revision = project / "revisions/001"
    _explainer(project, "C01")
    script = read_yaml(revision / "script/script.yaml")
    script["format_profile"] = "legacy"
    write_yaml_atomic(revision / "script/script.yaml", script)
    before = {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}

    with pytest.raises(
        ValueError,
        match="^explain_first_v1 project requires script format_profile explain_first_v1$",
    ):
        if submission == "draft":
            submit_draft(project, revision / "script/script.yaml",
                         revision / "storyboard/storyboard.yaml",
                         revision / "assets/asset-manifest.yaml")
        else:
            submit_medical_review(project)

    assert {path: path.read_bytes() for path in project.rglob("*") if path.is_file()} == before
    assert not list(revision.parent.glob(".001.draft-*"))


def test_youtube_long_still_requires_explainer_before_evidence_ready(tmp_path: Path) -> None:
    project = _project(tmp_path, "explain_first_v1")
    revision = project / "revisions/001"
    path = revision / "storyboard/storyboard.yaml"
    data = read_yaml(path)
    data["format_profile"] = "youtube_long"
    for scene in data["scenes"]:
        scene["chapter_id"] = "CH01"
    board = Storyboard.model_validate(data)
    write_yaml_atomic(path, board.model_dump(mode="json"))
    before = (project / "project.yaml").read_bytes()
    with pytest.raises(ValueError, match="explainer/explainer.yaml before evidence_ready"):
        build_evidence_ledger(project, [_claim()], [])
    assert (project / "project.yaml").read_bytes() == before
    _explainer(project)
    _, manifest = build_evidence_ledger(project, [_claim()], [])
    assert manifest.state == WorkflowState.EVIDENCE_READY
