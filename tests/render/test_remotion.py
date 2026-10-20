from pathlib import Path

from healthvideo.render.remotion import build_render_argv


def test_render_argv_uses_absolute_paths_because_pnpm_dir_changes_cwd(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    argv = build_render_argv(
        Path("cache/run/render-input.json"), Path("cache/run/video.mp4"), Path("cache/run")
    )
    for flag in ("--props", "--output", "--public-dir"):
        value = Path(argv[argv.index(flag) + 1])
        assert value.is_absolute(), flag
    assert argv[:2] == ["pnpm", "--dir"] and Path(argv[2]).name == "video"


from healthvideo.render.remotion import build_concat_argv


def test_render_argv_frame_range_and_muted(tmp_path) -> None:
    argv = build_render_argv(Path("i.json"), Path("o.mp4"), tmp_path, frames=(900, 1799), muted=True)
    assert "--frames=900-1799" in argv and "--muted" in argv


def test_render_argv_unchanged_without_options(tmp_path) -> None:
    argv = build_render_argv(Path("i.json"), Path("o.mp4"), tmp_path)
    assert not any(arg.startswith("--frames") or arg == "--muted" for arg in argv)


def test_concat_argv_copies_video_and_muxes_narration() -> None:
    argv = build_concat_argv(Path("list.txt"), Path("a.wav"), Path("out.mp4"))
    assert argv[0] == "ffmpeg" and ["-c:v", "copy"] == argv[argv.index("-c:v"):argv.index("-c:v") + 2]
    assert ["-map", "0:v", "-map", "1:a"] == argv[argv.index("-map"):argv.index("-map") + 4]


def test_renderer_identity_changes_when_font_bytes_change(tmp_path, monkeypatch) -> None:
    from healthvideo.render import remotion

    monkeypatch.setattr(remotion, "__file__", str(tmp_path / "src/healthvideo/render/remotion.py"))
    video = tmp_path / "video"
    (video / "src").mkdir(parents=True)
    (video / "src/fonts.ts").write_text("font loader", encoding="utf-8")
    (video / "package.json").write_text('{"dependencies":{"remotion":"4.0.522"}}', encoding="utf-8")
    fonts = video / "public/fonts"
    fonts.mkdir(parents=True)
    font = fonts / "BeVietnamPro-SemiBold.woff2"
    font.write_bytes(b"original font")
    original = remotion.renderer_identity()
    assert remotion.renderer_identity() == original
    font.write_bytes(b"updated font")
    assert remotion.renderer_identity() != original


def test_render_argv_can_use_the_builtin_public_dir() -> None:
    public_dir = Path(__file__).resolve().parents[2] / "video/public"
    argv = build_render_argv(Path("i.json"), Path("o.mp4"), public_dir)
    assert Path(argv[argv.index("--public-dir") + 1]) == public_dir.resolve()


def test_render_argv_stages_fonts_for_vertical_render_and_refreshes_them(tmp_path) -> None:
    fonts = Path(__file__).resolve().parents[2] / "video/public/fonts"
    (tmp_path / "fonts").mkdir()
    (tmp_path / "fonts/BeVietnamPro-SemiBold.woff2").write_bytes(b"stale font")

    def runner(argv):
        public_dir = Path(argv[argv.index("--public-dir") + 1])
        for source in fonts.iterdir():
            assert (public_dir / "fonts" / source.name).read_bytes() == source.read_bytes()
        return 0

    assert runner(build_render_argv(tmp_path / "i.json", tmp_path / "o.mp4", tmp_path)) == 0
