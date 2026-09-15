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
from healthvideo.workflows import hook_outro as hook_outro_module
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
    return target


def test_author_outro_is_idempotent_and_contiguous(project: Path) -> None:
    author_hook_outro(project, duration_frames=90)
    revision = project / "revisions/001"
    script_path = revision / "script/script.yaml"
    board_path = revision / "storyboard/storyboard.yaml"
    script = read_yaml(script_path)
    board = read_yaml(board_path)
    assert script["format_profile"] == "hook_outro_v1"
    assert script["lines"][-1]["text"] == OUTRO_TEXT
    assert board["scenes"][-1]["start_frame"] == 1350
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
    author_hook_outro(project, duration_frames=90)
    revision = project / "revisions/001"
    intent = revision / "workflow/pending-hook-outro.yaml"
    write_yaml_atomic(intent, {"revision": "001"})
    with pytest.raises(ValueError, match="pending"):
        approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=datetime.now(UTC))
    intent.unlink()
    with pytest.raises(ValueError, match="declared PYH logo"):
        approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=datetime.now(UTC))


def test_strict_hook_claim_requires_bound_marker(project: Path) -> None:
    author_hook_outro(project, duration_frames=90)
    revision = project / "revisions/001"
    script = Script.model_validate(read_yaml(revision / "script/script.yaml"))
    board = Storyboard.model_validate(read_yaml(revision / "storyboard/storyboard.yaml"))
    ledger = read_yaml(revision / "evidence/ledger.yaml")
    assert "[1]" in resolve_citations(script, ledger, board.scenes, strict_line_ids=True)
    first = script.lines[0].model_copy(update={"source_marker": None})
    bad = script.model_copy(update={"lines": [first, *script.lines[1:]]})
    with pytest.raises(ValueError, match="hook.*marker|marker.*hook"):
        resolve_citations(bad, ledger, board.scenes, strict_line_ids=True)


@pytest.mark.parametrize("interrupt_on", ["intent", "script", "board"])
def test_retry_recovers_each_authoring_interruption(
    project: Path, monkeypatch: pytest.MonkeyPatch, interrupt_on: str
) -> None:
    original = hook_outro_module.write_yaml_atomic
    suffix = {
        "intent": "pending-hook-outro.yaml",
        "script": "script.yaml",
        "board": "storyboard.yaml",
    }[interrupt_on]
    triggered = False

    def interrupted(path: Path, payload: dict) -> None:
        nonlocal triggered
        original(path, payload)
        if path.name == suffix and not triggered:
            triggered = True
            raise OSError("synthetic interruption")

    monkeypatch.setattr(hook_outro_module, "write_yaml_atomic", interrupted)
    with pytest.raises(OSError, match="synthetic interruption"):
        author_hook_outro(project, duration_frames=90)
    monkeypatch.setattr(hook_outro_module, "write_yaml_atomic", original)
    author_hook_outro(project, duration_frames=90)
    revision = project / "revisions/001"
    assert not (revision / "workflow/pending-hook-outro.yaml").exists()
    assert read_yaml(revision / "storyboard/storyboard.yaml")["scenes"][-1]["narration"] == OUTRO_TEXT


def test_cli_authors_outro(project: Path) -> None:
    result = CliRunner().invoke(app, ["outro", "author", str(project), "--duration-frames", "90"])
    assert result.exit_code == 0, result.output
    assert read_yaml(project / "revisions/001/script/script.yaml")["lines"][-1]["text"] == OUTRO_TEXT


def test_medical_packet_shows_hook_and_outro(project: Path) -> None:
    author_hook_outro(project, duration_frames=90)
    html = render_medical_packet(project / "revisions/001")
    assert "hook_outro_v1" in html
    assert "Ăn mặn có thể làm huyết áp tăng." in html
    assert OUTRO_TEXT in html


def test_retry_preserves_operator_edit_after_interruption(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = hook_outro_module.write_yaml_atomic

    def interrupted(path: Path, payload: dict) -> None:
        original(path, payload)
        if path.name == "pending-hook-outro.yaml":
            raise OSError("synthetic interruption")

    monkeypatch.setattr(hook_outro_module, "write_yaml_atomic", interrupted)
    with pytest.raises(OSError):
        author_hook_outro(project, duration_frames=90)
    monkeypatch.setattr(hook_outro_module, "write_yaml_atomic", original)
    script_path = project / "revisions/001/script/script.yaml"
    edited = read_yaml(script_path)
    edited["lines"][0]["text"] = "Operator đã sửa"
    write_yaml_atomic(script_path, edited)
    before = script_path.read_bytes()
    with pytest.raises(ValueError, match="refusing overwrite"):
        author_hook_outro(project, duration_frames=90)
    assert script_path.read_bytes() == before


def test_declared_logo_unblocks_medical_review(project: Path) -> None:
    author_hook_outro(project, duration_frames=90)
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
