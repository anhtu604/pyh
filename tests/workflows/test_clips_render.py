import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.long_form import clip_render_input
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review_html import render_video_packet
from tests.helpers import create_long_form_project_fixture

REVIEWED_AT = datetime(2026, 9, 30, 9, 0, tzinfo=UTC)
REVIEWER = "BS Nguyễn Văn An"


def _runner(calls: list[list[str]]):
    def run(argv: list[str]) -> int:
        calls.append(argv)
        out = Path(argv[argv.index("--output") + 1]) if "--output" in argv else Path(argv[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")
        return 0
    return run


def _produced(tmp_path: Path) -> tuple[Path, list[list[str]]]:
    project_dir = create_long_form_project_fixture(tmp_path)
    approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)
    calls: list[list[str]] = []
    produce_project(project_dir, SilentTTS(), _runner(calls))
    return project_dir, calls


def test_clip_render_input_is_vertical_and_retimed(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    board = Storyboard.model_validate(
        read_yaml(project_dir / "revisions/001/storyboard/storyboard.yaml")
    )
    result = clip_render_input(board, board.scenes[2:4], "audio/clips/CL02.wav")
    assert (result.format_profile, result.width, result.height) == ("vertical_clip", 1080, 1920)
    assert [(s.id, s.start_frame, s.chapter_id) for s in result.scenes] == [
        ("S03", 0, None), ("S04", 900, None)
    ]
    assert [s.narration for s in result.scenes] == [s.narration for s in board.scenes[2:4]]


def test_produce_renders_each_clip_vertical(tmp_path: Path) -> None:
    project_dir, calls = _produced(tmp_path)
    renders = project_dir / "revisions" / "001" / "renders"
    manifest = json.loads((renders / "render-manifest.json").read_text(encoding="utf-8"))
    assert manifest["clips"] == {
        "CL01": "clips/CL01.mp4", "CL02": "clips/CL02.mp4", "CL03": "clips/CL03.mp4"
    }
    clip_input = json.loads(
        (renders / "clips" / "CL01.render-input.json").read_text(encoding="utf-8")
    )
    assert (clip_input["width"], clip_input["height"]) == (1080, 1920)
    assert [scene["id"] for scene in clip_input["scenes"]] == ["S01", "S02"]
    assert (renders / "audio" / "clips" / "CL01.wav").is_file()
    assert all((renders / relative).is_file() for relative in manifest["clips"].values())
    assert calls[-1][0] == "ffmpeg"
    clip_calls = [c for c in calls if c[0] != "ffmpeg" and not any(a.startswith("--frames") for a in c)]
    assert len(clip_calls) == 3


def test_video_gate_binds_clips(tmp_path: Path) -> None:
    project_dir, _ = _produced(tmp_path)
    record = approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=REVIEWED_AT)
    assert {f"renders/clips/CL0{n}.mp4" for n in (1, 2, 3)} <= record.artifact_hashes.keys()


def test_video_gate_refuses_missing_clip(tmp_path: Path) -> None:
    project_dir, _ = _produced(tmp_path)
    (project_dir / "revisions/001/renders/clips/CL02.mp4").unlink()
    with pytest.raises(FileNotFoundError, match="renders/clips/CL02.mp4"):
        approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=REVIEWED_AT)


def test_video_packet_lists_clips(tmp_path: Path) -> None:
    project_dir, _ = _produced(tmp_path)
    html = render_video_packet(project_dir / "revisions" / "001")
    assert "../renders/clips/CL01.mp4" in html
