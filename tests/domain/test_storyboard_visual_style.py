"""Style contracts; all scene content here is synthetic."""

import hashlib
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.render.input import RenderInput, build_render_input
from healthvideo.storage.files import canonical_json_hash, read_yaml, write_yaml_atomic


def scene_data(visual="process_animation", **changes):
    data = {
        "id": "S01", "start_frame": 0, "duration_frames": 150,
        "narration": "Lời đọc thử nghiệm cho cảnh.",
        "on_screen_text": "Nhãn thử nghiệm trên hình.",
        "visual": visual, "chapter_id": "CH01",
    }
    if visual in {"anatomy_animation", "process_animation", "comparison", "timelapse"}:
        data["anatomy"] = {"subject": "heart", "state": "normal", "motion": "Test motion"}
    if visual == "source_card":
        data.update(claim_id="C01", source_marker="[1]", source_card={
            "source_id": "R01", "title": "Synthetic source", "journal": "Test",
            "interpretation": "Synthetic interpretation",
        })
    if visual == "evidence_highlight":
        data.update(source_marker="[1]", evidence_highlight={
            "image": "assets/test.png", "quote": "Synthetic quote",
            "x": 0, "y": 0, "width": 1, "height": 1,
        })
    if visual == "stat_gauge":
        data.update(claim_id="C01", stat_gauge={"value": 1, "unit": "%", "label": "Test"})
    if visual == "kinetic_term":
        data["kinetic_term"] = {"term": "Test", "definition": "Synthetic definition"}
    return {**data, **changes}


def board_data(style="scale_zoom", **scene_changes):
    return {"title": "Synthetic", "visual_style": style,
            "scenes": [scene_data(**scene_changes)]}


def test_legacy_fixture_serialization_bytes_and_hash_stay_unchanged(tmp_path):
    path = (Path(__file__).parents[1] / "fixtures/golden-project-v2/revisions/001"
            / "storyboard/storyboard.yaml")
    board = Storyboard.model_validate(read_yaml(path))
    payload = board.model_dump(mode="json")
    json_bytes = board.model_dump_json().encode("utf-8")
    yaml_bytes = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).encode("utf-8")
    # Captured from the existing model before adding either optional field.
    assert hashlib.sha256(json_bytes).hexdigest() == (
        "e5a6365206b4912c8767a4dbca4755469446c8600f7414361a0660aed82b72e0")
    assert hashlib.sha256(yaml_bytes).hexdigest() == (
        "e7db70b9c096ed354da05e299f012b2ee4776c6501e664e8e1904cc9afb57266")
    assert canonical_json_hash(payload) == (
        "8bb15606d94d5e709447e20a2e140004c8cb9492d735c448ba48d5928ba209b6")
    dumped = tmp_path / "storyboard.yaml"
    write_yaml_atomic(dumped, payload)
    assert dumped.read_bytes() == yaml_bytes
    assert Storyboard.model_validate(yaml.safe_load(yaml_bytes)).model_dump_json().encode() == json_bytes
    assert "visual_style" not in payload
    assert all("visual_takeaway" not in scene for scene in payload["scenes"])


@pytest.mark.parametrize("style", ["scale_zoom", "iso_infographic", "whiteboard"])
def test_valid_styles_round_trip(style):
    board = Storyboard.model_validate(board_data(style, visual_takeaway="Ý nghĩa hình thử nghiệm."))
    assert board.model_dump(mode="json")["visual_style"] == style


@pytest.mark.parametrize("style", ["unknown", "", "SCALE_ZOOM"])
def test_invalid_style_rejected(style):
    with pytest.raises(ValidationError, match="visual_style"):
        Storyboard.model_validate(board_data(style))


@pytest.mark.parametrize("style,visual", [
    (style, visual)
    for style, visuals in [
        ("scale_zoom", ("anatomy_animation", "process_animation", "comparison", "timelapse")),
        ("iso_infographic", ("anatomy_animation", "process_animation", "comparison", "timelapse")),
        ("whiteboard", ("process_animation", "comparison")),
    ]
    for visual in visuals
])
@pytest.mark.parametrize("takeaway", [None, "Ngắn", "x" * 11])
def test_mechanism_requires_meaningful_takeaway(style, visual, takeaway):
    with pytest.raises(ValidationError, match="Cảnh S01.*visual_takeaway"):
        Storyboard.model_validate(board_data(style, visual=visual, visual_takeaway=takeaway))


def test_mechanism_rejects_absent_takeaway():
    with pytest.raises(ValidationError, match="Cảnh S01.*visual_takeaway"):
        Storyboard.model_validate(board_data())


