from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.revision import RevisionRecord
from healthvideo.storage import revisions as revisions_module
from healthvideo.storage.files import read_yaml
from healthvideo.storage.revisions import create_revision

GOLDEN_V2 = Path("tests/fixtures/golden-project-v2")
GOLDEN_V1 = Path("tests/fixtures/golden-project")
FROZEN_NOW = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)


def copy_golden_v2(root: Path) -> Path:
    destination = root / "golden-project-v2"
    shutil.copytree(GOLDEN_V2, destination)
    return destination


def snapshot_tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_create_revision_preserves_parent_bytes_and_switches_active_revision(
    tmp_path: Path,
) -> None:
    project = copy_golden_v2(tmp_path)
    before = snapshot_tree(project / "revisions" / "001")

    revision = create_revision(project, "Sửa luận điểm", now=FROZEN_NOW)

    assert revision == "002"
    assert snapshot_tree(project / "revisions" / "001") == before
    assert read_yaml(project / "project.yaml")["active_revision"] == "002"


def test_create_revision_copies_only_the_allowed_source_directories(
    tmp_path: Path,
) -> None:
    project = copy_golden_v2(tmp_path)
    parent = project / "revisions" / "001"
    for excluded in ("handoffs", "reviews", "audio", "renders", "publish"):
        (parent / excluded).mkdir()
        (parent / excluded / "example.yaml").write_text("x", encoding="utf-8")

    create_revision(project, "Sửa luận điểm", now=FROZEN_NOW)

    new_revision = project / "revisions" / "002"
    for excluded in ("handoffs", "reviews", "audio", "renders", "publish"):
        assert not (new_revision / excluded).exists()
    for included in ("topic", "author", "evidence", "script", "storyboard", "assets"):
        assert (new_revision / included).is_dir()


def test_create_revision_writes_an_immutable_workflow_record(tmp_path: Path) -> None:
    project = copy_golden_v2(tmp_path)

    create_revision(project, "Sửa luận điểm", now=FROZEN_NOW)

    record = RevisionRecord.model_validate(
        read_yaml(project / "revisions" / "002" / "workflow.yaml")
    )
    assert record.revision == "002"
    assert record.parent_revision == "001"
    assert record.reason == "Sửa luận điểm"
    assert record.created_at == FROZEN_NOW


def test_create_revision_rejects_a_v1_project(tmp_path: Path) -> None:
    project = tmp_path / "golden-project"
    shutil.copytree(GOLDEN_V1, project)

    with pytest.raises(ValueError, match="migrate"):
        create_revision(project, "Sửa luận điểm", now=FROZEN_NOW)


def test_create_revision_cleans_up_staging_when_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = copy_golden_v2(tmp_path)
    before_manifest = (project / "project.yaml").read_bytes()
    before_revision = snapshot_tree(project / "revisions" / "001")

    def failing_copytree(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(revisions_module.shutil, "copytree", failing_copytree)

    with pytest.raises(OSError, match="simulated disk failure"):
        create_revision(project, "Sửa luận điểm", now=FROZEN_NOW)

    assert (project / "project.yaml").read_bytes() == before_manifest
    assert snapshot_tree(project / "revisions" / "001") == before_revision
    assert not (project / "revisions" / "002").exists()
    assert list((project / "revisions").glob(".002-stage-*")) == []


def test_create_revision_cleans_up_staging_when_validation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = copy_golden_v2(tmp_path)
    before_manifest = (project / "project.yaml").read_bytes()
    before_revision = snapshot_tree(project / "revisions" / "001")
    real_copytree = revisions_module.shutil.copytree

    def corrupting_copytree(source: object, destination: object, *args: object, **kwargs: object) -> None:
        real_copytree(source, destination, *args, **kwargs)
        if Path(source).name == "topic":
            (Path(destination) / "card.yaml").write_bytes(b"corrupted-by-test")

    monkeypatch.setattr(revisions_module.shutil, "copytree", corrupting_copytree)

    with pytest.raises(ValueError, match="does not match source bytes"):
        create_revision(project, "Sửa luận điểm", now=FROZEN_NOW)

    assert (project / "project.yaml").read_bytes() == before_manifest
    assert snapshot_tree(project / "revisions" / "001") == before_revision
    assert not (project / "revisions" / "002").exists()
    assert list((project / "revisions").glob(".002-stage-*")) == []


def test_create_revision_refuses_to_replace_an_existing_destination(
    tmp_path: Path,
) -> None:
    project = copy_golden_v2(tmp_path)
    before_manifest = (project / "project.yaml").read_bytes()
    before_revision = snapshot_tree(project / "revisions" / "001")
    collision = project / "revisions" / "002"
    collision.mkdir()
    (collision / "sentinel.txt").write_text("already here", encoding="utf-8")
    before_collision = snapshot_tree(collision)

    with pytest.raises(FileExistsError):
        create_revision(project, "Sửa luận điểm", now=FROZEN_NOW)

    assert (project / "project.yaml").read_bytes() == before_manifest
    assert snapshot_tree(project / "revisions" / "001") == before_revision
    assert snapshot_tree(collision) == before_collision
    assert list((project / "revisions").glob(".002-stage-*")) == []
