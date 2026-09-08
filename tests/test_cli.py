import shutil
from pathlib import Path

from typer.testing import CliRunner

from healthvideo import __version__
from healthvideo.cli import app
from healthvideo.storage.files import read_yaml


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_project_new_creates_project_and_reports_duplicate_without_overwrite(
    tmp_path,
) -> None:
    runner = CliRunner()
    command = [
        "project",
        "new",
        "muoi-va-huyet-ap",
        "--title",
        "Ăn mặn và tăng huyết áp",
        "--root",
        str(tmp_path),
    ]

    created = runner.invoke(app, command)
    duplicate = runner.invoke(app, command)

    assert created.exit_code == 0
    assert (tmp_path / "muoi-va-huyet-ap" / "project.yaml").is_file()
    assert duplicate.exit_code != 0
    assert "Project already exists" in duplicate.stdout
    assert read_yaml(tmp_path / "muoi-va-huyet-ap" / "author-brief.yaml")["title"] == (
        "Ăn mặn và tăng huyết áp"
    )


def test_produce_dry_run_prints_remotion_command_without_changing_state(
    tmp_path,
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "golden-project"
    project_dir = tmp_path / "golden-project"
    shutil.copytree(fixture, project_dir)
    original_manifest = (project_dir / "project.yaml").read_bytes()

    result = CliRunner().invoke(
        app, ["produce", str(project_dir), "--tts", "silent", "--dry-run"]
    )

    assert result.exit_code == 0
    assert "pnpm --dir" in result.stdout
    assert not (project_dir / "renders" / "video.mp4").exists()
    assert (project_dir / "project.yaml").read_bytes() == original_manifest
