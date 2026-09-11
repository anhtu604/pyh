from pathlib import Path

import pytest
import yaml

from healthvideo.storage.immutable import write_yaml_once


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
