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


from pathlib import Path

from healthvideo.render.chapters import render_long_form


def _fake_runner(calls: list[list[str]]):
    def run(argv: list[str]) -> int:
        calls.append(argv)
        out = Path(argv[argv.index("--output") + 1]) if "--output" in argv else Path(argv[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")
        return 0
    return run


def _render(tmp_path: Path, render_input, calls: list[list[str]]):
    (tmp_path / "ri.json").write_text("{}", encoding="utf-8")
    return render_long_form(
        render_input_path=tmp_path / "ri.json", render_input=render_input,
        public_dir=tmp_path, audio=tmp_path / "a.wav", output=tmp_path / "out" / "video.mp4",
        cache_dir=tmp_path / "cache", asset_hashes={}, renderer_identity=RENDERER,
        runner=_fake_runner(calls),
    )


def test_renders_each_chapter_then_concats(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    parts = _render(tmp_path, _input(("CH01", 900, "a"), ("CH02", 900, "b")), calls)
    assert [p.split("-")[0] for p in parts] == ["CH01", "CH02"]
    assert "--frames=0-899" in calls[0] and "--frames=900-1799" in calls[1]
    assert calls[2][0] == "ffmpeg" and (tmp_path / "out" / "video.mp4").is_file()
    assert not (tmp_path / "out" / "chapters.txt").exists()
    listing = (tmp_path / "cache" / "chapters.txt").read_text(encoding="utf-8")
    assert listing.count("file '") == 2


def test_second_run_reuses_unchanged_chapters(tmp_path: Path) -> None:
    _render(tmp_path, _input(("CH01", 900, "a"), ("CH02", 900, "b")), [])
    calls: list[list[str]] = []
    _render(tmp_path, _input(("CH01", 900, "a"), ("CH02", 900, "b-edited")), calls)
    rendered = [c for c in calls if c[0] != "ffmpeg"]
    assert len(rendered) == 1 and "--frames=900-1799" in rendered[0]


def test_failed_chapter_raises_and_leaves_no_part(tmp_path: Path) -> None:
    import pytest
    (tmp_path / "ri.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Chapter CH01 render failed"):
        render_long_form(
            render_input_path=tmp_path / "ri.json", render_input=_input(("CH01", 1800, "a")),
            public_dir=tmp_path, audio=tmp_path / "a.wav", output=tmp_path / "video.mp4",
            cache_dir=tmp_path / "cache", asset_hashes={}, renderer_identity=RENDERER,
            runner=lambda argv: 1,
        )
    assert not list((tmp_path / "cache").glob("*.mp4"))


def test_referenced_asset_without_hash_raises() -> None:
    import pytest

    from healthvideo.domain.storyboard import Scene, Storyboard
    from healthvideo.render.input import build_render_input

    scene = Scene(id="S01", start_frame=0, duration_frames=1800, narration="a",
                  visual="whiteboard", chapter_id="CH01",
                  visual_assets=({"path": "assets/missing.png", "role": "whiteboard"},))
    board = Storyboard(title="PYH", scenes=(scene,), format_profile="youtube_long")
    ri = build_render_input(board, "audio/narration.wav", duration_policy="v2")
    with pytest.raises(ValueError, match="assets/missing.png"):
        chapter_cache_key(ri, chapter_spans(ri)[0], {}, RENDERER)
