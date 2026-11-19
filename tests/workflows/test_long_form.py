"""Tests for effective clip plan resolution and shorts-plan wired long-form clip output."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.long_form import (
    CLIP_PLAN_ARTIFACT,
    load_clip_scenes,
    load_effective_clip_specs,
)
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.shorts_plan import save_shorts_plan
from tests.helpers import create_long_form_project_fixture

NOW = datetime(2026, 11, 19, 4, 30, tzinfo=UTC)
REVIEWER = "BS Nguyễn Văn An"


def _runner(argv: list[str]) -> int:
    out = Path(argv[argv.index("--output") + 1]) if "--output" in argv else Path(argv[-1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"mp4-" + out.name.encode())
    return 0


def test_load_effective_clip_specs_backward_compatible_without_shorts_plan(tmp_path: Path) -> None:
    project = create_long_form_project_fixture(tmp_path)
    revision = project / "revisions/001"
    plan = load_effective_clip_specs(revision)
    assert [clip.id for clip in plan.clips] == ["CL01", "CL02", "CL03"]
    assert plan.clips[0].mascot_max_width_percent is None

    storyboard = Storyboard.model_validate(read_yaml(revision / "storyboard/storyboard.yaml"))
    scenes_by_clip = load_clip_scenes(revision, storyboard)
    assert list(scenes_by_clip) == ["CL01", "CL02", "CL03"]
    assert [s.id for s in scenes_by_clip["CL01"]] == ["S01", "S02"]


def test_long_form_produce_uses_posts_shorts_plan_when_present(tmp_path: Path) -> None:
    project = create_long_form_project_fixture(tmp_path)
    revision = project / "revisions/001"
    clip_plan_before = (revision / CLIP_PLAN_ARTIFACT).read_bytes()
    clip_plan_sha_before = sha256_file(revision / CLIP_PLAN_ARTIFACT)

    approve_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    # Shorts plan selects 2 clips (dropping CL03) with Style A 9:16 constraints.
    sp_file = tmp_path / "shorts-plan.yaml"
    write_yaml_atomic(
        sp_file,
        {
            "schema_version": "1.0",
            "clips": [
                {
                    "id": "CL01",
                    "title": "Hook muối và huyết áp",
                    "hook_text": "Ăn mặn tăng huyết áp thế nào?",
                    "start_scene_id": "S01",
                    "end_scene_id": "S02",
                    "target_seconds": 70,
                    "loop_bridge": "Theo dõi phần tiếp theo.",
                    "caption": "Giảm muối giúp kiểm soát huyết áp [claim:C01].",
                    "safety_caveat": "Mức đáp ứng khác nhau giữa từng người [claim:C02].",
                    "safe_zone_checked": True,
                    "mascot_max_width_percent": 26.0,
                    "subtitle_position": "bottom_center",
                    "hook_window_seconds": 1.8,
                },
                {
                    "id": "CL02",
                    "title": "Thói quen nêm nhạt",
                    "hook_text": "Nêm nhạt dần để bảo vệ mạch máu.",
                    "start_scene_id": "S05",
                    "end_scene_id": "S06",
                    "target_seconds": 83,
                    "caption": "Bắt đầu từ bữa cơm gia đình.",
                    "safety_caveat": "Không tự ý ngưng thuốc khi chưa hỏi bác sĩ.",
                    "safe_zone_checked": True,
                    "mascot_max_width_percent": 24.0,
                    "subtitle_position": "bottom_center",
                    "hook_window_seconds": 1.6,
                },
            ],
        },
    )
    save_shorts_plan(project, sp_file)

    effective = load_effective_clip_specs(revision)
    assert [clip.id for clip in effective.clips] == ["CL01", "CL02"]
    assert effective.clips[1].first_scene_id == "S05"
    assert effective.clips[1].last_scene_id == "S06"
    assert effective.clips[0].mascot_max_width_percent == 26.0
    assert effective.clips[0].subtitle_position == "bottom_center"
    assert effective.clips[0].hook_window_seconds == 1.8

    produce_project(project, SilentTTS(), _runner)

    # Approved script/clip-plan.yaml bytes remain untouched (medical gate stays valid).
    assert (revision / CLIP_PLAN_ARTIFACT).read_bytes() == clip_plan_before
    assert sha256_file(revision / CLIP_PLAN_ARTIFACT) == clip_plan_sha_before

    renders = revision / "renders"
    manifest = json.loads((renders / "render-manifest.json").read_text(encoding="utf-8"))
    assert manifest["clips"] == {
        "CL01": "clips/CL01.mp4",
        "CL02": "clips/CL02.mp4",
    }
    assert (renders / "clips/CL01.mp4").is_file()
    assert (renders / "clips/CL02.mp4").is_file()
    assert not (renders / "clips/CL03.mp4").exists()

    cl02_input = json.loads((renders / "clips/CL02.render-input.json").read_text(encoding="utf-8"))
    assert [scene["id"] for scene in cl02_input["scenes"]] == ["S05", "S06"]


def test_load_effective_clip_specs_rejects_broken_shorts_plan_after_medical_gate(
    tmp_path: Path,
) -> None:
    project = create_long_form_project_fixture(tmp_path)
    revision = project / "revisions/001"
    sb_path = revision / "storyboard/storyboard.yaml"
    sb = read_yaml(sb_path)
    sb["scenes"][2]["claim_id"] = "C01"
    sb["scenes"][2]["source_marker"] = "[1]"
    write_yaml_atomic(sb_path, sb)
    outline_path = revision / "script/outline.yaml"
    outline = read_yaml(outline_path)
    outline["chapters"][2]["claim_ids"] = ["C01"]
    write_yaml_atomic(outline_path, outline)
    cp_path = revision / CLIP_PLAN_ARTIFACT
    cp = read_yaml(cp_path)
    cp["clips"][1]["first_scene_id"] = "S02"
    write_yaml_atomic(cp_path, cp)
    approve_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    # S03..S04 is 1890 frames (valid duration) and has C01, but misses caveat C02 (S02).
    sp_file = tmp_path / "bad-shorts-plan.yaml"
    write_yaml_atomic(
        sp_file,
        {
            "schema_version": "1.0",
            "clips": [
                {
                    "id": "CL01",
                    "title": "Thiếu caveat sau cổng",
                    "hook_text": "Hook ngắn",
                    "start_scene_id": "S03",
                    "end_scene_id": "S04",
                    "target_seconds": 63,
                    "caption": "Giảm muối [claim:C01].",
                    "safety_caveat": "Hỏi bác sĩ.",
                    "safe_zone_checked": True,
                }
            ],
        },
    )
    save_shorts_plan(project, sp_file)

    with pytest.raises(ValueError, match="CL01: claim C01 requires caveat C02"):
        load_effective_clip_specs(revision)
    with pytest.raises(ValueError, match="CL01: claim C01 requires caveat C02"):
        produce_project(project, SilentTTS(), _runner)
