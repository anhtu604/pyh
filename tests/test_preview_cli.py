import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from healthvideo.cli import REPO_ROOT, app
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from tests.helpers import create_project_fixture, create_v2_project_fixture


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize(
    "version,profile,composition",
    [
        ("1.0", "vertical_clip", "VerticalClip"),
        ("2.0", "youtube_long", "LongForm"),
    ],
)
def test_preview_active_run_argv_and_url_are_read_only(
    tmp_path, monkeypatch, version, profile, composition
):
    project = (
        create_project_fixture(tmp_path, state="idea")
        if version == "1.0"
        else create_v2_project_fixture(tmp_path)
    )
    manifest = read_yaml(project / "project.yaml")
    manifest["artifact_hashes"]["production"] = "active-run"
    write_yaml_atomic(project / "project.yaml", manifest)
    root = project if version == "1.0" else project / "revisions" / "001"
    run = root / "renders" / "active-run" if version == "1.0" else root / "renders"
    run.mkdir(parents=True)
    props = run / "render-input.json"
    props.write_text(json.dumps({"format_profile": profile}), encoding="utf-8")
    # An existing lease must not prevent viewing or be changed by preview.
    (project / ".healthvideo").mkdir(exist_ok=True)
    (project / ".healthvideo" / "write-lease.yaml").write_bytes(b"busy")
    before = snapshot(project)
    monkeypatch.setattr(
        "healthvideo.cli.resolve_pnpm_argv", lambda args: ["pnpm", *args]
    )
    calls = []

    def launch(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr("healthvideo.cli.subprocess.run", launch)
    expected = [
        "pnpm",
        "--dir",
        str(REPO_ROOT / "video"),
        "exec",
        "remotion",
        "studio",
        "src/index.ts",
        "--props",
        str(props.resolve()),
        "--port",
        "3107",
        "--public-dir",
        str(run.resolve()),
        "--no-open",
    ]
    result = CliRunner().invoke(
        app, ["preview", str(project), "--port", "3107", "--print-only"]
    )
    assert result.exit_code == 0, result.output
    assert subprocess.list2cmdline(expected) in result.stdout
    assert "http://localhost:3107" in result.stdout
    assert composition in result.stdout
    assert calls == []
    assert snapshot(project) == before

    result = CliRunner().invoke(app, ["preview", str(project), "--port", "3107"])
    assert result.exit_code == 0, result.output
    assert calls == [(expected, {"check": False, "shell": False})]
    assert snapshot(project) == before


@pytest.mark.parametrize(
    "outcome,code", [(7, 7), (KeyboardInterrupt(), 0), (OSError("missing"), 1)]
)
def test_preview_default_port_and_foreground_exit(tmp_path, monkeypatch, outcome, code):
    project = create_project_fixture(tmp_path, state="rendered")
    before = snapshot(project)
    calls = []

    def launch(argv, **kwargs):
        calls.append(argv)
        if isinstance(outcome, BaseException):
            raise outcome
        return subprocess.CompletedProcess(argv, outcome)

    monkeypatch.setattr("healthvideo.cli.subprocess.run", launch)
    result = CliRunner().invoke(app, ["preview", str(project)])
    assert result.exit_code == code, result.output
    assert "http://localhost:3000" in result.stdout
    assert calls[0][calls[0].index("--port") + 1] == "3000"
    assert snapshot(project) == before


@pytest.mark.parametrize("active", [False, True])
def test_preview_missing_active_render_is_read_only(tmp_path, active):
    project = create_project_fixture(tmp_path, state="idea")
    if active:
        manifest = read_yaml(project / "project.yaml")
        manifest["artifact_hashes"]["production"] = "missing-run"
        write_yaml_atomic(project / "project.yaml", manifest)
    # Never fall back to an old run.
    old = project / "renders" / "old-run"
    old.mkdir()
    (old / "render-input.json").write_text("{}")
    before = snapshot(project)
    result = CliRunner().invoke(app, ["preview", str(project), "--print-only"])
    assert result.exit_code == 1
    assert "Chưa có render" in result.stdout
    assert "produce" in result.stdout
    assert "duyệt y khoa" in result.stdout
    assert snapshot(project) == before
