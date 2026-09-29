from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.render.chapters import ChapterSpan, chapter_cache_key, chapter_spans
from healthvideo.render.input import build_render_input

RENDERER = {"name": "remotion", "package_version": "4.0.522", "source_sha256": "x"}


def _input(*chapters: tuple[str, int, str]):
    scenes, start = [], 0
    for index, (chapter, frames, text) in enumerate(chapters, start=1):
        scenes.append(Scene(id=f"S{index:02d}", start_frame=start, duration_frames=frames,
                            narration=text, visual="whiteboard", chapter_id=chapter))
        start += frames
    board = Storyboard(title="PYH", scenes=tuple(scenes), format_profile="youtube_long")
    return build_render_input(board, "audio/narration.wav", duration_policy="v2")


def test_spans_merge_contiguous_scenes() -> None:
    spans = chapter_spans(_input(("CH01", 900, "a"), ("CH01", 900, "b"), ("CH02", 600, "c")))
    assert spans == (ChapterSpan("CH01", 0, 1800), ChapterSpan("CH02", 1800, 2400))


def test_key_ignores_absolute_position_of_chapter() -> None:
    short = _input(("CH01", 900, "a"), ("CH02", 900, "same"))
    longer = _input(("CH01", 1200, "a2"), ("CH02", 900, "same"))
    key = lambda ri: chapter_cache_key(ri, chapter_spans(ri)[1], {}, RENDERER)
    assert key(short) == key(longer)


def test_key_changes_with_text_renderer_and_assets() -> None:
    base = _input(("CH01", 1800, "a"))
    span = chapter_spans(base)[0]
    original = chapter_cache_key(base, span, {}, RENDERER)
    edited = _input(("CH01", 1800, "b"))
    assert chapter_cache_key(edited, chapter_spans(edited)[0], {}, RENDERER) != original
    assert chapter_cache_key(base, span, {}, {**RENDERER, "source_sha256": "y"}) != original
