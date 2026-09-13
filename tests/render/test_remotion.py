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
