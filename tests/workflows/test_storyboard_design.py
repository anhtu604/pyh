"""Tests for storyboard_validation_error and storyboard_ready diagnostics."""

from pathlib import Path

from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.factory_standards import STYLE_SPEC_FILE, pin_standards
from healthvideo.workflows.storyboard_design import (
    storyboard_ready,
    storyboard_validation_error,
)
from tests.helpers import create_v2_project_fixture

REV = Path("revisions/001")


def test_storyboard_validation_error_none_when_fixture_valid(tmp_path):
    project = create_v2_project_fixture(tmp_path / "projects")
    assert storyboard_validation_error(project) is None
    assert storyboard_ready(project) is True


def test_storyboard_validation_error_surfaces_missing_and_pydantic_failures(tmp_path):
    missing_dir = tmp_path / "no-project"
    missing_dir.mkdir(parents=True, exist_ok=True)
    assert storyboard_validation_error(missing_dir) == "thiếu project.yaml"
    assert storyboard_ready(missing_dir) is False

    project = create_v2_project_fixture(tmp_path / "projects")
    sb_path = project / REV / "storyboard/storyboard.yaml"
    sb_path.unlink()
    assert storyboard_validation_error(project) == "thiếu storyboard/storyboard.yaml"
    assert storyboard_ready(project) is False

    write_yaml_atomic(sb_path, {"schema_version": "1.0", "scenes": "not-a-list"})
    err = storyboard_validation_error(project)
    assert err is not None and err.startswith("storyboard/storyboard.yaml lỗi:")


def test_storyboard_validation_error_surfaces_layout_and_asset_hash_failures(tmp_path):
    project = create_v2_project_fixture(tmp_path / "projects")
    sb_path = project / REV / "storyboard/storyboard.yaml"
    sb_data = read_yaml(sb_path)
    # Remove timing / break scene duration so layout or validation reports concrete cause.
    sb_data["scenes"][0]["duration_frames"] = 0
    write_yaml_atomic(sb_path, sb_data)
    err = storyboard_validation_error(project)
    assert err is not None and (
        "duration_frames" in err or "storyboard/storyboard.yaml lỗi:" in err
    )

    project2 = create_v2_project_fixture(tmp_path / "projects2")
    manifest_path = project2 / REV / "assets/asset-manifest.yaml"
    manifest_data = read_yaml(manifest_path)
    if manifest_data.get("assets"):
        first_asset = manifest_data["assets"][0]
        if first_asset.get("sha256"):
            first_asset["sha256"] = "0" * 64
            write_yaml_atomic(manifest_path, manifest_data)
            hash_err = storyboard_validation_error(project2)
            assert hash_err is not None and "sha256" in hash_err.lower()


def test_storyboard_validation_error_checks_style_a_mascot_pose_when_pinned(tmp_path):
    project = create_v2_project_fixture(tmp_path / "projects")
    spec = tmp_path / STYLE_SPEC_FILE
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("# Style A\n", encoding="utf-8")
    pin_standards(tmp_path, project)

    sb_path = project / REV / "storyboard/storyboard.yaml"
    sb_data = read_yaml(sb_path)
    # On explain_first / non-outro scene with Style A active, bogus mascot_pose fails validation.
    sb_data["scenes"][0]["mascot_pose"] = "nonexistent_pose"
    write_yaml_atomic(sb_path, sb_data)
    err = storyboard_validation_error(project)
    assert err is not None
