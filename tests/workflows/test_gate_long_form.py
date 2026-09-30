from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.gate_review import GateKind
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate, medical_reviewed_paths
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review_html import render_medical_packet
from tests.helpers import create_long_form_project_fixture, create_v2_project_fixture

REVIEWED_AT = datetime(2026, 9, 30, 9, 0, tzinfo=UTC)
REVIEWER = "BS Nguyễn Văn An"


def _revision(project_dir: Path) -> Path:
    return project_dir / "revisions" / "001"


def test_medical_gate_binds_outline_and_clip_plan(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    record = approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)
    assert {"script/outline.yaml", "script/clip-plan.yaml"} <= record.artifact_hashes.keys()
    assert read_yaml(project_dir / "project.yaml")["state"] == "medically_approved"


def test_medical_gate_requires_clip_plan(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    (_revision(project_dir) / "script" / "clip-plan.yaml").unlink()
    with pytest.raises(FileNotFoundError, match="youtube_long needs script/clip-plan.yaml"):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_medical_review"


def test_medical_gate_blocks_clip_missing_caveat(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    path = _revision(project_dir) / "script" / "clip-plan.yaml"
    plan = read_yaml(path)
    plan["clips"][0].update({"last_scene_id": "S01", "outro_scene_id": "S03"})
    write_yaml_atomic(path, plan)
    with pytest.raises(ValueError, match="CL01: claim C01 requires caveat C02"):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)
    assert not (_revision(project_dir) / "reviews" / "medical-approval.yaml").exists()


def test_medical_gate_blocks_outline_mismatch(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    path = _revision(project_dir) / "script" / "outline.yaml"
    outline = read_yaml(path)
    outline["chapters"][0]["claim_ids"] = []
    write_yaml_atomic(path, outline)
    with pytest.raises(ValueError, match="Scene S01: claim C01 is not planned in chapter CH01"):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)


def test_editing_clip_plan_after_approval_blocks_production(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)
    path = _revision(project_dir) / "script" / "clip-plan.yaml"
    plan = read_yaml(path)
    plan["clips"][1]["title"] = "Đổi sau khi duyệt"
    write_yaml_atomic(path, plan)
    with pytest.raises(ValueError, match="current medical approval"):
        produce_project(project_dir, SilentTTS(), lambda argv: 0)


def test_vertical_project_gate_paths_unchanged(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    paths = medical_reviewed_paths(_revision(project_dir))
    assert "script/outline.yaml" not in paths and "script/clip-plan.yaml" not in paths


def test_medical_packet_shows_outline_and_clips(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    html = render_medical_packet(_revision(project_dir))
    assert "Dàn ý chương" in html and "CH05" in html
    assert "Clip dọc 9:16" in html and "CL01" in html and "S01, S02" in html
