import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.domain.brand import LogoVariant
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.hook_outro import OUTRO_TEXT
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.citations import resolve_citations
from healthvideo.workflows.gate_review import approve_gate, medical_reviewed_paths
from healthvideo.workflows.hook_outro import author_hook_outro
from healthvideo.workflows.review_html import render_medical_packet
from healthvideo.workflows.visual_assets import create_brand_logo_asset


@pytest.fixture
def project(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    shutil.copytree(Path("tests/fixtures/golden-project-v2"), target)
    data = read_yaml(target / "project.yaml")
    data["state"] = "awaiting_medical_review"
    write_yaml_atomic(target / "project.yaml", data)
    script_path = target / "revisions/001/script/script.yaml"
    script = read_yaml(script_path)
    script["format_profile"] = "hook_outro_v1"
    write_yaml_atomic(script_path, script)
    return target


def test_author_outro_is_idempotent_and_contiguous(project: Path) -> None:
    revision = project / "revisions/001"
    script_path = revision / "script/script.yaml"
    board_path = revision / "storyboard/storyboard.yaml"
    script = read_yaml(script_path)
    board = read_yaml(board_path)
    assert script["format_profile"] == "hook_outro_v1"
    assert script["lines"][-1]["text"] == OUTRO_TEXT
    assert board["scenes"][-1]["start_frame"] == 1110
    assert board["scenes"][-1]["duration_frames"] == 90
    assert board["scenes"][-1]["script_line_id"] == "OUTRO"
    before = (script_path.read_bytes(), board_path.read_bytes())
    author_hook_outro(project, duration_frames=90)
    assert (script_path.read_bytes(), board_path.read_bytes()) == before


def test_author_rejects_invalid_duration_without_write(project: Path) -> None:
    revision = project / "revisions/001"
    script_path = revision / "script/script.yaml"
    before = script_path.read_bytes()
    with pytest.raises(ValueError, match="duration"):
        author_hook_outro(project, duration_frames=0)
    assert script_path.read_bytes() == before


def test_medical_gate_rejects_unfinished_authoring_and_missing_logo(project: Path) -> None:
    revision = project / "revisions/001"
    intent = revision / "workflow/pending-hook-outro.yaml"
    write_yaml_atomic(intent, {"revision": "001"})
    with pytest.raises(ValueError, match="pending"):
        approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=datetime.now(UTC))
    intent.unlink()
    board_path = revision / "storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["scenes"][-1]["visual_assets"] = []
    write_yaml_atomic(board_path, board)
    with pytest.raises(ValueError, match="declared PYH logo"):
        approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=datetime.now(UTC))


def test_strict_hook_claim_requires_bound_marker(project: Path) -> None:
    revision = project / "revisions/001"
    script = Script.model_validate(read_yaml(revision / "script/script.yaml"))
    board = Storyboard.model_validate(read_yaml(revision / "storyboard/storyboard.yaml"))
    ledger = read_yaml(revision / "evidence/ledger.yaml")
    assert "[1]" in resolve_citations(script, ledger, board.scenes, strict_line_ids=True)
    first = script.lines[0].model_copy(update={"source_marker": None})
    bad = script.model_copy(update={"lines": [first, *script.lines[1:]]})
    with pytest.raises(ValueError, match="hook.*marker|marker.*hook"):
        resolve_citations(bad, ledger, board.scenes, strict_line_ids=True)


def test_cli_authors_outro(project: Path) -> None:
    result = CliRunner().invoke(app, ["outro", "author", str(project), "--duration-frames", "90"])
    assert result.exit_code == 0, result.output
    assert read_yaml(project / "revisions/001/script/script.yaml")["lines"][-1]["text"] == OUTRO_TEXT


def test_medical_packet_shows_hook_and_outro(project: Path) -> None:
    html = render_medical_packet(project / "revisions/001")
    assert "hook_outro_v1" in html
    assert Script.model_validate(read_yaml(project / "revisions/001/script/script.yaml")).lines[0].text in html
    assert OUTRO_TEXT in html


def test_declared_logo_unblocks_medical_review(project: Path) -> None:
    manifest_path = project / "revisions/001/assets/asset-manifest.yaml"
    manifest = read_yaml(manifest_path)
    manifest["assets"] = [
        item for item in manifest["assets"] if item["path"] != "assets/test-logo.svg"
    ]
    write_yaml_atomic(manifest_path, manifest)
    (manifest_path.parent / "test-logo.svg").unlink()
    board_path = project / "revisions/001/storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["scenes"][-1]["visual_assets"] = []
    write_yaml_atomic(board_path, board)
    path = create_brand_logo_asset(
        project, scene_id="OUTRO", asset_name="pyh-logo", variant=LogoVariant.MONOGRAM
    )
    assert path.is_file()
    manifest = read_yaml(project / "revisions/001/assets/asset-manifest.yaml")
    logo = next(item for item in manifest["assets"] if item["path"] == "assets/pyh-logo.svg")
    assert logo["source"] == "built_in:pyh-logo"
    assert create_brand_logo_asset(
        project, scene_id="OUTRO", asset_name="pyh-logo", variant=LogoVariant.MONOGRAM
    ) == path
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=datetime.now(UTC))
    assert (project / "revisions/001/reviews/medical-approval.yaml").is_file()
    assert "asset:assets/pyh-logo.svg" in medical_reviewed_paths(project / "revisions/001")


def test_explain_first_outro_is_preserved(project: Path) -> None:
    script_path = project / "revisions/001/script/script.yaml"
    script = read_yaml(script_path)
    script["format_profile"] = "explain_first_v1"
    write_yaml_atomic(script_path, script)
    before = script_path.read_bytes()
    with pytest.raises(ValueError, match="outro already exists"):
        author_hook_outro(project, duration_frames=90)
    assert script_path.read_bytes() == before
