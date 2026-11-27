import pytest
from pydantic import ValidationError

from healthvideo.domain.clip_plan import (
    ClipPlan,
    ClipSpec,
    resolve_clip_scenes,
    validate_clip_plan,
    vertical_clip_storyboard,
)
from healthvideo.domain.script import Script, ScriptLine
from healthvideo.domain.storyboard import Scene, Storyboard


def scene(id="S01", **kwargs):
    return Scene(id=id, start_frame=0, duration_frames=1800, narration=id,
                 visual="whiteboard", on_screen_text=id, **kwargs)


def board(*scenes):
    return Storyboard(title="Test", format_profile="youtube_long", scenes=scenes)


def test_clip_script_line_contract():
    assert ScriptLine(id="L01", text="Hook", purpose="clip_hook", clip_id="CL01").clip_id == "CL01"
    for kwargs in ({"purpose": "clip_hook"}, {"clip_id": "CL01"},
                   {"purpose": "clip_hook", "clip_id": "CL1"},
                   {"purpose": "clip_hook", "clip_id": "CL01", "claim_id": "C01"}):
        with pytest.raises(ValidationError):
            ScriptLine(id="L01", text="Test", **kwargs)


def test_clip_scene_contract_and_projection():
    from healthvideo.domain.long_form import (
        long_form_lines,
        long_form_scenes,
        long_form_script,
        long_form_storyboard,
    )

    hook = scene("H01", clip_only="CL01")
    main = scene(chapter_id="CH01")
    storyboard = board(hook, main)
    script = Script(title="Test", lines=[ScriptLine(id="L01", text="Main"),
                    ScriptLine(id="L02", text="Hook", purpose="clip_hook", clip_id="CL01")])
    assert long_form_lines(script) == (script.lines[0],)
    assert long_form_script(script).lines == [script.lines[0]]
    assert long_form_scenes(storyboard) == (main,)
    assert long_form_storyboard(storyboard).scenes == (main,)
    assert long_form_scenes(storyboard.model_copy(update={"format_profile": "vertical_clip"})) == (hook, main)
    for updates in ({"start_frame": 1}, {"chapter_id": "CH01"}, {"clip_only": "CL1"}):
        raw = hook.model_dump() | updates
        with pytest.raises(ValidationError):
            Scene.model_validate(raw)


def test_resolve_uses_long_form_range_and_checks_ownership():
    a, b = scene("S01", chapter_id="CH01"), scene("S02", chapter_id="CH01")
    hook, outro = scene("H01", clip_only="CL01"), scene("O01", clip_only="CL01")
    storyboard = board(a, hook, b, outro)
    clip = ClipSpec(id="CL01", title="Clip", first_scene_id="S01", last_scene_id="S02", hook_scene_id="H01", outro_scene_id="O01")
    assert resolve_clip_scenes(clip, storyboard) == (hook, a, b, outro)
    with pytest.raises(ValueError, match="clip.only"):
        resolve_clip_scenes(clip.model_copy(update={"first_scene_id": "H01"}), storyboard)
    with pytest.raises(ValueError, match="CL02"):
        resolve_clip_scenes(clip.model_copy(update={"id": "CL02"}), storyboard)
    vertical = vertical_clip_storyboard(storyboard, (hook, a, outro))
    assert [s.start_frame for s in vertical.scenes] == [0, 1800, 3600]
    assert all(s.clip_only is None for s in vertical.scenes)


def test_clip_script_cross_validation():
    from healthvideo.domain.clip_plan import validate_clip_script

    line = ScriptLine(id="L01", text="Hook", purpose="clip_hook", clip_id="CL01")
    script = Script(title="Test", lines=[line])
    hook = scene("H01", clip_only="CL01", script_line_id="L01").model_copy(update={"narration": "Hook"})
    validate_clip_script(script, board(hook))
    for update in ({"narration": "Changed"}, {"claim_id": "C01"}, {"clip_only": "CL02"}, {"script_line_id": "missing"}, {"clip_only": None, "chapter_id": "CH01"}):
        with pytest.raises(ValueError):
            validate_clip_script(script, board(hook.model_copy(update=update)))
    with pytest.raises(ValueError, match="referenced"):
        validate_clip_script(script, board())


