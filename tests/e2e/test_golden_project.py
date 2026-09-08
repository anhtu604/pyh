import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import healthvideo.workflows.package as package_workflow
from healthvideo.cli import app
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from tests.helpers import create_project_fixture, synthesize_fixture_audio

GOLDEN_PROJECT = Path(__file__).parents[1] / "fixtures" / "golden-project"


def test_package_contains_video_caption_sources_and_manifest(tmp_path) -> None:
    project = create_project_fixture(tmp_path, state="approved_to_publish")
    output = package_project(project)
    assert (output / "video.mp4").exists()
    assert "[1]" in (output / "caption.txt").read_text(encoding="utf-8")
    assert "R01" in (output / "sources.md").read_text(encoding="utf-8")
    assert '"approval_stale": false' in (output / "manifest.json").read_text(
        encoding="utf-8"
    )


def test_golden_project_runs_from_medical_review_to_publishable_package(
    tmp_path,
) -> None:
    """Walk the golden fixture through both gates and read the published package."""
    project_dir = _copy_golden_project(tmp_path)
    _set_state(project_dir, "awaiting_medical_review")
    runner = CliRunner()

    medical = runner.invoke(
        app, ["review", "medical", str(project_dir), "--reviewer", "BS An", "--yes"]
    )
    video_path = produce_project(project_dir, SilentTTS(), _fake_renderer)
    video = runner.invoke(
        app, ["review", "video", str(project_dir), "--reviewer", "BS An", "--yes"]
    )
    packaged = runner.invoke(app, ["package", str(project_dir)])

    assert (medical.exit_code, video.exit_code, packaged.exit_code) == (0, 0, 0)
    publish_dir = project_dir / "publish"
    assert str(publish_dir) in packaged.stdout
    assert sorted(path.name for path in publish_dir.iterdir()) == [
        "caption.txt",
        "manifest.json",
        "sources.md",
        "video.mp4",
    ]
    assert (publish_dir / "video.mp4").read_bytes() == video_path.read_bytes()

    caption = (publish_dir / "caption.txt").read_text(encoding="utf-8")
    assert "Ăn mặn có thể làm huyết áp tăng." in caption
    assert "không thay thế khám, chẩn đoán hoặc điều trị y khoa" in caption
    assert "[1]" in caption
    assert "[2]" not in caption

    sources = (publish_dir / "sources.md").read_text(encoding="utf-8")
    assert "R01" in sources
    assert "10.0000/synthetic-salt-bp" in sources
    assert "Tôi khuyên bạn giảm dần" not in sources

    manifest = json.loads((publish_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["approval_stale"] is False
    assert manifest["video_approval"]["reviewer"] == "BS An"
    assert manifest["source_markers"] == {"[1]": ["R01"]}
    assert sorted(manifest["artifact_sha256"]) == [
        "caption.txt",
        "render-input.json",
        "sources.md",
        "video.mp4",
    ]
    assert read_yaml(project_dir / "project.yaml")["state"] == "approved_to_publish"


def test_package_refuses_a_project_that_has_not_passed_the_video_gate(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_video_review")

    with pytest.raises(ValueError, match="approved_to_publish"):
        package_project(project_dir)

    assert not (project_dir / "publish").exists()


def test_package_refuses_when_the_video_approval_record_is_missing(tmp_path) -> None:
    """State alone is not evidence of approval: packaging publishes outward."""
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")
    shutil.rmtree(project_dir / "reviews")

    with pytest.raises(FileNotFoundError, match="video approval record"):
        package_project(project_dir)

    assert not (project_dir / "publish").exists()


def test_package_refuses_a_stale_video_approval(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")
    _active_video(project_dir).write_bytes(b"re-rendered-mp4")

    with pytest.raises(ValueError, match="stale"):
        package_project(project_dir)

    assert not (project_dir / "publish").exists()


def test_package_refuses_a_marker_no_evidence_record_backs(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")
    ledger_path = project_dir / "evidence" / "ledger.yaml"
    ledger = read_yaml(ledger_path)
    ledger["claims"][0]["sources"] = []
    write_yaml_atomic(ledger_path, ledger)

    with pytest.raises(ValueError, match="lists no source"):
        package_project(project_dir)

    assert not (project_dir / "publish").exists()


def test_package_replaces_an_earlier_package_in_place(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")
    first = package_project(project_dir)
    (first / "stale-note.txt").write_text("bản cũ", encoding="utf-8")

    second = package_project(project_dir)

    assert second == first
    assert not (second / "stale-note.txt").exists()
    assert (second / "video.mp4").is_file()
    assert _staging_directories(project_dir) == []


def test_package_leaves_no_partial_publish_when_publishing_fails(
    tmp_path, monkeypatch
) -> None:
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")

    def failing_publish(source_dir: Path, destination_dir: Path) -> None:
        raise OSError("volume disappeared")

    monkeypatch.setattr(package_workflow, "replace_directory_atomic", failing_publish)

    with pytest.raises(OSError, match="volume disappeared"):
        package_project(project_dir)

    assert not (project_dir / "publish").exists()
    assert _staging_directories(project_dir) == []


def _copy_golden_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "golden-project"
    shutil.copytree(GOLDEN_PROJECT, project_dir)
    synthesize_fixture_audio(project_dir)
    return project_dir


def _set_state(project_dir: Path, state: str) -> None:
    manifest_path = project_dir / "project.yaml"
    manifest = read_yaml(manifest_path)
    manifest["state"] = state
    write_yaml_atomic(manifest_path, manifest)


def _fake_renderer(argv: list[str]) -> int:
    """Stand in for Remotion so the golden run stays offline and GPU-free."""
    output = Path(argv[argv.index("--output") + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"golden-mp4")
    return 0


def _active_video(project_dir: Path) -> Path:
    manifest = read_yaml(project_dir / "project.yaml")
    return (
        project_dir / "renders" / manifest["artifact_hashes"]["production"] / "video.mp4"
    )


def _staging_directories(project_dir: Path) -> list[Path]:
    return sorted(project_dir.glob(".*package-*"))
