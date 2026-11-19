"""Workflow tests for `shorts_plan` persistence and verified mapping to `ClipPlan`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from healthvideo.domain.gate_review import GateKind
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.shorts_plan import (
    SHORTS_PLAN_ARTIFACT,
    ShortClipSpec,
    _revision_hash,
    save_shorts_plan,
    shorts_plan_ready,
    sync_shorts_plan_to_clip_plan,
)
from tests.helpers import create_long_form_project_fixture

NOW = datetime(2026, 11, 19, 4, 0, tzinfo=UTC)
REVIEWER = "BS Nguyễn Văn An"


def _write_shorts(project_dir: Path, tmp_path: Path, clips: list[dict]) -> Path:
    plan_file = tmp_path / "shorts-input.yaml"
    write_yaml_atomic(
        plan_file,
        {
            "schema_version": "1.0",
            "clips": clips,
        },
    )
    return save_shorts_plan(project_dir, plan_file)


def _approved_long_form(tmp_path: Path, *, claim_on_s03: bool = False) -> Path:
    project = create_long_form_project_fixture(tmp_path)
    if claim_on_s03:
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
        cp_path = revision / "script/clip-plan.yaml"
        cp = read_yaml(cp_path)
        cp["clips"][1]["first_scene_id"] = "S02"
        write_yaml_atomic(cp_path, cp)
    approve_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    return project


def test_sync_shorts_plan_to_clip_plan_maps_style_a_and_preserves_caveats(tmp_path: Path) -> None:
    project = _approved_long_form(tmp_path)
    revision = project / "revisions/001"
    _write_shorts(
        project,
        tmp_path,
        [
            {
                "id": "CL01",
                "title": "Muối và huyết áp chuẩn A",
                "hook_text": "Ăn mặn ảnh hưởng huyết áp ra sao?",
                "start_scene_id": "S01",
                "end_scene_id": "S02",
                "target_seconds": 70,
                "loop_bridge": "Xem tiếp phần đọc nhãn muối.",
                "caption": "Giảm muối giúp hạ huyết áp [claim:C01].",
                "safety_caveat": "Mức giảm khác nhau giữa từng người [claim:C02].",
                "safe_zone_checked": True,
                "mascot_max_width_percent": 25.0,
                "subtitle_position": "bottom_center",
                "hook_window_seconds": 1.5,
            },
            {
                "id": "CL02",
                "title": "Nêm nhạt dần",
                "hook_text": "Tập nêm nhạt không khó như bạn nghĩ.",
                "start_scene_id": "S05",
                "end_scene_id": "S06",
                "target_seconds": 83,
                "caption": "Thói quen giảm muối hằng ngày.",
                "safety_caveat": "Trao đổi bác sĩ nếu đang điều trị tăng huyết áp.",
                "safe_zone_checked": True,
            },
        ],
    )
    assert shorts_plan_ready(project) is True

    mapped = sync_shorts_plan_to_clip_plan(revision)
    assert [clip.id for clip in mapped.clips] == ["CL01", "CL02"]
    assert mapped.clips[0].first_scene_id == "S01"
    assert mapped.clips[0].last_scene_id == "S02"
    assert mapped.clips[0].mascot_max_width_percent == 25.0
    assert mapped.clips[0].subtitle_position == "bottom_center"
    assert mapped.clips[0].hook_window_seconds == 1.5
    assert mapped.clips[1].first_scene_id == "S05"
    assert mapped.clips[1].last_scene_id == "S06"
    assert mapped.clips[1].mascot_max_width_percent == 28.0
    assert mapped.clips[1].subtitle_position == "bottom_center"
    assert mapped.clips[1].hook_window_seconds == 2.0


def test_sync_shorts_plan_requires_medical_approval(tmp_path: Path) -> None:
    project = create_long_form_project_fixture(tmp_path)
    revision = project / "revisions/001"
    _write_shorts(
        project,
        tmp_path,
        [
            {
                "id": "CL01",
                "title": "Chưa duyệt cổng y khoa",
                "hook_text": "Hook ngắn",
                "start_scene_id": "S01",
                "end_scene_id": "S02",
                "target_seconds": 70,
                "caption": "Caption [claim:C01].",
                "safety_caveat": "Caveat [claim:C02].",
                "safe_zone_checked": True,
            }
        ],
    )
    with pytest.raises(ValueError, match="current medical approval"):
        sync_shorts_plan_to_clip_plan(revision)


def test_sync_shorts_plan_blocks_missing_caveat_and_bad_duration(tmp_path: Path) -> None:
    project = _approved_long_form(tmp_path, claim_on_s03=True)
    revision = project / "revisions/001"

    # S03..S04 lasts 1890 frames (valid 60-90s duration), contains C01, but misses caveat C02 (S02).
    _write_shorts(
        project,
        tmp_path,
        [
            {
                "id": "CL01",
                "title": "Thiếu caveat",
                "hook_text": "Hook",
                "start_scene_id": "S03",
                "end_scene_id": "S04",
                "target_seconds": 63,
                "caption": "Giảm muối [claim:C01].",
                "safety_caveat": "Mức giảm khác nhau.",
                "safe_zone_checked": True,
            }
        ],
    )
    with pytest.raises(ValueError, match="CL01: claim C01 requires caveat C02"):
        sync_shorts_plan_to_clip_plan(revision)

    # Duration exceeds 90s Shorts upper bound (2700 frames).
    _write_shorts(
        project,
        tmp_path,
        [
            {
                "id": "CL01",
                "title": "Quá 90 giây",
                "hook_text": "Hook",
                "start_scene_id": "S01",
                "end_scene_id": "S04",
                "target_seconds": 90,
                "caption": "Giảm muối [claim:C01].",
                "safety_caveat": "Mức giảm khác nhau [claim:C02].",
                "safe_zone_checked": True,
            }
        ],
    )
    with pytest.raises(ValueError, match="CL01: duration 3790 frames must be between 1800 and 2700"):
        sync_shorts_plan_to_clip_plan(revision)

    # Duration under 60s RenderInput lower bound (1800 frames): S05 alone is 1500 + 90 = 1590 frames (53s).
    _write_shorts(
        project,
        tmp_path,
        [
            {
                "id": "CL01",
                "title": "Dưới 60 giây",
                "hook_text": "Hook",
                "start_scene_id": "S05",
                "end_scene_id": "S05",
                "target_seconds": 53,
                "caption": "Tóm tắt.",
                "safety_caveat": "Hỏi bác sĩ.",
                "safe_zone_checked": True,
            }
        ],
    )
    with pytest.raises(ValueError, match="CL01: duration 1590 frames must be between 1800 and 2700"):
        sync_shorts_plan_to_clip_plan(revision)


def test_sync_shorts_plan_blocks_narration_drift_and_tampered_style_a(tmp_path: Path) -> None:
    project = _approved_long_form(tmp_path)
    revision = project / "revisions/001"
    _write_shorts(
        project,
        tmp_path,
        [
            {
                "id": "CL01",
                "title": "Hợp lệ ban đầu",
                "hook_text": "Hook",
                "start_scene_id": "S01",
                "end_scene_id": "S02",
                "target_seconds": 70,
                "caption": "Giảm muối [claim:C01].",
                "safety_caveat": "Mức giảm khác nhau [claim:C02].",
                "safe_zone_checked": True,
            }
        ],
    )

    # Tampering storyboard narration invalidates both medical approval and hash.
    sb_path = revision / "storyboard/storyboard.yaml"
    sb = read_yaml(sb_path)
    sb["scenes"][0]["narration"] = "Lời đọc bị tự ý sửa sau cổng y khoa."
    write_yaml_atomic(sb_path, sb)
    with pytest.raises(ValueError, match="current medical approval"):
        sync_shorts_plan_to_clip_plan(revision)

    # Even without requiring medical approval, narration drift against script.yaml is blocked.
    shorts_path = revision / SHORTS_PLAN_ARTIFACT
    shorts_data = read_yaml(shorts_path)
    shorts_data["revision_hash"] = _revision_hash(revision)
    write_yaml_atomic(shorts_path, shorts_data)
    with pytest.raises(ValueError, match="narration diverges from approved script"):
        sync_shorts_plan_to_clip_plan(revision, require_medical_approval=False)

    # Style A constraints reject out-of-spec values.
    base = shorts_data["clips"][0]
    with pytest.raises(ValidationError):
        ShortClipSpec.model_validate({**base, "mascot_max_width_percent": 35.0})
    with pytest.raises(ValidationError):
        ShortClipSpec.model_validate({**base, "subtitle_position": "top_left"})
    with pytest.raises(ValidationError):
        ShortClipSpec.model_validate({**base, "hook_window_seconds": 2.5})
