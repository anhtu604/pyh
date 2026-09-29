"""Opt-in smoke across the actual Python to Remotion process boundary."""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.storage.files import read_yaml
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.package import package_project
from tests.workflows.test_draft import _draft_args, _evidence_ready


@pytest.mark.skipif(
    os.environ.get("PYH_REAL_RENDER_SMOKE") != "1",
    reason="set PYH_REAL_RENDER_SMOKE=1 to run actual Remotion",
)
def test_real_production_and_package(tmp_path: Path) -> None:
    project = _evidence_ready(tmp_path)
    runner = CliRunner()
    assert runner.invoke(app, _draft_args(project)).exit_code == 0
    assert runner.invoke(app, ["operator", "submit-medical", str(project)]).exit_code == 0
    approve_gate(project, GateKind.MEDICAL, reviewer="Fixture reviewer", now=datetime.now(UTC))

    produced = runner.invoke(app, ["produce", str(project), "--tts", "silent"])
    assert produced.exit_code == 0, produced.stdout
    manifest = ProjectManifestV2.model_validate(read_yaml(project / "project.yaml"))
    assert manifest.state is WorkflowState.AWAITING_VIDEO_REVIEW
    revision = project / "revisions/001"
    run = revision / "renders"
    assert (run / "video.mp4").stat().st_size > 0
    assert (run / "render-manifest.json").is_file()
    assert (revision / "reviews/video-qa.json").is_file()

    approve_gate(project, GateKind.VIDEO, reviewer="Fixture reviewer", now=datetime.now(UTC))
    published = package_project(project)
    assert (published / "video.mp4").is_file()
    assert ProjectManifestV2.model_validate(read_yaml(project / "project.yaml")).state is WorkflowState.PACKAGED
