from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.project import ProjectManifest
from healthvideo.domain.review import ReviewKind
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review import (
    approval_is_stale,
    approve_medical,
    approve_video,
    latest_approval,
)
from tests.helpers import create_project_fixture


def test_medical_approval_binds_script_and_evidence_hash(tmp_path) -> None:
    project = create_project_fixture(tmp_path, state="awaiting_medical_review")
    record = approve_medical(project, reviewer="BS An", note="Đã đối chiếu số liệu")
    assert set(record.artifact_hashes) == {"evidence", "script"}
    assert record.decision == "approved"


def test_video_cannot_be_approved_before_render(tmp_path) -> None:
    project = create_project_fixture(tmp_path, state="awaiting_medical_review")
    with pytest.raises(ValueError, match="awaiting_video_review"):
        approve_video(project, reviewer="BS An", note="")


def test_medical_approval_writes_audit_record_and_advances_state(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_medical_review")

    record = approve_medical(project_dir, reviewer="  BS An  ", note="Đã đối chiếu")

    stored = read_yaml(project_dir / "reviews" / f"medical-{record.id}.yaml")
    assert stored["kind"] == "medical"
    assert stored["reviewer"] == "BS An"
    assert stored["note"] == "Đã đối chiếu"
    assert stored["artifact_hashes"] == dict(record.artifact_hashes)
    assert read_yaml(project_dir / "project.yaml")["state"] == "script_approved"
    assert latest_approval(project_dir, ReviewKind.MEDICAL) == record


def test_medical_approval_timestamp_is_timezone_aware(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_medical_review")
    before = datetime.now(UTC)

    record = approve_medical(project_dir, reviewer="BS An")

    assert record.reviewed_at.tzinfo is not None
    assert record.reviewed_at.utcoffset() is not None
    assert before <= record.reviewed_at <= datetime.now(UTC)
    reloaded = latest_approval(project_dir, ReviewKind.MEDICAL)
    assert reloaded is not None
    assert reloaded.reviewed_at == record.reviewed_at


def test_medical_approval_is_rejected_outside_its_gate(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")

    with pytest.raises(ValueError, match="awaiting_medical_review"):
        approve_medical(project_dir, reviewer="BS An")

    assert list((project_dir / "reviews").glob("*.yaml")) == []


def test_video_approval_binds_render_artifacts_and_advances_state(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_video_review")

    record = approve_video(project_dir, reviewer="BS An", note="Đã xem hết video")

    assert set(record.artifact_hashes) == {"render_input", "video"}
    assert record.kind == "video"
    assert (project_dir / "reviews" / f"video-{record.id}.yaml").is_file()
    assert read_yaml(project_dir / "project.yaml")["state"] == "approved_to_publish"


def test_medical_approval_goes_stale_when_the_script_changes(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_medical_review")
    approve_medical(project_dir, reviewer="BS An")
    assert not approval_is_stale(project_dir, _project(project_dir), ReviewKind.MEDICAL)

    script = read_yaml(project_dir / "script" / "script.yaml")
    script["lines"][0]["text"] = "Ăn mặn luôn làm huyết áp tăng."
    write_yaml_atomic(project_dir / "script" / "script.yaml", script)

    assert approval_is_stale(project_dir, _project(project_dir), ReviewKind.MEDICAL)
    with pytest.raises(ValueError, match="stale"):
        produce_project(project_dir, SilentTTS(), lambda argv: 0)


def test_medical_approval_survives_a_cosmetic_rewrite_of_the_script(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_medical_review")
    approve_medical(project_dir, reviewer="BS An")
    script_path = project_dir / "script" / "script.yaml"

    write_yaml_atomic(script_path, read_yaml(script_path))

    assert not approval_is_stale(project_dir, _project(project_dir), ReviewKind.MEDICAL)


def test_video_approval_goes_stale_when_the_render_changes(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_video_review")
    record = approve_video(project_dir, reviewer="BS An")
    project = _project(project_dir)
    assert not approval_is_stale(project_dir, project, ReviewKind.VIDEO)

    run_dir = project_dir / "renders" / project.artifact_hashes["production"]
    (run_dir / "video.mp4").write_bytes(b"re-rendered-mp4")

    assert approval_is_stale(project_dir, project, ReviewKind.VIDEO)
    assert latest_approval(project_dir, ReviewKind.VIDEO) == record


def test_missing_artifacts_make_an_approval_stale(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_medical_review")
    approve_medical(project_dir, reviewer="BS An")

    (project_dir / "evidence" / "ledger.yaml").unlink()

    assert approval_is_stale(project_dir, _project(project_dir), ReviewKind.MEDICAL)


def test_project_without_review_has_no_stale_approval(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_medical_review")

    assert latest_approval(project_dir, ReviewKind.MEDICAL) is None
    assert not approval_is_stale(project_dir, _project(project_dir), ReviewKind.MEDICAL)


@pytest.mark.parametrize("break_run", ["no_production_hash", "missing_video"])
def test_video_approval_needs_the_published_render(tmp_path, break_run: str) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_video_review")
    project = read_yaml(project_dir / "project.yaml")
    if break_run == "no_production_hash":
        project["artifact_hashes"] = {}
        write_yaml_atomic(project_dir / "project.yaml", project)
    else:
        run_dir = project_dir / "renders" / project["artifact_hashes"]["production"]
        (run_dir / "video.mp4").unlink()

    with pytest.raises(FileNotFoundError, match="video review needs artifacts"):
        approve_video(project_dir, reviewer="BS An")

    assert list((project_dir / "reviews").glob("*.yaml")) == []
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"


def _project(project_dir: Path) -> ProjectManifest:
    return ProjectManifest.model_validate(read_yaml(project_dir / "project.yaml"))
