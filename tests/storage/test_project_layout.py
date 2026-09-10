from pathlib import Path

import pytest

from healthvideo.storage.project_layout import resolve_project_layout


def test_reader_resolves_v1_and_v2_artifact_roots() -> None:
    v1 = resolve_project_layout(Path("tests/fixtures/golden-project"))
    v2 = resolve_project_layout(Path("tests/fixtures/golden-project-v2"))

    assert v1.schema_version == "1.0"
    assert v1.artifact_root == v1.project_dir
    assert v2.schema_version == "2.0"
    assert v2.artifact_root == v2.project_dir / "revisions" / "001"


def test_reader_rejects_an_unknown_schema_version(tmp_path: Path) -> None:
    (tmp_path / "project.yaml").write_text(
        "schema_version: '3.0'\nslug: muoi-va-huyet-ap\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Unsupported project schema version"):
        resolve_project_layout(tmp_path)


def test_reader_rejects_a_v2_project_without_its_active_revision(tmp_path: Path) -> None:
    (tmp_path / "project.yaml").write_text(
        "schema_version: '2.0'\nslug: muoi-va-huyet-ap\n", encoding="utf-8"
    )

    with pytest.raises(FileNotFoundError, match="Active revision"):
        resolve_project_layout(tmp_path)
