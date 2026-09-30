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


def _long_form_project(tmp_path: Path) -> Path:
    project_dir = create_long_form_project_fixture(tmp_path)
    approve_gate(project_dir, GateKind.MEDICAL, reviewer="BS Nguyễn Văn An", now=REVIEWED_AT)
    return project_dir


def test_youtube_long_renders_by_chapter(tmp_path: Path) -> None:
    project_dir = _long_form_project(tmp_path)
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> int:
        calls.append(argv)
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
    assert "--frames=0-899" in calls[0] and "--muted" in calls[0]
    assert calls[-1][0] == "ffmpeg"
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

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    result = CliRunner().invoke(cli.app, ["produce", str(project_dir), "--tts", "silent"])

    assert result.exit_code == 0, result.output
    assert executables[-1] == "ffmpeg"
    assert "ffmpeg" not in executables[:-1]
