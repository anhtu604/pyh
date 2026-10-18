from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.gate_review import GateKind
from healthvideo.storage.files import read_yaml
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from tests.helpers import create_long_form_project_fixture

REVIEWED_AT = datetime(2026, 9, 30, 9, 0, tzinfo=UTC)
REVIEWER = "BS Nguyễn Văn An"


def _runner(argv: list[str]) -> int:
    out = Path(argv[argv.index("--output") + 1]) if "--output" in argv else Path(argv[-1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"mp4-" + out.name.encode())
    return 0


def _video_approved(tmp_path: Path) -> Path:
    project_dir = create_long_form_project_fixture(tmp_path)
    approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)
    produce_project(project_dir, SilentTTS(), _runner)
    approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=REVIEWED_AT)
    return project_dir


def test_long_form_runs_from_medical_review_to_packaged(tmp_path: Path) -> None:
    project_dir = _video_approved(tmp_path)
    approval = read_yaml(project_dir / "revisions" / "001" / "reviews" / "video-approval.yaml")
    assert {f"renders/clips/CL0{n}.mp4" for n in (1, 2, 3)} <= approval["artifact_hashes"].keys()

    publish = package_project(project_dir)

    assert read_yaml(project_dir / "project.yaml")["state"] == "packaged"
    assert (publish / "video.mp4").is_file()


def test_package_refuses_clip_changed_after_video_review(tmp_path: Path) -> None:
    project_dir = _video_approved(tmp_path)
    (project_dir / "revisions" / "001" / "renders" / "clips" / "CL02.mp4").write_bytes(b"edited")

    with pytest.raises(ValueError, match="current video approval"):
        package_project(project_dir)
    assert read_yaml(project_dir / "project.yaml")["state"] == "video_approved"