def test_marked_hook_duration_is_bounded():
    main = scene(chapter_id="CH01")
    hook = scene("H01", clip_only="CL01")
    clip = ClipSpec(id="CL01", title="Clip", first_scene_id="S01", last_scene_id="S01", hook_scene_id="H01")
    with pytest.raises(ValueError, match="hook"):
        validate_clip_plan(ClipPlan(clips=(clip,)), board(main, hook), {})


def test_r5_requires_hook_and_outro():
    from tests.render.test_quality import board as r5_board
    from tests.render.test_quality import shot

    storyboard = r5_board([shot(0, 1800)], frames=1800)
    storyboard = storyboard.model_copy(update={"format_profile": "youtube_long"})
    clip = ClipSpec(id="CL01", title="Clip", first_scene_id=storyboard.scenes[0].id,
                    last_scene_id=storyboard.scenes[0].id)
    with pytest.raises(ValueError, match="hook_scene_id and outro_scene_id"):
        validate_clip_plan(ClipPlan(clips=(clip,)), storyboard, {})


def test_r5_requires_dedicated_marked_hook_and_outro():
    from tests.render.test_quality import board as r5_board
    from tests.render.test_quality import shot

    original = r5_board([shot(0, 1800)], frames=1800)
    main = scene(chapter_id="CH01")
    hook, outro = scene("H01", chapter_id="CH01"), scene("O01", chapter_id="CH01")
    storyboard = original.model_copy(update={"format_profile": "youtube_long", "scenes": (hook, main, outro)})
    clip = ClipSpec(id="CL01", title="Clip", first_scene_id="S01", last_scene_id="S01",
                    hook_scene_id="H01", outro_scene_id="O01")
    with pytest.raises(ValueError, match="R5 hook requires clip_only=CL01"):
        validate_clip_plan(ClipPlan(clips=(clip,)), storyboard, {})


def test_plan_checks_approved_hook_and_outro_purposes():
    main = scene(chapter_id="CH01")
    hook = scene("H01", clip_only="CL01", script_line_id="L01").model_copy(
        update={"duration_frames": 150})
    outro = scene("O01", clip_only="CL01", script_line_id="L02").model_copy(
        update={"duration_frames": 240})
    script = Script(title="Test", lines=[
        ScriptLine(id="L01", text="H01", purpose="clip_hook", clip_id="CL01"),
        ScriptLine(id="L02", text="O01", purpose="clip_outro", clip_id="CL01"),
    ])
    clip = ClipSpec(id="CL01", title="Clip", first_scene_id="S01", last_scene_id="S01",
                    hook_scene_id="H01", outro_scene_id="O01")
    plan = ClipPlan(clips=(clip,))
    assert validate_clip_plan(plan, board(main, hook, outro), {}, script=script)["CL01"] == (hook, main, outro)
    with pytest.raises(ValueError, match="clip-only outro exceeds 8s"):
        validate_clip_plan(plan, board(main, hook, outro.model_copy(update={"duration_frames": 241})), {}, script=script)
    wrong = script.model_copy(update={"lines": [script.lines[0].model_copy(update={"purpose": "clip_outro"}), script.lines[1]]})
    with pytest.raises(ValueError, match="hook requires clip_hook"):
        validate_clip_plan(plan, board(main, hook, outro), {}, script=wrong)


def test_optional_markers_do_not_change_legacy_serialization():
    assert "clip_id" not in ScriptLine(id="L01", text="Test").model_dump()
    assert "clip_only" not in scene().model_dump()


def test_clip_script_rejects_duplicate_ids_and_source_marker_changes():
    from healthvideo.domain.clip_plan import validate_clip_script

    line = ScriptLine(id="L01", text="Outro", purpose="clip_outro", clip_id="CL01", source_marker="[1]")
    script = Script(title="Test", lines=[line])
    outro = scene("O01", clip_only="CL01", script_line_id="L01", source_marker="[1]").model_copy(update={"narration": "Outro"})
    validate_clip_script(script, board(outro))
    with pytest.raises(ValueError, match="source_marker"):
        validate_clip_script(script, board(outro.model_copy(update={"source_marker": "[2]"})))
    with pytest.raises(ValueError, match="duplicate script line"):
        validate_clip_script(script.model_copy(update={"lines": [line, line]}), board(outro))
    with pytest.raises(ValueError, match="duplicate scene"):
        validate_clip_script(script, board(outro, outro))
    with pytest.raises(ValueError, match="exactly once"):
        validate_clip_script(script, board(outro, outro.model_copy(update={"id": "O02"})))


