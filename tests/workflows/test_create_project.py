import pytest

import healthvideo.workflows.create_project as create_project_workflow
from healthvideo.storage.files import read_yaml
from healthvideo.workflows.create_project import create_project


def test_create_project_writes_author_brief_and_manifest(tmp_path) -> None:
    project_dir = create_project(tmp_path, "muoi-va-huyet-ap", "Ăn mặn và tăng huyết áp")

    assert read_yaml(project_dir / "project.yaml")["state"] == "idea"
    brief = read_yaml(project_dir / "author-brief.yaml")
    assert brief["title"] == "Ăn mặn và tăng huyết áp"
    assert brief["personal_position"] == ""
    assert brief["emotion"] == ""
    assert {path.name for path in project_dir.iterdir() if path.is_dir()} == {
        "trend",
        "evidence",
        "script",
        "storyboard",
        "handoffs",
        "audio",
        "assets",
        "renders",
        "reviews",
        "voice-learning",
        "publish",
    }


def test_create_project_rejects_duplicate_slug_without_overwriting_brief(tmp_path) -> None:
    project_dir = create_project(tmp_path, "muoi-va-huyet-ap", "Tiêu đề ban đầu")

    with pytest.raises(FileExistsError, match="Project already exists"):
        create_project(tmp_path, "muoi-va-huyet-ap", "Tiêu đề ghi đè")

    assert read_yaml(project_dir / "author-brief.yaml")["title"] == "Tiêu đề ban đầu"


def test_create_project_cleans_staging_directory_after_write_failure_and_can_retry(
    tmp_path, monkeypatch
) -> None:
    original_write_yaml_atomic = create_project_workflow.write_yaml_atomic
    calls = 0

    def fail_first_write(path, data) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("synthetic write failure")
        original_write_yaml_atomic(path, data)

    monkeypatch.setattr(create_project_workflow, "write_yaml_atomic", fail_first_write)

    with pytest.raises(OSError, match="synthetic write failure"):
        create_project(tmp_path, "muoi-va-huyet-ap", "Ăn mặn và tăng huyết áp")

    assert not (tmp_path / "muoi-va-huyet-ap").exists()
    assert list(tmp_path.glob(".muoi-va-huyet-ap.tmp-*")) == []

    project_dir = create_project(tmp_path, "muoi-va-huyet-ap", "Ăn mặn và tăng huyết áp")

    assert read_yaml(project_dir / "author-brief.yaml")["title"] == "Ăn mặn và tăng huyết áp"
