"""Opt-in smoke across the actual Python to Remotion process boundary.

Only Remotion rendering/encoding and package assembly are real. The shared
synthetic_workflow_* fixtures isolate FLUX, music generation/mixing, branding
and Whisper alignment; narration explicitly uses SilentTTS. This does not
validate GPU models, paid speech providers, pronunciation or medical content.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.storage.files import read_yaml, sha256_file
from healthvideo.workflows.gate_review import approve_gate, check_revision_posts
from healthvideo.workflows.package import package_project
from tests.helpers import write_posts_fixture
from tests.workflows.test_draft import _draft_args, _evidence_ready


@pytest.mark.skipif(
    os.environ.get("PYH_REAL_RENDER_SMOKE") != "1",
    reason="set PYH_REAL_RENDER_SMOKE=1 to run actual Remotion",
)
def test_real_production_and_package(
    tmp_path: Path,
    synthetic_workflow_brand,
    synthetic_workflow_music,
    synthetic_workflow_illustrations,
    synthetic_workflow_alignment,
) -> None:
    project = _evidence_ready(tmp_path)
    runner = CliRunner()
    assert runner.invoke(app, _draft_args(project)).exit_code == 0
    assert runner.invoke(app, ["step", "submit-medical", str(project)]).exit_code == 0
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

    # Posts are part of the reviewed upload payload, even for a render smoke.
    write_posts_fixture(revision)
    assert check_revision_posts(revision) == []
    approve_gate(project, GateKind.VIDEO, reviewer="Fixture reviewer", now=datetime.now(UTC))
    published = package_project(project)
    assert sha256_file(published / "video.mp4") == sha256_file(run / "video.mp4")
    for name in ("posts.yaml", "posts.md", "caption.txt", "sources.md", "render-input.json"):
        assert (published / name).is_file()
    package_manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
    payload_hashes = package_manifest["payload_sha256"]
    assert {"video.mp4", "posts.yaml", "sources.md", "render-input.json"} <= payload_hashes.keys()
    for relative, digest in payload_hashes.items():
        assert sha256_file(published / relative) == digest
    assert read_yaml(published / "posts.yaml") == read_yaml(revision / "posts/posts.yaml")
    assert ProjectManifestV2.model_validate(read_yaml(project / "project.yaml")).state is WorkflowState.PACKAGED