@pytest.mark.parametrize("text_field", ["narration", "on_screen_text"])
def test_takeaway_must_differ_after_case_and_whitespace_normalization(text_field):
    with pytest.raises(ValidationError, match="Cảnh S01.*visual_takeaway"):
        Storyboard.model_validate(board_data(
            visual_takeaway="  Ý NGHĨA\tHÌNH\nTHỬ NGHIỆM.  ",
            **{text_field: "ý nghĩa hình thử nghiệm."},
        ))


@pytest.mark.parametrize("value", ["", " \t\n", "x" * 161])
def test_takeaway_rejects_blank_or_overlong_even_without_style(value):
    with pytest.raises(ValidationError, match="visual_takeaway"):
        Scene.model_validate(scene_data(visual_takeaway=value))


@pytest.mark.parametrize("length", [12, 160])
def test_takeaway_trims_before_length_validation(length):
    board = Storyboard.model_validate(board_data(visual_takeaway="  " + "x" * length + " \t"))
    assert board.scenes[0].visual_takeaway == "x" * length


@pytest.mark.parametrize("style", ["scale_zoom", "iso_infographic", "whiteboard"])
@pytest.mark.parametrize("visual", [
    "chart", "source_card", "evidence_highlight", "brand_outro", "stat_gauge", "kinetic_term",
    "whiteboard", "anatomy_animation", "process_animation", "comparison", "timelapse",
])
def test_style_visual_allowlist(style, visual):
    data = board_data(style, visual=visual, visual_takeaway="Ý nghĩa hình thử nghiệm.")
    if style == "whiteboard" and visual in {"anatomy_animation", "timelapse"}:
        with pytest.raises(ValidationError, match="Cảnh S01.*whiteboard"):
            Storyboard.model_validate(data)
    else:
        assert Storyboard.model_validate(data).scenes[0].visual == visual


@pytest.mark.parametrize("style", ["scale_zoom", "iso_infographic"])
def test_whiteboard_allowed_in_multiple_chapters(style):
    first = scene_data("whiteboard")
    second = scene_data("whiteboard", id="S02", chapter_id="CH02", start_frame=150)
    data = {"title": "Synthetic", "visual_style": style, "scenes": [first, second]}
    board = Storyboard.model_validate(data)
    assert [scene.chapter_id for scene in board.scenes] == ["CH01", "CH02"]
    assert all(scene.visual == "whiteboard" and scene.visual_takeaway is None
               for scene in board.scenes)
    second["chapter_id"] = "CH01"
    assert len(Storyboard.model_validate(data).scenes) == 2
    second["chapter_id"] = "CH02"
    data["visual_style"] = "whiteboard"
    assert len(Storyboard.model_validate(data).scenes) == 2


def test_legacy_board_skips_all_style_checks():
    data = {"title": "Legacy", "scenes": [
        scene_data("anatomy_animation"),
        scene_data("whiteboard", id="S02", chapter_id="CH02"),
        scene_data("whiteboard", id="S03", chapter_id="CH03"),
    ]}
    assert len(Storyboard.model_validate(data).scenes) == 3
    data["visual_style"] = None
    assert "visual_style" not in Storyboard.model_validate(data).model_dump()
    data["scenes"][0]["visual_takeaway"] = data["scenes"][0]["narration"]
    assert Storyboard.model_validate(data).scenes[0].visual_takeaway == data["scenes"][0]["narration"]


def test_style_and_takeaway_are_in_storyboard_hash():
    data = board_data(visual_takeaway="Ý nghĩa hình thử nghiệm.")
    original = canonical_json_hash(Storyboard.model_validate(data).model_dump(mode="json"))
    data["visual_style"] = "iso_infographic"
    assert canonical_json_hash(Storyboard.model_validate(data).model_dump(mode="json")) != original
    data["visual_style"] = "scale_zoom"
    data["scenes"][0]["visual_takeaway"] = "Ý nghĩa hình thử nghiệm khác."
    assert canonical_json_hash(Storyboard.model_validate(data).model_dump(mode="json")) != original


def test_styled_storyboard_builds_and_round_trips_render_input():
    board = Storyboard.model_validate(board_data(visual_takeaway="Ý nghĩa hình thử nghiệm."))
    rendered = build_render_input(board, "audio/test.wav")
    payload = rendered.model_dump(mode="json")
    assert payload["visual_style"] == "scale_zoom"
    assert payload["scenes"][0]["visual_takeaway"] == "Ý nghĩa hình thử nghiệm."
    assert RenderInput.model_validate(payload) == rendered
