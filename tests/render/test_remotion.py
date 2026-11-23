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
    assert ["-movflags", "+faststart"] == argv[argv.index("-movflags"):argv.index("-movflags") + 2]


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


def test_remotion_bundle_reuse_syncs_public_and_supports_gl_fallback(tmp_path: Path) -> None:
    from healthvideo.render.remotion import (
        active_bundle,
        build_bundle_argv,
        create_bundle,
        render_gl_fallback_argv,
    )

    pub = tmp_path / "public"
    pub.mkdir()
    (pub / "audio").mkdir()
    (pub / "audio/narration.wav").write_bytes(b"wav1")

    bundle_dir = tmp_path / ".remotion-bundle"
    bundle_calls: list[list[str]] = []

    def fake_bundler(argv: list[str]) -> int:
        bundle_calls.append(argv)
        out_dir = Path(argv[argv.index("--out-dir") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text("<html></html>", encoding="utf-8")
        (out_dir / "public").mkdir(exist_ok=True)
        return 0

    assert build_bundle_argv(pub, bundle_dir)[3:6] == ["exec", "remotion", "bundle"]
    created = create_bundle(pub, bundle_dir, runner=fake_bundler)
    assert created == bundle_dir and len(bundle_calls) == 1

    # New clip audio added after bundling is synced into bundle/public on render.
    (pub / "audio/clips").mkdir()
    (pub / "audio/clips/CL01.wav").write_bytes(b"clip-wav")
    with active_bundle(bundle_dir, gl="angle", hardware_acceleration="if-possible"):
        argv = build_render_argv(tmp_path / "i.json", tmp_path / "o.mp4", pub)
    assert argv[3:7] == ["exec", "remotion", "render", str(bundle_dir.resolve())]
    assert argv[7] == "HealthVideo"
    assert "--gl=angle" in argv and "--hardware-acceleration=if-possible" in argv
    assert (bundle_dir / "public/audio/clips/CL01.wav").read_bytes() == b"clip-wav"

    fallback = render_gl_fallback_argv(argv)
    assert fallback is not None
    assert "--gl=swiftshader" in fallback and "--hardware-acceleration=disable" in fallback
    assert render_gl_fallback_argv(fallback) is None


def test_probe_video_streams_validates_streams_and_duration(tmp_path: Path) -> None:
    import json
    import shutil
    import subprocess

    import pytest

    from healthvideo.render.run import is_mp4_container, probe_video_streams

    mp4 = tmp_path / "sample.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32)
    assert is_mp4_container(mp4) is True

    def fake_probe(payload: dict, returncode: int = 0):
        def _run(argv, **kwargs):
            return subprocess.CompletedProcess(argv, returncode, stdout=json.dumps(payload), stderr="bad")
        return _run

    ok = probe_video_streams(
        mp4,
        expected_duration_ms=2000,
        runner=fake_probe({
            "format": {"duration": "2.02"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }),
    )
    assert ok["passed"] is True and ok["duration_ms"] == 2020 and ok["has_audio"] is True

    with pytest.raises(RuntimeError, match="no audio stream"):
        probe_video_streams(
            mp4,
            runner=fake_probe({
                "format": {"duration": "2.0"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }),
        )

    with pytest.raises(RuntimeError, match="differs from expected"):
        probe_video_streams(
            mp4,
            expected_duration_ms=5000,
            runner=fake_probe({
                "format": {"duration": "2.0"},
                "streams": [
                    {"codec_type": "video", "codec_name": "h264"},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
            }),
        )

    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        real_mp4 = tmp_path / "real.mp4"
        res = subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(real_mp4),
        ], capture_output=True, check=False)
        if res.returncode == 0 and real_mp4.is_file():
            probed = probe_video_streams(real_mp4, expected_duration_ms=1000)
            assert probed["has_video"] and probed["has_audio"]
            assert 800 <= probed["duration_ms"] <= 1200


def test_produce_prebundle_gpu_fallback_and_media_probe(tmp_path: Path, monkeypatch) -> None:
    import json

    from healthvideo.domain.gate_review import GateKind
    from healthvideo.domain.project_v2 import WorkflowState
    from healthvideo.tts.silent import SilentTTS
    from healthvideo.workflows import produce
    from healthvideo.workflows.gate_review import approve_gate
    from tests.helpers import create_v2_project_fixture

    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now="2026-11-22T23:54:00+07:00")

    bundle_calls: list[Path] = []
    render_calls: list[list[str]] = []

    def fake_create_bundle(public_dir: Path, out_dir: Path, **kwargs) -> Path:
        bundle_calls.append(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text("<html></html>", encoding="utf-8")
        (out_dir / "public").mkdir(exist_ok=True)
        return out_dir

    def fake_probe(path: Path, *, expected_duration_ms: int | None = None, **kwargs) -> dict:
        return {
            "passed": True,
            "path": path.name,
            "has_video": True,
            "has_audio": True,
            "duration_ms": expected_duration_ms or 1000,
            "expected_duration_ms": expected_duration_ms,
            "drift_ms": 0,
        }

    def runner(argv: list[str]) -> int:
        render_calls.append(argv)
        if "--gl=angle" in argv:
            return 1
        out = Path(argv[argv.index("--output") + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16)
        return 0

    monkeypatch.setenv("PYH_REMOTION_PREBUNDLE", "1")
    monkeypatch.setattr(produce.remotion_module, "create_bundle", fake_create_bundle)
    monkeypatch.setattr(produce, "probe_video_streams", fake_probe)

    result = produce.produce_project(project, tts=SilentTTS(), runner=runner)
    assert len(bundle_calls) == 1
    assert not bundle_calls[0].exists()
    assert len(render_calls) == 2
    assert "--gl=angle" in render_calls[0]
    assert "--gl=swiftshader" in render_calls[1]
    assert str(bundle_calls[0].resolve()) in render_calls[1]
    qa = json.loads((project / "revisions/001/reviews/video-qa.json").read_text(encoding="utf-8"))
    assert qa["media_probe"]["passed"] is True
    assert result.is_file()


def test_flux_style_a_suffix_is_affirmative() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("flux_generate", Path("tools/flux/generate.py"))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    suffix = mod.AFFIRMATIVE_STYLE_A_SUFFIX.lower()
    for banned in ("no text", "no letters", "no watermark", "without "):
        assert banned not in suffix
    assert "flat 2d vector" in suffix


def test_is_real_render_runner_detects_mocked_cli_or_factory_deps(monkeypatch) -> None:
    from healthvideo import cli
    from healthvideo.workflows import factory_deps, produce

    monkeypatch.delenv("PYH_REMOTION_PREBUNDLE", raising=False)
    assert produce._is_real_render_runner(cli.run_render_argv) is True
    assert produce._is_real_render_runner(factory_deps._run_render_argv) is True

    monkeypatch.setattr(cli, "resolve_pnpm_argv", lambda args: ["mock", *args])
    assert produce._is_real_render_runner(cli.run_render_argv) is False

    monkeypatch.setattr(factory_deps, "resolve_pnpm_argv", lambda args: ["mock", *args])
    assert produce._is_real_render_runner(factory_deps._run_render_argv) is False


def test_stage_medanim_assets_identity_and_bundle_sync(tmp_path: Path, monkeypatch) -> None:
    from healthvideo.render import remotion
    from healthvideo.storage.files import sha256_file

    repo_root = Path(__file__).resolve().parents[2]
    src_svg = repo_root / "library/medanim/liver-enzyme-leak/assets/niaid-liver-230.svg"
    assert src_svg.is_file()

    # 1. stage_fonts=False stays strictly read-only.
    dry_pub = tmp_path / "dry-pub"
    dry_pub.mkdir()
    remotion.build_render_argv(tmp_path / "i.json", tmp_path / "o.mp4", dry_pub, stage_fonts=False)
    assert list(dry_pub.iterdir()) == []

    # 2. stage_fonts=True stages medanim assets into public_dir/medanim/<id>/ with exact sha256.
    pub = tmp_path / "pub"
    pub.mkdir()
    remotion.build_render_argv(tmp_path / "i.json", tmp_path / "o.mp4", pub, stage_fonts=True)
    staged_svg = pub / "medanim/liver-enzyme-leak/niaid-liver-230.svg"
    assert staged_svg.is_file()
    assert sha256_file(staged_svg) == sha256_file(src_svg)

    pub_bundle = tmp_path / "pub-bundle"
    pub_bundle.mkdir()
    remotion.build_bundle_argv(pub_bundle, tmp_path / "out-bundle", stage_fonts=True)
    assert sha256_file(pub_bundle / "medanim/liver-enzyme-leak/niaid-liver-230.svg") == sha256_file(src_svg)

    # 3. sync_bundle_public copies public_dir/medanim/... into bundle_dir/public/medanim/...
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    remotion.sync_bundle_public(pub, bundle_dir)
    synced_svg = bundle_dir / "public/medanim/liver-enzyme-leak/niaid-liver-230.svg"
    assert synced_svg.is_file()
    assert sha256_file(synced_svg) == sha256_file(src_svg)

    # 4. renderer_identity reflects changes in library/medanim/*/assets/* while keeping the 4 keys.
    fake_repo = tmp_path / "fake-repo"
    (fake_repo / "src/healthvideo/render").mkdir(parents=True)
    (fake_repo / "video/src").mkdir(parents=True)
    (fake_repo / "video/public/fonts").mkdir(parents=True)
    (fake_repo / "video/src/index.ts").write_text("export {};", encoding="utf-8")
    (fake_repo / "video/package.json").write_text('{"dependencies":{"remotion":"4.0.522"}}', encoding="utf-8")
    (fake_repo / "video/public/fonts/font.woff2").write_bytes(b"font")
    med_asset = fake_repo / "library/medanim/liver-enzyme-leak/assets/niaid-liver-230.svg"
    med_asset.parent.mkdir(parents=True)
    med_asset.write_text("<svg>v1</svg>", encoding="utf-8")

    monkeypatch.setattr(remotion, "__file__", str(fake_repo / "src/healthvideo/render/remotion.py"))
    id1 = remotion.renderer_identity()
    assert set(id1.keys()) == {"name", "package_version", "source_sha256", "fonts_sha256"}
    med_asset.write_text("<svg>v2</svg>", encoding="utf-8")
    id2 = remotion.renderer_identity()
    assert id2["source_sha256"] != id1["source_sha256"]
    assert id2["fonts_sha256"] == id1["fonts_sha256"]
