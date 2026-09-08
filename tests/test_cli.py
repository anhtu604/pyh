import shutil
from pathlib import Path

from typer.testing import CliRunner

from healthvideo import __version__
from healthvideo.cli import app
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.produce import produce_project
from tests.helpers import create_project_fixture, synthesize_fixture_audio


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
    synthesize_fixture_audio(project_dir)
    original_manifest = (project_dir / "project.yaml").read_bytes()

    result = CliRunner().invoke(
        app, ["produce", str(project_dir), "--tts", "silent", "--dry-run"]
    )

    assert result.exit_code == 0
    assert "pnpm --dir" in result.stdout
    assert not (project_dir / "renders" / "video.mp4").exists()
    assert (project_dir / "project.yaml").read_bytes() == original_manifest


def test_produce_dry_run_prints_remotion_command_for_a_cache_hit(tmp_path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "golden-project"
    project_dir = tmp_path / "golden-project"
    shutil.copytree(fixture, project_dir)
    synthesize_fixture_audio(project_dir)

    def successful_runner(argv: list[str]) -> int:
        output = Path(argv[argv.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"synthetic-mp4")
        return 0

    produce_project(project_dir, SilentTTS(), successful_runner)
    original_manifest = (project_dir / "project.yaml").read_bytes()

    result = CliRunner().invoke(
        app, ["produce", str(project_dir), "--tts", "silent", "--dry-run"]
    )

    assert result.exit_code == 0
    assert "pnpm --dir" in result.stdout
    assert (project_dir / "project.yaml").read_bytes() == original_manifest


def test_produce_dry_run_rejects_invalid_state_before_printing_command(
    tmp_path,
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "golden-project"
    project_dir = tmp_path / "golden-project"
    shutil.copytree(fixture, project_dir)
    project = read_yaml(project_dir / "project.yaml")
    project["state"] = "idea"
    write_yaml_atomic(project_dir / "project.yaml", project)

    result = CliRunner().invoke(
        app, ["produce", str(project_dir), "--tts", "silent", "--dry-run"]
    )

    assert result.exit_code == 1
    assert "pnpm --dir" not in result.stdout


def test_review_medical_requires_the_typed_confirmation(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_medical_review")

    result = CliRunner().invoke(
        app,
        ["review", "medical", str(project_dir), "--reviewer", "BS An"],
        input="ok\n",
    )

    assert result.exit_code == 1
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_medical_review"
    assert list((project_dir / "reviews").glob("*.yaml")) == []


def test_review_medical_approves_after_the_typed_confirmation(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_medical_review")

    result = CliRunner().invoke(
        app,
        [
            "review",
            "medical",
            str(project_dir),
            "--reviewer",
            "BS An",
            "--note",
            "Đã đối chiếu số liệu",
        ],
        input="APPROVE\n",
    )

    assert result.exit_code == 0
    assert read_yaml(project_dir / "project.yaml")["state"] == "script_approved"
    records = list((project_dir / "reviews").glob("medical-*.yaml"))
    assert len(records) == 1
    assert read_yaml(records[0])["reviewer"] == "BS An"


def test_review_video_with_yes_skips_the_confirmation(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_video_review")

    result = CliRunner().invoke(
        app, ["review", "video", str(project_dir), "--reviewer", "BS An", "--yes"]
    )

    assert result.exit_code == 0
    assert read_yaml(project_dir / "project.yaml")["state"] == "approved_to_publish"
    assert len(list((project_dir / "reviews").glob("video-*.yaml"))) == 1


def test_review_medical_reports_the_state_gate(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")

    result = CliRunner().invoke(
        app, ["review", "medical", str(project_dir), "--reviewer", "BS An", "--yes"]
    )

    assert result.exit_code == 1
    assert "awaiting_medical_review" in result.stdout


def test_status_reports_state_and_a_stale_approval(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_medical_review")
    runner = CliRunner()
    runner.invoke(
        app, ["review", "medical", str(project_dir), "--reviewer", "BS An", "--yes"]
    )

    approved = runner.invoke(app, ["status", str(project_dir)])
    script_path = project_dir / "script" / "script.yaml"
    script = read_yaml(script_path)
    script["title"] = "Ăn mặn và tăng huyết áp — bản sửa"
    write_yaml_atomic(script_path, script)
    stale = runner.invoke(app, ["status", str(project_dir)])

    assert approved.exit_code == 0
    assert "state=script_approved" in approved.stdout
    assert "approval_stale=false" in approved.stdout
    assert "BS An" in approved.stdout
    assert stale.exit_code == 0
    assert "approval_stale=true" in stale.stdout
