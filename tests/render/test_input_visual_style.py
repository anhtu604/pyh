import hashlib
from pathlib import Path

from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.render.input import RenderInput, build_render_input
from healthvideo.storage.files import canonical_json_hash, read_yaml


def test_render_input_legacy_bytes_and_hash():
    board = Storyboard.model_validate(read_yaml(
        Path(__file__).parents[1] / "fixtures/golden-project-v2/revisions/001/storyboard/storyboard.yaml"
    ))
    result = build_render_input(board, "audio/narration.wav")
    assert hashlib.sha256(result.model_dump_json().encode()).hexdigest() == (
        "02b5c84cef8ffbf1a017f6a214568b76980a29af11cc2647ff3907fee1e1c0ea")
    assert canonical_json_hash(result.model_dump(mode="json")) == (
        "6c1a4d4b95dcdb46d036ac4c7c0f2569b0d1cee97bd3286d00aa1851ba41126b")
    explicit_nulls = result.model_dump(mode="json")
    explicit_nulls["visual_style"] = None
    for scene in explicit_nulls["scenes"]:
        scene["visual_takeaway"] = None
    assert RenderInput.model_validate(explicit_nulls).model_dump_json() == result.model_dump_json()


def test_render_input_style_and_takeaway_round_trip():
    board = Storyboard(title="Synthetic", visual_style="whiteboard", scenes=(Scene(
        id="S01", start_frame=0, duration_frames=150, visual="whiteboard",
        narration="Synthetic narration", on_screen_text="Synthetic label",
        visual_takeaway="Synthetic visual takeaway",
    ),))
    result = build_render_input(board, "audio/narration.wav")
    restored = RenderInput.model_validate_json(result.model_dump_json())
    assert restored.visual_style == "whiteboard"
    assert restored.scenes[0].visual_takeaway == "Synthetic visual takeaway"
