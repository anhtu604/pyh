"""Clip narration is reviewed explicitly and mapped only through approved scene IDs."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from healthvideo.domain.script import Script, ScriptLine
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import review_html
from healthvideo.workflows.shorts_plan import ShortsPlan, _validate_and_map_shorts_plan
from tests.helpers import create_long_form_project_fixture


def _artifacts(tmp_path: Path):
    project = create_long_form_project_fixture(tmp_path)
    revision = project / "revisions/001"
    script = Script.model_validate(read_yaml(revision / "script/script.yaml"))
    board = Storyboard.model_validate(read_yaml(revision / "storyboard/storyboard.yaml"))
    lines = [
        ScriptLine(id="CH01", text="Bạn đang băn khoăn <điều gì>?", purpose="clip_hook", clip_id="CL01"),
        ScriptLine(id="CO01", text="Thử hành động này. Xem video đầy đủ trên kênh.", purpose="clip_outro", clip_id="CL01"),
    ]
    script = script.model_copy(update={"lines": script.lines + lines})
    scenes = [board.scenes[0].model_copy(update={
        "id": scene_id, "script_line_id": line.id, "narration": line.text,
        "clip_only": "CL01", "chapter_id": None, "start_frame": 0,
        "claim_id": None, "source_marker": None,
        "visual": "whiteboard", "evidence_highlight": None,
        "on_screen_text": "Clip",
    }) for scene_id, line in zip(("SH01", "SO01"), lines, strict=True)]
    return script, board.model_copy(update={"scenes": board.scenes + tuple(scenes)})


def _plan(**extra):
    return ShortsPlan.model_validate({"clips": [{
        "id": "CL01", "title": "Clip", "hook_text": "Nhãn biên tập",
        "start_scene_id": "S01", "end_scene_id": "S02", "target_seconds": 70,
        "caption": "Caption", "safety_caveat": "Giữ giới hạn", "safe_zone_checked": True,
        **extra,
    }]})


@pytest.mark.parametrize("explicit", [True, False])
def test_shorts_map_approved_clip_hook_and_outro(tmp_path: Path, explicit: bool):
    script, board = _artifacts(tmp_path)
    plan = _plan(**({"hook_scene_id": "SH01", "outro_scene_id": "SO01"} if explicit else {}))
    mapped = _validate_and_map_shorts_plan(plan, script, board, {}, require_long_form_bounds=False)
    assert mapped.clips[0].hook_scene_id == "SH01"
    assert mapped.clips[0].outro_scene_id == "SO01"


def test_shorts_map_checks_dedicated_narration(tmp_path: Path):
    script, board = _artifacts(tmp_path)
    board = board.model_copy(update={"scenes": board.scenes[:-1] + (
        board.scenes[-1].model_copy(update={"narration": "Unapproved wording"}),
    )})
    with pytest.raises(ValueError, match="narration diverges"):
        _validate_and_map_shorts_plan(_plan(), script, board, {}, require_long_form_bounds=False)


def test_shorts_plan_rejects_new_narration_fields():
    with pytest.raises(ValidationError, match="Extra inputs"):
        _plan(outro_text="New narration")


def test_medical_clip_section_groups_and_escapes_approved_lines(tmp_path: Path):
    script, _ = _artifacts(tmp_path)
    section = review_html._render_clip_lines_section(script)
    assert "Lời riêng cho clip" in section
    assert "CL01" in section and "Hook" in section and "Outro" in section
    assert "&lt;điều gì&gt;" in section
    assert "CH01" in section and "CO01" in section
    assert script.lines[0].text not in section


def test_medical_packet_includes_dedicated_clip_lines(tmp_path: Path):
    script, board = _artifacts(tmp_path)
    script = script.model_copy(update={"format_profile": "hook_outro_v1"})
    revision = next(tmp_path.glob("*/revisions/001"))
    write_yaml_atomic(revision / "script/script.yaml", script.model_dump(mode="json"))
    write_yaml_atomic(revision / "storyboard/storyboard.yaml", board.model_dump(mode="json"))
    packet = review_html.render_medical_packet(revision)
    assert "Lời riêng cho clip" in packet
    assert "CH01" in packet and "CO01" in packet
    hook_outro = packet.split("Hook và outro đã khai báo", 1)[1].split("</section>", 1)[0]
    assert script.lines[-3].text in hook_outro
    assert script.lines[-1].text not in hook_outro
    assert "Timeline outro: 5500–6100 frame" in hook_outro
