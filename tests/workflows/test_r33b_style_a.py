"""R3.3b workflow tests for Style A pinning, storyboard mascot_pose, thumbnail, and 9:16 shorts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.render import thumbnail as thumbnail_render
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.factory_standards import STYLE_SPEC_FILE, pin_standards
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.shorts_plan import (
    STYLE_A_HOOK_MAX_SECONDS,
    STYLE_A_MASCOT_MAX_WIDTH_PERCENT,
    STYLE_A_SUBTITLE_POSITION,
    ShortClipSpec,
    save_shorts_plan,
    shorts_plan_ready,
)
from healthvideo.workflows.storyboard_design import (
    storyboard_ready,
    submit_storyboard_design,
)
from tests.helpers import create_v2_project_fixture, submit_video_fixture

NOW = datetime(2026, 11, 19, 3, 0, tzinfo=UTC)


def _seed_style_a(root: Path) -> Path:
    spec = root / STYLE_SPEC_FILE
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("# PYH Style A test spec\n", encoding="utf-8")
    return spec


def _fake_renderer(argv: list[str]) -> int:
    output = Path(argv[argv.index("--output") + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    if "still" in argv:
        Image.new("RGB", (1280, 720), "navy").save(output)
    else:
        output.write_bytes(b"synthetic-v2-mp4")
    return 0


def _add_mascot_poses(board: dict) -> dict:
    scenes = [dict(scene) for scene in board["scenes"]]
    seen_chapter = None
    last = len(scenes) - 1
    for index, scene in enumerate(scenes):
        if index == 0:
            scene["mascot_pose"] = "surprised"
        elif index == last or scene.get("visual") == "brand_outro":
            scene["mascot_pose"] = "thumbs_up"
        elif scene.get("chapter_id") and scene["chapter_id"] != seen_chapter:
            scene["mascot_pose"] = "explain"
        if scene.get("chapter_id"):
            seen_chapter = scene["chapter_id"]
    return {**board, "scenes": scenes}


def test_storyboard_design_enforces_style_a_mascot_pose_when_pinned(tmp_path: Path) -> None:
    _seed_style_a(tmp_path)
    project = create_v2_project_fixture(tmp_path / "projects", state=WorkflowState.DRAFT_READY)
    pin_standards(tmp_path, project)
    revision = project / "revisions/001"
    sb_path = revision / "storyboard/storyboard.yaml"
    assets_path = revision / "assets/asset-manifest.yaml"

    assert storyboard_ready(project) is False
    with pytest.raises(ValueError, match="thiếu mascot_pose"):
        submit_storyboard_design(project, sb_path, assets_path)

    updated_sb = tmp_path / "storyboard-style-a.yaml"
    write_yaml_atomic(updated_sb, _add_mascot_poses(read_yaml(sb_path)))
    submit_storyboard_design(project, updated_sb, assets_path)
    assert storyboard_ready(project) is True


def test_produce_rejects_missing_mascot_pose_and_records_style_spec_in_manifest(
    tmp_path: Path,
) -> None:
    _seed_style_a(tmp_path)
    project = create_v2_project_fixture(
        tmp_path / "projects", state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    pin_standards(tmp_path, project)
    approve_gate(project, GateKind.MEDICAL, reviewer="BS Test", now=NOW)
    with pytest.raises(ValueError, match="thiếu mascot_pose"):
        produce_project(project, SilentTTS(), _fake_renderer)

    # Fresh project with valid Style A mascot_pose produces and binds style_spec in render-manifest.
    project_ok = create_v2_project_fixture(
        tmp_path / "projects_ok", state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    rev_ok = project_ok / "revisions/001"
    write_yaml_atomic(
        rev_ok / "storyboard/storyboard.yaml",
        _add_mascot_poses(read_yaml(rev_ok / "storyboard/storyboard.yaml")),
    )
    pin_standards(tmp_path, project_ok)
    approve_gate(project_ok, GateKind.MEDICAL, reviewer="BS Test", now=NOW)
    produce_project(project_ok, SilentTTS(), _fake_renderer)
    manifest = json.loads((rev_ok / "renders/render-manifest.json").read_text(encoding="utf-8"))
    assert manifest["style_spec"]["path"] == STYLE_SPEC_FILE.as_posix()


def test_package_enforces_style_a_thumbnail_when_pinned(tmp_path: Path) -> None:
    _seed_style_a(tmp_path)
    project = create_v2_project_fixture(
        tmp_path / "projects", state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    rev = project / "revisions/001"
    write_yaml_atomic(
        rev / "storyboard/storyboard.yaml",
        _add_mascot_poses(read_yaml(rev / "storyboard/storyboard.yaml")),
    )
    pin_standards(tmp_path, project)
    approve_gate(project, GateKind.MEDICAL, reviewer="BS Test", now=NOW)
    produce_project(project, SilentTTS(), _fake_renderer)

    posts_path = rev / "posts/posts.yaml"
    posts_data = read_yaml(posts_path)
    posts_data["thumbnail"] = {
        "headline": "Vì sao cần theo dõi huyết áp?",
        "background_prompt": "Flat illustration",
        "seed": 5,
    }
    write_yaml_atomic(posts_path, posts_data)
    thumbnail_render.render_thumbnail(rev, runner=_fake_renderer)
    submit_video_fixture(project)
    approve_gate(project, GateKind.VIDEO, reviewer="BS Test", now=NOW)

    with pytest.raises(ValueError, match="Thumbnail không đạt chuẩn phong cách A"):
        package_project(project)

    # Fresh project with Style A compliant thumbnail packages cleanly.
    project_ok = create_v2_project_fixture(
        tmp_path / "projects_ok", state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    rev_ok = project_ok / "revisions/001"
    write_yaml_atomic(
        rev_ok / "storyboard/storyboard.yaml",
        _add_mascot_poses(read_yaml(rev_ok / "storyboard/storyboard.yaml")),
    )
    pin_standards(tmp_path, project_ok)
    approve_gate(project_ok, GateKind.MEDICAL, reviewer="BS Test", now=NOW)
    posts_ok_path = rev_ok / "posts/posts.yaml"
    posts_ok = read_yaml(posts_ok_path)
    posts_ok["thumbnail"] = {
        "headline": "Ăn mặn hại mạch?",
        "background_prompt": "Flat 2D matte off_white background",
        "seed": 9,
        "mascot_pose": "surprised",
        "mechanism_visual": "artery_cross_section",
        "background_theme": "off_white",
        "font_family": "Be Vietnam Pro",
        "font_weight": 800,
    }
    write_yaml_atomic(posts_ok_path, posts_ok)
    produce_project(project_ok, SilentTTS(), _fake_renderer)
    submit_video_fixture(project_ok)
    approve_gate(project_ok, GateKind.VIDEO, reviewer="BS Test", now=NOW)
    publish = package_project(project_ok)
    posts_md = (publish / "posts.md").read_text(encoding="utf-8")
    assert "## Thumbnail" in posts_md
    assert "surprised" in posts_md


def test_shorts_plan_enforces_style_a_9x16_defaults_and_limits(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "projects")
    base_clip = {
        "id": "CL01",
        "title": "Hook 9:16 chuẩn A",
        "hook_text": "Ăn mặn làm tăng huyết áp thế nào?",
        "start_scene_id": "S01",
        "end_scene_id": "S02",
        "target_seconds": 60,
        "caption": "Giảm muối giúp kiểm soát huyết áp [claim:C01].",
        "safety_caveat": "Không tự ý ngưng thuốc khi chưa hỏi bác sĩ.",
        "safe_zone_checked": True,
    }

    # Defaults satisfy Style A 9:16 constraints for backward compatibility.
    clip = ShortClipSpec.model_validate(base_clip)
    assert clip.mascot_max_width_percent == STYLE_A_MASCOT_MAX_WIDTH_PERCENT
    assert clip.subtitle_position == STYLE_A_SUBTITLE_POSITION
    assert clip.hook_window_seconds == STYLE_A_HOOK_MAX_SECONDS

    # Violations are rejected.
    with pytest.raises(ValidationError):
        ShortClipSpec.model_validate({**base_clip, "mascot_max_width_percent": 32.0})
    with pytest.raises(ValidationError):
        ShortClipSpec.model_validate({**base_clip, "subtitle_position": "top_center"})
    with pytest.raises(ValidationError):
        ShortClipSpec.model_validate({**base_clip, "hook_window_seconds": 3.0})

    plan_file = tmp_path / "shorts-plan.yaml"
    write_yaml_atomic(
        plan_file,
        {
            "schema_version": "1.0",
            "clips": [
                {
                    **base_clip,
                    "mascot_max_width_percent": 25.0,
                    "subtitle_position": "bottom_center",
                    "hook_window_seconds": 1.5,
                }
            ],
        },
    )
    saved = save_shorts_plan(project, plan_file)
    assert saved.is_file()
    assert shorts_plan_ready(project) is True
