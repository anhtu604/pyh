"""Tests for deterministic SRT subtitle QA and 9:16 safe-zone validation."""

from __future__ import annotations

from pathlib import Path

from healthvideo.domain.script import Script, ScriptLine
from healthvideo.qa import (
    lint_project_qa,
    review_srt,
    review_srt_file,
    review_vertical_safe_zone,
)
from healthvideo.storage.files import write_yaml_atomic
from tests.helpers import create_v2_project_fixture


def test_review_srt_accepts_valid_vietnamese_and_real_questions() -> None:
    srt = (
        "1\n"
        "00:00:01,000 --> 00:00:04,500\n"
        "Bạn có biết vì sao men gan tăng?\n\n"
        "2\n"
        "00:00:04,500 --> 00:00:08,000\n"
        "Đừng tự ý mua thuốc bổ gan.\n"
    )
    script = Script(
        title="Men gan",
        lines=[
            ScriptLine(id="L01", text="Bạn có biết vì sao men gan tăng?"),
            ScriptLine(id="L02", text="Đừng tự ý mua thuốc bổ gan."),
        ],
    )
    assert review_srt(srt, script=script) == []


def test_review_srt_detects_empty_bad_timestamps_overlap_and_lossy_utf8(tmp_path: Path) -> None:
    script = Script(title="Test", lines=[ScriptLine(id="L01", text="Xin chào.")])
    empty_issues = review_srt("   \n", script=script)
    assert [issue.code for issue in empty_issues] == ["empty_srt"]

    broken_srt = (
        "2\n"
        "00:00:05,000 --> 00:00:04,000\n"
        "Chữ b? m?t d?u\n\n"
        "2\n"
        "00:00:03,000 --> 00:00:06,000\n"
        "Dòng thứ hai quá dài vượt mức bốn mươi hai ký tự chuẩn\n\n"
        "3\n"
        "00:00:05,500 --> 00:00:07,000\n"
        "Câu này bị chồng lấp.\n"
    )
    codes = {issue.code for issue in review_srt(broken_srt)}
    assert {
        "invalid_cue_index",
        "non_positive_duration",
        "lossy_utf8_srt",
        "non_monotonic_timestamp",
        "cue_layout_overflow",
        "overlapping_cue",
    } <= codes

    bad_file = tmp_path / "bad.srt"
    bad_file.write_bytes(b"\xff\xfe00:00")
    assert [issue.code for issue in review_srt_file(bad_file)] == ["invalid_utf8_srt"]


def test_review_vertical_safe_zone_checks_box_mascot_and_legacy_compatibility() -> None:
    # Legacy pre-Style-A clip without safe-zone metadata does not fail.
    legacy_clip = {"id": "CL01", "title": "Legacy", "first_scene_id": "S01", "last_scene_id": "S04"}
    assert review_vertical_safe_zone(legacy_clip, require_flag=False) == []

    # Valid 9:16 Style A clip & caption box inside 1080x1920 safe bounds.
    valid_clip = {
        "id": "CL01",
        "safe_zone_checked": True,
        "mascot_max_width_percent": 26,
        "subtitle_position": "bottom_center",
        "hook_window_seconds": 1.8,
    }
    assert (
        review_vertical_safe_zone(
            valid_clip,
            caption_lines=["Giữ gan khỏe mỗi ngày", "không lạm dụng thuốc"],
            caption_box={"x": 80, "y": 1300, "width": 840, "height": 150},
            require_flag=True,
        )
        == []
    )

    bad_clip = {
        "id": "CL02",
        "safe_zone_checked": False,
        "mascot_max_width_percent": 35,
        "subtitle_position": "top_left",
    }
    bad_issues = review_vertical_safe_zone(
        bad_clip,
        caption_box={"x": 100, "y": 1600, "width": 920, "height": 160},
        require_flag=True,
    )
    assert {issue.code for issue in bad_issues} == {
        "safe_zone_unchecked",
        "mascot_exceeds_safe_width",
        "invalid_subtitle_position",
        "safe_zone_bottom_overlap",
        "safe_zone_right_rail_overlap",
    }


def test_lint_project_qa_keeps_legacy_fixture_clean_and_catches_broken_srt(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path / "projects")
    rev = project_dir / "revisions/001"
    # Existing v2 fixture without SRT or shorts-plan passes cleanly.
    assert lint_project_qa(project_dir) == []

    # Adding a broken packaged SRT triggers deterministic SRT QA errors.
    srt_path = rev / "publish/subtitles.vi.srt"
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text(
        "1\n00:00:05,000 --> 00:00:08,000\nDòng đầu.\n\n"
        "2\n00:00:06,000 --> 00:00:09,000\nCh?ng l?p.\n",
        encoding="utf-8",
    )
    shorts_path = rev / "posts/shorts-plan.yaml"
    shorts_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml_atomic(
        shorts_path,
        {
            "schema_version": "1.0",
            "clips": [
                {
                    "id": "CL01",
                    "safe_zone_checked": False,
                    "mascot_max_width_percent": 28,
                }
            ],
        },
    )
    issues = lint_project_qa(project_dir)
    codes = {issue.code for issue in issues}
    assert {"overlapping_cue", "lossy_utf8_srt", "safe_zone_unchecked"} <= codes
