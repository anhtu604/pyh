from pathlib import Path

from healthvideo.render.remotion import build_render_argv


def test_render_argv_uses_absolute_paths_because_pnpm_dir_changes_cwd() -> None:
    argv = build_render_argv(
        Path("cache/run/render-input.json"), Path("cache/run/video.mp4"), Path("cache/run")
    )
    for flag in ("--props", "--output", "--public-dir"):
        value = Path(argv[argv.index(flag) + 1])
        assert value.is_absolute(), flag
    assert argv[:2] == ["pnpm", "--dir"] and Path(argv[2]).name == "video"


from healthvideo.render.remotion import build_concat_argv


def test_render_argv_frame_range_and_muted() -> None:
    argv = build_render_argv(Path("i.json"), Path("o.mp4"), Path("."), frames=(900, 1799), muted=True)
    assert "--frames=900-1799" in argv and "--muted" in argv


def test_render_argv_unchanged_without_options() -> None:
    argv = build_render_argv(Path("i.json"), Path("o.mp4"), Path("."))
    assert not any(arg.startswith("--frames") or arg == "--muted" for arg in argv)


def test_concat_argv_copies_video_and_muxes_narration() -> None:
    argv = build_concat_argv(Path("list.txt"), Path("a.wav"), Path("out.mp4"))
    assert argv[0] == "ffmpeg" and ["-c:v", "copy"] == argv[argv.index("-c:v"):argv.index("-c:v") + 2]
    assert ["-map", "0:v", "-map", "1:a"] == argv[argv.index("-map"):argv.index("-map") + 4]
