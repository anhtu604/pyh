import pytest
from pydantic import ValidationError

from healthvideo.domain.hook_outro import OUTRO_TEXT, validate_hook_outro
from healthvideo.domain.script import Delivery, Script, ScriptLine
from healthvideo.domain.storyboard import Scene, Storyboard, VisualAssetRef


def _pair():
    script = Script(title="Thử nghiệm", format_profile="hook_outro_v1", lines=[
        ScriptLine(id="HOOK", text="Câu hỏi?", delivery=Delivery(intent="hook")),
        ScriptLine(id="OUTRO", text=OUTRO_TEXT, purpose="outro", delivery=Delivery(intent="close")),
    ])
    board = Storyboard(title="Thử nghiệm", scenes=(
        Scene(id="HOOK", start_frame=0, duration_frames=30, narration="Câu hỏi?", script_line_id="HOOK", visual="whiteboard"),
        Scene(id="OUTRO", start_frame=30, duration_frames=60, narration=OUTRO_TEXT, script_line_id="OUTRO", visual="brand_outro"),
    ))
    return script, board


def test_hook_outro_requires_pinned_final_line_and_scene():
    script, board = _pair()
    validate_hook_outro(script, board)
    with pytest.raises(ValueError, match="outro"):
        validate_hook_outro(script.model_copy(update={"lines": script.lines[:-1]}), board)
    bad = board.model_copy(update={"scenes": (*board.scenes[:-1], board.scenes[-1].model_copy(update={"narration": "Sai"}))})
    with pytest.raises(ValueError, match="mismatch"):
        validate_hook_outro(script, bad)


def test_medical_gate_requires_exactly_one_brand_reference():
    script, board = _pair()
    with pytest.raises(ValueError, match="logo"):
        validate_hook_outro(script, board, require_brand=True)
    logo = VisualAssetRef(path="assets/logo.svg", role="brand")
    final = board.scenes[-1].model_copy(update={"visual_assets": (logo,)})
    board = board.model_copy(update={"scenes": (*board.scenes[:-1], final)})
    validate_hook_outro(script, board, require_brand=True)
    two = final.model_copy(update={"visual_assets": (logo, VisualAssetRef(path="assets/logo2.svg", role="brand"))})
    with pytest.raises(ValueError, match="logo"):
        validate_hook_outro(script, board.model_copy(update={"scenes": (*board.scenes[:-1], two)}), require_brand=True)


def test_legacy_profile_defaults_and_rejects_new_outro():
    script, board = _pair()
    legacy = Script(title="Cũ", lines=script.lines[:1])
    assert legacy.format_profile == "legacy"
    first = board.scenes[0].model_copy(update={"script_line_id": None})
    validate_hook_outro(legacy, board.model_copy(update={"scenes": (first,)}))
    with pytest.raises(ValueError, match="legacy"):
        validate_hook_outro(legacy, board)


def test_brand_reference_cannot_have_pose():
    with pytest.raises(ValidationError, match="pose"):
        VisualAssetRef(path="assets/logo.svg", role="brand", pose="wave")
