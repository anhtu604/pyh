import pytest

from healthvideo.storage.files import read_yaml
from healthvideo.workflows.create_project import create_project


def test_create_project_writes_author_brief_and_manifest(tmp_path) -> None:
    project_dir = create_project(tmp_path, "muoi-va-huyet-ap", "Ăn mặn và tăng huyết áp")

    assert read_yaml(project_dir / "project.yaml")["state"] == "idea"
    brief = read_yaml(project_dir / "author-brief.yaml")
    assert brief["title"] == "Ăn mặn và tăng huyết áp"
    assert brief["personal_position"] == ""
    assert (project_dir / "script").is_dir()
    assert (project_dir / "reviews").is_dir()


def test_create_project_rejects_duplicate_slug_without_overwriting_brief(tmp_path) -> None:
    project_dir = create_project(tmp_path, "muoi-va-huyet-ap", "Tiêu đề ban đầu")

    with pytest.raises(FileExistsError, match="Project already exists"):
        create_project(tmp_path, "muoi-va-huyet-ap", "Tiêu đề ghi đè")

    assert read_yaml(project_dir / "author-brief.yaml")["title"] == "Tiêu đề ban đầu"
