import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import healthvideo.workflows.package as package_workflow
from healthvideo.cli import app
from healthvideo.domain.review import ReviewKind
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review import (
    approve_medical,
    approve_video,
    latest_approval,
)
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
        "render-input.json",
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
    assert manifest["approval_bindings"]["video"]["reviewer"] == "BS An"
    assert manifest["source_markers"] == {"[1]": ["R01"]}
    assert sorted(manifest["payload_sha256"]) == [
        "caption.txt",
        "render-input.json",
        "sources.md",
        "video.mp4",
    ]
    assert all(
        manifest["payload_sha256"][name] == sha256_file(publish_dir / name)
        for name in manifest["payload_sha256"]
    )
    for kind in (ReviewKind.MEDICAL, ReviewKind.VIDEO):
        approval = latest_approval(project_dir, kind)
        assert approval is not None
        assert manifest["approval_bindings"][kind.value]["approval_sha256"] == (
            canonical_json_hash(approval.model_dump(mode="json"))
        )
    assert read_yaml(project_dir / "project.yaml")["state"] == "approved_to_publish"


def test_package_refuses_a_project_that_has_not_passed_the_video_gate(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_video_review")

    with pytest.raises(ValueError, match="approved_to_publish"):
        package_project(project_dir)

    assert not (project_dir / "publish").exists()


def test_package_refuses_when_the_video_approval_record_is_missing(tmp_path) -> None:
    """State alone is not evidence of approval: packaging publishes outward."""
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")
    for record in (project_dir / "reviews").glob("video-*.yaml"):
        record.unlink()

    with pytest.raises(FileNotFoundError, match="video approval record"):
        package_project(project_dir)

    assert not (project_dir / "publish").exists()


def test_package_refuses_when_the_medical_approval_record_is_missing(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")
    for record in (project_dir / "reviews").glob("medical-*.yaml"):
        record.unlink()

    with pytest.raises(FileNotFoundError, match="medical approval record"):
        package_project(project_dir)

    assert not (project_dir / "publish").exists()


def test_package_refuses_a_stale_video_approval(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")
    _active_video(project_dir).write_bytes(b"re-rendered-mp4")

    with pytest.raises(ValueError, match="stale"):
        package_project(project_dir)

    assert not (project_dir / "publish").exists()


@pytest.mark.parametrize("artifact", ["ledger", "script", "storyboard"])
def test_package_refuses_when_medically_approved_input_changes_after_both_gates(
    tmp_path, artifact: str
) -> None:
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")
    path = {
        "ledger": project_dir / "evidence" / "ledger.yaml",
        "script": project_dir / "script" / "script.yaml",
        "storyboard": project_dir / "storyboard" / "storyboard.yaml",
    }[artifact]
    data = read_yaml(path)
    data["schema_version"] = "1.1"
    write_yaml_atomic(path, data)

    with pytest.raises(ValueError, match="medical approval is stale"):
        package_project(project_dir)

    assert not (project_dir / "publish").exists()


def test_package_refuses_marker_only_shown_by_the_approved_render_input(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")
    _replace_video_approval_after_changing_render_marker(project_dir, "[2]")

    with pytest.raises(ValueError, match=r"Render scene S01 shows \[2\]"):
        package_project(project_dir)

    assert not (project_dir / "publish").exists()


def test_package_checks_each_repeated_render_marker_against_its_script_claim(
    tmp_path,
) -> None:
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")
    render_input_path = _active_video(project_dir).with_name("render-input.json")
    render_input = json.loads(render_input_path.read_text(encoding="utf-8"))
    render_input["scenes"][1]["claim_id"] = "C02"
    render_input_path.write_text(
        json.dumps(render_input, ensure_ascii=False), encoding="utf-8"
    )
    _replace_video_approval(project_dir)

    with pytest.raises(ValueError, match=r"Render scene S02 shows \[1\]"):
        package_project(project_dir)

    assert not (project_dir / "publish").exists()


def test_package_uses_markers_from_the_approved_render_input(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")
    output = package_project(project_dir)

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_markers"] == {"[1]": ["R01"]}
    assert "[1]" in (output / "sources.md").read_text(encoding="utf-8")


def test_package_refuses_a_marker_no_evidence_record_backs(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")
    ledger_path = project_dir / "evidence" / "ledger.yaml"
    ledger = read_yaml(ledger_path)
    ledger["claims"][0]["sources"] = []
    write_yaml_atomic(ledger_path, ledger)
    _replace_approvals(project_dir)

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


@pytest.mark.parametrize("artifact", ["video.mp4", "render-input.json"])
def test_package_rejects_staged_video_artifact_changed_during_copy(
    tmp_path, monkeypatch, artifact: str
) -> None:
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")
    real_copy = shutil.copy2

    def tampering_copy(source: Path, destination: Path) -> Path:
        result = real_copy(source, destination)
        if source.name == artifact:
            if artifact == "video.mp4":
                destination.write_bytes(b"unapproved-video")
            else:
                payload = json.loads(destination.read_text(encoding="utf-8"))
                payload["title"] = "Unapproved render input"
                destination.write_text(json.dumps(payload), encoding="utf-8")
        return result

    monkeypatch.setattr(package_workflow.shutil, "copy2", tampering_copy)

    with pytest.raises(ValueError, match="staged .* approved"):
        package_project(project_dir)

    assert not (project_dir / "publish").exists()


def test_package_uses_approved_medical_snapshots_when_source_mutates_during_copy(
    tmp_path, monkeypatch
) -> None:
    project_dir = create_project_fixture(tmp_path, state="approved_to_publish")
    script_path = project_dir / "script" / "script.yaml"
    approved_text = read_yaml(script_path)["lines"][0]["text"]
    real_copy = shutil.copy2
    mutated = False

    def mutating_copy(source: Path, destination: Path) -> Path:
        nonlocal mutated
        result = real_copy(source, destination)
        if not mutated:
            script = read_yaml(script_path)
            script["lines"][0]["text"] = "UNAPPROVED MUTATION"
            write_yaml_atomic(script_path, script)
            mutated = True
        return result

    monkeypatch.setattr(package_workflow.shutil, "copy2", mutating_copy)

    output = package_project(project_dir)

    caption = (output / "caption.txt").read_text(encoding="utf-8")
    assert approved_text in caption
    assert "UNAPPROVED MUTATION" not in caption


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


def _replace_video_approval_after_changing_render_marker(
    project_dir: Path, marker: str
) -> None:
    render_input_path = _active_video(project_dir).with_name("render-input.json")
    render_input = json.loads(render_input_path.read_text(encoding="utf-8"))
    render_input["scenes"][0]["source_marker"] = marker
    render_input_path.write_text(
        json.dumps(render_input, ensure_ascii=False), encoding="utf-8"
    )
    _replace_video_approval(project_dir)


def _replace_video_approval(project_dir: Path) -> None:
    for record in (project_dir / "reviews").glob("video-*.yaml"):
        record.unlink()
    _set_state(project_dir, "awaiting_video_review")
    approve_video(project_dir, reviewer="BS An")


def _replace_approvals(project_dir: Path) -> None:
    for record in (project_dir / "reviews").glob("*.yaml"):
        record.unlink()
    _set_state(project_dir, "awaiting_medical_review")
    approve_medical(project_dir, reviewer="BS An")
    _set_state(project_dir, "awaiting_video_review")
    approve_video(project_dir, reviewer="BS An")


def _staging_directories(project_dir: Path) -> list[Path]:
    return sorted(project_dir.glob(".*package-*"))
