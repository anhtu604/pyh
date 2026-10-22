"""Offline process-boundary E2E with real CLI subprocesses.

Every run is offline under `tmp_path`: TTS is silent, Remotion is the worker's
fake renderer, the only AI clip is fake bytes authored before the medical gate,
and nothing publishes. Exactly two human gates are approved per project.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.hook_outro import OUTRO_TEXT
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.video_ai.base import VeoRequest, VeoResult, VideoProbeResult
from healthvideo.workflows.ai_clips import AIClipRights, generate_ai_clip
from healthvideo.workflows.package import _ensure_v2_gate_approval
from healthvideo.workflows.visual_assets import (
    bind_chart_asset,
    create_evidence_chart,
)
from tests.helpers import (
    _advance_v2_state,
    create_v2_project_fixture,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("subprocess_worker.py")
FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures"
ENTERED_AT = datetime(2026, 9, 10, 7, 30, tzinfo=UTC)


@pytest.mark.parametrize("ai", [False, True])
def test_golden_v2_crosses_process_boundaries_to_a_package(
    tmp_path: Path, ai: bool
) -> None:
    project, provider_requests = _prepare_v2_awaiting_medical(tmp_path, ai=ai)
    revision = project / "revisions/001"

    for arguments in (
        ("review", "approve", project, "--gate", "medical", "--reviewer", "doctor", "--yes"),
        ("produce", project),
        ("review", "approve", project, "--gate", "video", "--reviewer", "doctor", "--yes"),
        ("package", project),
    ):
        _assert_cli_ok(*arguments)

    scenes = json.loads((revision / "renders/render-input.json").read_text(encoding="utf-8"))[
        "scenes"
    ]
    assert scenes[0]["start_frame"] == 0
    assert not any("intro" in f"{scene['id']} {scene['visual']}".lower() for scene in scenes)
    assert (scenes[-1]["visual"], scenes[-1]["narration"]) == ("brand_outro", OUTRO_TEXT)
    assert "test-logo.svg" in json.dumps(scenes[-1])
    qa = json.loads((revision / "reviews/video-qa.json").read_text(encoding="utf-8"))
    assert qa["composition_duration_ms"] == round(
        sum(scene["duration_frames"] for scene in scenes) * 1000 / 30
    )
    assert qa["audio_duration_ms"] == qa["composition_duration_ms"]
    assert sorted(path.name for path in (revision / "reviews").glob("*-approval.yaml")) == [
        "medical-approval.yaml",
        "video-approval.yaml",
    ]
    assert (revision / "publish/ai-disclosure.json").is_file() is ai
    assert read_yaml(project / "project.yaml")["state"] == "packaged"

    for kind in GateKind:
        _ensure_v2_gate_approval(project / "revisions/001", kind)
    assert len(provider_requests) == (1 if ai else 0)


def _prepare_v2_awaiting_medical(
    tmp_path: Path, *, ai: bool
) -> tuple[Path, list[VeoRequest]]:
    """Author a v2 project up to the medical gate in-process; AI bytes are fake."""
    if not ai:
        project = create_v2_project_fixture(
            tmp_path / "source", state=WorkflowState.AWAITING_MEDICAL_REVIEW
        )
        board_path = project / "revisions/001/storyboard/storyboard.yaml"
        board = read_yaml(board_path)
        return project, []

    project = tmp_path / "golden-project-v2"
    shutil.copytree(FIXTURES / "golden-project-v2", project)
    _advance_v2_state(project, WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision = project / "revisions/001"
    ledger = read_yaml(revision / "evidence/ledger.yaml")
    ledger["claims"][0]["chart_data"] = [
        {"id": "bp-count", "source_id": "R01", "label": "Mẫu thử tổng hợp",
         "value": 12, "denominator": 40, "unit": "người"}
    ]
    write_yaml_atomic(revision / "evidence/ledger.yaml", ledger)
    board = read_yaml(revision / "storyboard/storyboard.yaml")
    board["visual_budget_profile"] = "m6_5_v1"
    # A dedicated synthetic M6.5 scenario still exercises chart + Veo rights.
    from copy import deepcopy

    whiteboard = deepcopy(board["scenes"][-2])
    whiteboard.update(id="S03", script_line_id="L03", visual="whiteboard")
    highlight = deepcopy(board["scenes"][0])
    highlight.update(id="S01", script_line_id="L01")
    chart = deepcopy(highlight)
    chart.update(id="S04", script_line_id="L04", visual="chart")
    chart.pop("evidence_highlight")
    clip = deepcopy(highlight)
    clip.update(id="S02", script_line_id="L02", visual="ai_clip")
    clip.pop("evidence_highlight")
    board["scenes"] = [whiteboard, highlight, chart, clip, board["scenes"][-1]]
    durations = (1200, 165, 165, 180, 90)
    words = (95, 15, 15, 15)
    frame = 0
    for index, (scene, frames) in enumerate(zip(board["scenes"], durations, strict=True)):
        scene.update(start_frame=frame, duration_frames=frames)
        if index < 4:
            scene["narration"] = " ".join(["Synthetic."] * words[index])
        frame += frames
    from tests.helpers import align_fixture_script

    align_fixture_script(revision, board)
    write_yaml_atomic(revision / "storyboard/storyboard.yaml", board)
    create_evidence_chart(
        project, claim_id="C01", datum_id="bp-count", asset_name="chart-count",
        license="synthetic_test_only", rights_basis="fixture nội bộ", creator="repository_fixture",
    )
    bind_chart_asset(project, scene_id="S04", asset_path="assets/chart-count.svg")

    requests: list[VeoRequest] = []

    class FakeVeo:
        def generate(self, request: VeoRequest) -> VeoResult:
            requests.append(request)
            return VeoResult(video_bytes=b"synthetic-e2e-ai-clip", mime_type="video/mp4")

    generate_ai_clip(
        project, scene_id="S02", prompt="Minh họa tổng hợp: nêm ít muối",
        duration_seconds=6, requested_seed=None,
        rights=AIClipRights(
            source="Google Vertex AI generation", creator="PYH operator",
            license="synthetic_test_only", rights_basis="fixture nội bộ",
        ),
        transport=FakeVeo(), now=ENTERED_AT,
        probe=lambda _path: VideoProbeResult(
            mime_type="video/mp4", container="mp4", width=1080, height=1920,
            source_fps=24, duration_ms=6000, source_frame_count=144, video_stream_count=1,
        ),
    )
    return project, requests


def _cli(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WORKER), "cli", *map(str, arguments)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPOSITORY_ROOT,
        check=False,
        timeout=120,
    )


def _assert_cli_ok(*arguments: object) -> None:
    result = _cli(*arguments)
    assert result.returncode == 0, f"{arguments[:2]}: {result.stdout}{result.stderr}"