def test_mascot_long_form_roles_ignore_clip_only_scenes():
    from healthvideo.domain.storyboard import validate_style_a_mascot_poses

    main = scene(chapter_id="CH01", mascot_pose="welcome")
    storyboard = board(scene("H01", clip_only="CL01"), main, scene("O01", clip_only="CL01"))
    validate_style_a_mascot_poses(storyboard)


def test_pre_gate_estimated_layout_blocks_r5_missing_clip_hook_outro(tmp_path, monkeypatch):
    from healthvideo.workflows.draft import validate_estimated_layout
    from tests.render.test_quality import board as r5_board
    from tests.render.test_quality import shot

    original = r5_board([shot(0, 1800)], frames=1800)
    storyboard = original.model_copy(update={"format_profile": "youtube_long", "scenes": (
        original.scenes[0].model_copy(update={"chapter_id": "CH01"}),)})
    clip = ClipSpec(id="CL01", title="Clip", first_scene_id=storyboard.scenes[0].id,
                    last_scene_id=storyboard.scenes[0].id)
    monkeypatch.setattr("healthvideo.workflows.voice_preview.draft_line_ms", lambda *_: None)
    with pytest.raises(ValueError, match="R5 clip requires hook_scene_id and outro_scene_id"):
        validate_estimated_layout(tmp_path, Script(title="Test", lines=[
            ScriptLine(id="L1", text=storyboard.scenes[0].narration)]), storyboard,
                                  clip_plan=ClipPlan(clips=(clip,)), claims={})


@pytest.mark.parametrize("hook_ms,outro_ms,error", [
    (4700, 7700, None),
    (4800, 7700, "clip-only hook exceeds 5s"),
    (4700, 7800, "clip-only outro exceeds 8s"),
])
def test_pre_gate_measured_clip_speech_limits(tmp_path, monkeypatch, hook_ms, outro_ms, error):
    from healthvideo.workflows.draft import validate_estimated_layout
    from tests.render.test_quality import board as r5_board
    from tests.render.test_quality import shot

    original = r5_board([shot(0, 1800)], frames=1800)
    main_text = f"{original.scenes[0].narration} Question1? Question2?"
    main = original.scenes[0].model_copy(update={"chapter_id": "CH01", "narration": main_text})

    def _clip_shot(shot_id: str) -> dict:
        return {
            "id": shot_id, "kind": "story", "tier": None, "component": "ReferenceDistribution",
            "asset_paths": [], "question_ids": ["Q1"],
            "start": {"kind": "scene_start"}, "end": {"kind": "scene_end"},
            "actions": [], "text_windows": [], "long_shot_reason": None,
        }

    hook = scene("H01", clip_only="CL01", script_line_id="LH", shots=(_clip_shot("SH_H01"),))
    outro = scene("O01", clip_only="CL01", script_line_id="LO", shots=(_clip_shot("SH_O01"),))
    storyboard = original.model_copy(update={"format_profile": "youtube_long", "scenes": (hook, main, outro)})
    script = Script(title="Test", lines=[
        ScriptLine(id="L1", text=main.narration),
        ScriptLine(id="LH", text=hook.narration, purpose="clip_hook", clip_id="CL01"),
        ScriptLine(id="LO", text=outro.narration, purpose="clip_outro", clip_id="CL01"),
    ])
    clip = ClipSpec(id="CL01", title="Clip", first_scene_id=main.id, last_scene_id=main.id,
                    hook_scene_id=hook.id, outro_scene_id=outro.id)
    measured = {"L1": 60000, "LH": hook_ms, "LO": outro_ms}
    monkeypatch.setattr("healthvideo.workflows.voice_preview.draft_line_ms", lambda *_: measured)
    if error is not None:
        with pytest.raises(ValueError, match=error):
            validate_estimated_layout(tmp_path, script, storyboard, clip_plan=ClipPlan(clips=(clip,)), claims={})
    else:
        timed = validate_estimated_layout(tmp_path, script, storyboard, clip_plan=ClipPlan(clips=(clip,)), claims={})
        assert timed.scenes[0].duration_frames == 150
        assert timed.scenes[-1].duration_frames == 240
