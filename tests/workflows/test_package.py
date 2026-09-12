import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

import healthvideo.workflows.package as package_workflow
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from tests.helpers import create_v2_project_fixture

NOW = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)


def test_v2_package_refuses_before_video_approval(tmp_path: Path) -> None:
    project_dir = _v2_awaiting_video_review_project(tmp_path)

    with pytest.raises(ValueError, match="video_approved|video approval"):
        package_project(project_dir)

    assert not (_revision_root(project_dir) / "publish").exists()


def test_v2_package_refuses_video_bytes_that_no_longer_match_approval(
    tmp_path: Path,
) -> None:
    project_dir = _v2_video_approved_project(tmp_path)
    (_revision_root(project_dir) / "renders" / "video.mp4").write_bytes(
        b"changed-after-approval"
    )

    with pytest.raises(ValueError, match="video approval"):
        package_project(project_dir)

    assert not (_revision_root(project_dir) / "publish").exists()


def test_v2_package_promotes_payload_then_transitions_to_packaged(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = _v2_video_approved_project(tmp_path)
    resolutions = 0
    real_resolve = package_workflow.resolve_project_layout

    def counting_resolve(path: Path):
        nonlocal resolutions
        resolutions += 1
        return real_resolve(path)

    monkeypatch.setattr(package_workflow, "resolve_project_layout", counting_resolve)

    output = package_project(project_dir)

    assert output == _revision_root(project_dir) / "publish"
    assert {"video.mp4", "caption.txt", "sources.md", "manifest.json"} <= {
        path.name for path in output.iterdir()
    }
    assert read_yaml(project_dir / "project.yaml")["state"] == (
        WorkflowState.PACKAGED.value
    )
    assert resolutions == 1


def test_v2_package_promotion_failure_keeps_state_and_leaves_no_partial_package(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = _v2_video_approved_project(tmp_path)

    def fail_promotion(source_dir: Path, destination_dir: Path) -> None:
        raise OSError("synthetic package promotion failure")

    monkeypatch.setattr(
        package_workflow, "replace_directory_atomic", fail_promotion
    )

    with pytest.raises(OSError, match="promotion failure"):
        package_project(project_dir)

    revision_root = _revision_root(project_dir)
    assert read_yaml(project_dir / "project.yaml")["state"] == (
        WorkflowState.VIDEO_APPROVED.value
    )
    assert not (revision_root / "publish").exists()
    assert list(revision_root.glob(".*.package-*")) == []


def test_v2_package_rejects_render_input_changed_during_copy(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = _v2_video_approved_project(tmp_path)
    real_copy = shutil.copy2

    def tampering_copy(source: Path, destination: Path) -> Path:
        copied = real_copy(source, destination)
        if source.name == "render-input.json":
            payload = json.loads(destination.read_text(encoding="utf-8"))
            payload["title"] = "Unapproved staged render input"
            destination.write_text(json.dumps(payload), encoding="utf-8")
        return copied

    monkeypatch.setattr(package_workflow.shutil, "copy2", tampering_copy)

    with pytest.raises(ValueError, match="staged render_input"):
        package_project(project_dir)

    revision_root = _revision_root(project_dir)
    assert read_yaml(project_dir / "project.yaml")["state"] == "video_approved"
    assert not (revision_root / "publish").exists()
    assert list(revision_root.glob(".*.package-*")) == []


def _v2_awaiting_video_review_project(tmp_path: Path) -> Path:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    storyboard_path = _revision_root(project_dir) / "storyboard" / "storyboard.yaml"
    storyboard = read_yaml(storyboard_path)
    storyboard["scenes"][0]["duration_frames"] = 1350
    write_yaml_atomic(storyboard_path, storyboard)
    approve_gate(
        project_dir,
        GateKind.MEDICAL,
        reviewer="BS Nguyễn Văn An",
        now=NOW,
    )
    produce_project(project_dir, SilentTTS(), _fake_renderer)
    return project_dir


def _v2_video_approved_project(tmp_path: Path) -> Path:
    project_dir = _v2_awaiting_video_review_project(tmp_path)
    approve_gate(
        project_dir,
        GateKind.VIDEO,
        reviewer="BS Nguyễn Văn An",
        now=NOW,
    )
    return project_dir


def _revision_root(project_dir: Path) -> Path:
    return project_dir / "revisions" / "001"


def _fake_renderer(argv: list[str]) -> int:
    output = Path(argv[argv.index("--output") + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"synthetic-v2-mp4")
    return 0
