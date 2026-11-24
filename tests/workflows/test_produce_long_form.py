import json
from datetime import UTC, datetime
from pathlib import Path

from healthvideo.domain.gate_review import GateKind
from healthvideo.storage.files import read_yaml
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.produce import produce_project
from tests.helpers import create_long_form_project_fixture

REVIEWED_AT = datetime(2026, 9, 29, 9, 0, tzinfo=UTC)


def test_r5_chapter_cache_reuses_unchanged_chapter_and_checks_bytes(tmp_path):
    from healthvideo.render.input import build_render_input
    from healthvideo.render.quality import resolve_r5_shots
    from healthvideo.workflows.long_form import render_r5_long_form
    from tests.render.test_quality import board, shot

    original = board([shot(0, 9000)], frames=9000)
    first = original.scenes[0].model_copy(update={"chapter_id": "CH01"})
    second = first.model_copy(update={"id": "S2", "start_frame": 9000, "chapter_id": "CH02",
        "shots": (first.shots[0].model_copy(update={"id": "SH2"}),)})
    original = original.model_copy(update={"scenes": (first, second), "format_profile": "youtube_long"})
    resolved = resolve_r5_shots(original)
    calls = []

    def runner(argv):
        calls.append(argv)
        output = Path(argv[argv.index("--output") + 1] if "--output" in argv else argv[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fixture video")
        return 0

    def run(value, identity=None):
        return render_r5_long_form(render_input_path=tmp_path / "input.json", render_input=value,
            public_dir=tmp_path, audio=tmp_path / "audio.wav", output=tmp_path / "out.mp4",
            cache_dir=tmp_path / "cache", asset_hashes={}, renderer_identity={"source": "fixture"},
            audio_identity=identity or {"voice_id": "fixture", "speed": "1.18", "lexicon": "fixture"}, runner=runner)

    value = build_render_input(resolved, "audio/a.wav")
    initial = run(value)
    changed = value.model_copy(update={"scenes": (value.scenes[0].model_copy(update={"narration": "changed fixture"}), value.scenes[1])})
    subsequent = run(changed)
    assert initial[0] != subsequent[0]
    assert initial[1] == subsequent[1]
    assert sum(any(arg.startswith("--frames") for arg in call) for call in calls) == 3
    # A present but corrupted cached MP4 is never accepted as a cache hit.
    (tmp_path / "cache" / subsequent[1]).write_bytes(b"corrupted")
    run(changed)
    assert sum(any(arg.startswith("--frames") for arg in call) for call in calls) == 4
    sped = run(changed, {"voice_id": "fixture", "speed": "1.2", "lexicon": "fixture"})
    assert all(a != b for a, b in zip(sped, subsequent))


def _long_form_project(tmp_path: Path) -> Path:
    project_dir = create_long_form_project_fixture(tmp_path)
    approve_gate(project_dir, GateKind.MEDICAL, reviewer="BS Nguyễn Văn An", now=REVIEWED_AT)
    return project_dir


def test_youtube_long_renders_by_chapter(tmp_path: Path) -> None:
    project_dir = _long_form_project(tmp_path)
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> int:
        calls.append(argv)
        if "--public-dir" in argv:
            public_dir = Path(argv[argv.index("--public-dir") + 1])
            fonts = Path(__file__).resolve().parents[2] / "video/public/fonts"
            for name in ("BeVietnamPro-SemiBold.woff2", "BeVietnamPro-ExtraBold.woff2", "OFL.txt"):
                assert (public_dir / "fonts" / name).read_bytes() == (fonts / name).read_bytes()
        out = Path(argv[argv.index("--output") + 1]) if "--output" in argv else Path(argv[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")
        return 0

    output = produce_project(project_dir, SilentTTS(), runner)
    renders = project_dir / "revisions" / "001" / "renders"
    manifest = json.loads((renders / "render-manifest.json").read_text(encoding="utf-8"))
    render_input = json.loads((renders / "render-input.json").read_text(encoding="utf-8"))

    assert output == renders / "video.mp4" and output.is_file()
    assert (render_input["width"], render_input["height"]) == (1920, 1080)
    assert manifest["chapter_parts"][0].startswith("CH01-")
    end = render_input["scenes"][0]["duration_frames"] - 1
    assert any(f"--frames=0-{end}" in call and "--muted" in call for call in calls)
    assert calls[-1][0] == "ffmpeg"
    assert read_yaml(project_dir / "project.yaml")["state"] == "production_in_progress"
    from tests.helpers import submit_video_fixture

    submit_video_fixture(project_dir)
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"
    # project-level so a new revision reuses unchanged chapters (spec 4.1)
    assert list((project_dir / "renders-cache").glob("CH01-*.mp4"))
    assert not (project_dir / "revisions" / "001" / "renders-cache").exists()


def test_cli_runner_routes_ffmpeg_concat_past_pnpm(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from healthvideo import cli

    project_dir = _long_form_project(tmp_path)
    executables: list[str] = []

    def fake_run(argv, **kwargs):
        executables.append(Path(argv[0]).stem.lower())
        out = Path(argv[argv.index("--output") + 1]) if "--output" in argv else Path(argv[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")
        return type("Done", (), {"returncode": 0})()

    monkeypatch.setattr(cli, "resolve_pnpm_argv",
                        lambda args: ["pnpm", *args])
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    result = CliRunner().invoke(cli.app, ["produce", str(project_dir), "--tts", "silent"])

    assert result.exit_code == 0, result.output
    assert executables[-1] == "ffmpeg"
    assert "ffmpeg" not in executables[:-1]
