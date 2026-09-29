import pytest
from pydantic import ValidationError

from healthvideo.domain.format_profile import FORMAT_SPECS
from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.render.input import RenderInput, build_render_input


def _scene(scene_id: str, start: int, frames: int, chapter: str | None) -> Scene:
    return Scene(
        id=scene_id, start_frame=start, duration_frames=frames,
        narration="Nội dung", visual="whiteboard", chapter_id=chapter,
    )


def _long(*chapters: tuple[str, int]) -> Storyboard:
    scenes, start = [], 0
    for index, (chapter, frames) in enumerate(chapters, start=1):
        scenes.append(_scene(f"S{index:02d}", start, frames, chapter))
        start += frames
    return Storyboard(title="PYH", scenes=tuple(scenes), format_profile="youtube_long")


def test_legacy_storyboard_defaults_to_vertical_clip() -> None:
    board = Storyboard(title="PYH", scenes=(_scene("S01", 0, 1350, None),))
    result = build_render_input(board, "audio/a.wav")
    assert (result.format_profile, result.width, result.height) == ("vertical_clip", 1080, 1920)


def test_youtube_long_is_landscape_and_allows_25_minutes() -> None:
    result = build_render_input(_long(("CH01", 25 * 60 * 30)), "audio/a.wav")
    assert (result.format_profile, result.width, result.height) == ("youtube_long", 1920, 1080)


@pytest.mark.parametrize("frames", [60 * 30 - 1, 25 * 60 * 30 + 1])
def test_youtube_long_enforces_bounds_under_both_policies(frames: int) -> None:
    for policy in ("v1", "v2"):
        with pytest.raises(ValueError, match="total duration"):
            build_render_input(_long(("CH01", frames)), "audio/a.wav", duration_policy=policy)


def test_youtube_long_requires_chapter_on_every_scene() -> None:
    with pytest.raises(ValidationError, match="S02: youtube_long scene requires chapter_id"):
        Storyboard(
            title="PYH", format_profile="youtube_long",
            scenes=(_scene("S01", 0, 900, "CH01"), _scene("S02", 900, 900, None)),
        )


def test_youtube_long_rejects_non_contiguous_chapter() -> None:
    with pytest.raises(ValidationError, match="S03: chapter CH01 must be contiguous"):
        _long(("CH01", 900), ("CH02", 900), ("CH01", 900))


def test_chapter_id_pattern() -> None:
    with pytest.raises(ValidationError):
        _scene("S01", 0, 900, "chapter-1")


def test_render_input_rejects_size_that_mismatches_profile() -> None:
    with pytest.raises(ValidationError, match="youtube_long requires 1920x1080"):
        RenderInput(title="PYH", audio_file="audio/a.wav", format_profile="youtube_long")


def test_specs_match_spec_document() -> None:
    assert FORMAT_SPECS["vertical_clip"].max_frames == 90 * 30
    assert FORMAT_SPECS["youtube_long"].max_frames == 25 * 60 * 30
