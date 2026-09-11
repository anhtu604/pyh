from pathlib import Path

import pytest
import yaml

from healthvideo.storage.immutable import promote_directory_once, write_yaml_once


def test_write_yaml_once_creates_parent_and_writes_payload(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "record.yaml"

    write_yaml_once(path, {"status": "complete", "count": 3})

    assert path.is_file()
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == {
        "status": "complete",
        "count": 3,
    }


def test_write_yaml_once_refuses_to_overwrite_an_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "record.yaml"
    write_yaml_once(path, {"status": "complete"})
    original = path.read_bytes()

    with pytest.raises(FileExistsError):
        write_yaml_once(path, {"status": "failed"})

    assert path.read_bytes() == original


def test_write_yaml_once_does_not_partially_write_before_failing(tmp_path: Path) -> None:
    path = tmp_path / "record.yaml"
    write_yaml_once(path, {"status": "complete", "note": "original"})
    original = path.read_bytes()

    for _ in range(3):
        with pytest.raises(FileExistsError):
            write_yaml_once(path, {"status": "failed", "note": "replacement"})

    assert path.read_bytes() == original


def test_promote_directory_once_moves_the_staging_directory_into_place(
    tmp_path: Path,
) -> None:
    source = tmp_path / "staging"
    destination = tmp_path / "published"
    source.mkdir()
    (source / "file.txt").write_text("hello", encoding="utf-8")

    promote_directory_once(source, destination)

    assert not source.exists()
    assert (destination / "file.txt").read_text(encoding="utf-8") == "hello"


def test_promote_directory_once_refuses_to_replace_an_existing_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "staging"
    destination = tmp_path / "published"
    source.mkdir()
    (source / "file.txt").write_text("new", encoding="utf-8")
    destination.mkdir()
    (destination / "existing.txt").write_text("old", encoding="utf-8")

    with pytest.raises(FileExistsError):
        promote_directory_once(source, destination)

    assert source.is_dir()
    assert (source / "file.txt").read_text(encoding="utf-8") == "new"
    assert (destination / "existing.txt").read_text(encoding="utf-8") == "old"
    assert not (destination / "file.txt").exists()


def test_promote_directory_once_creates_missing_parent_directories(
    tmp_path: Path,
) -> None:
    source = tmp_path / "staging"
    destination = tmp_path / "nested" / "revisions" / "002"
    source.mkdir()
    (source / "file.txt").write_text("hello", encoding="utf-8")

    promote_directory_once(source, destination)

    assert (destination / "file.txt").read_text(encoding="utf-8") == "hello"
