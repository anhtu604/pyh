from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from healthvideo.storage import files
from healthvideo.storage.files import (
    DirectoryPromotionError,
    canonical_json_hash,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)


def test_atomic_writers_use_unique_owned_temporary_files(tmp_path, monkeypatch) -> None:
    path = tmp_path / "shared.txt"
    seen: list[Path] = []
    real_replace = files.os.replace

    def record_replace(old: Path, new: Path) -> None:
        seen.append(Path(old))
        real_replace(old, new)

    monkeypatch.setattr(files.os, "replace", record_replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda text: files.write_text_atomic(path, text), ["a", "b"]))

    assert len({item.name for item in seen}) == 2
    assert all(item.parent == tmp_path for item in seen)
    assert path.read_text(encoding="utf-8") in {"a", "b"}
    assert not [item for item in tmp_path.iterdir() if item != path]


def test_atomic_write_failure_removes_only_its_owned_temporary(tmp_path, monkeypatch) -> None:
    path = tmp_path / "shared.txt"
    unrelated = tmp_path / ".shared.txt.unrelated.tmp"
    unrelated.write_text("keep", encoding="utf-8")

    def fail_replace(old: Path, new: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(files.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        files.write_text_atomic(path, "new")

    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert sorted(item.name for item in tmp_path.iterdir()) == [unrelated.name]


def test_yaml_round_trip_and_hash(tmp_path) -> None:
    path = tmp_path / "project.yaml"

    write_yaml_atomic(path, {"slug": "muoi-va-huyet-ap", "state": "idea"})

    assert read_yaml(path)["state"] == "idea"
    assert len(sha256_file(path)) == 64
    assert not (tmp_path / "project.yaml.tmp").exists()


def test_canonical_json_hash_keeps_dates_deterministic() -> None:
    """YAML dates stay hashable, and hash by their value."""
    published = canonical_json_hash({"published": date(2026, 9, 7)})

    assert published == canonical_json_hash({"published": date(2026, 9, 7)})
    assert published != canonical_json_hash({"published": date(2026, 9, 8)})
    assert len(canonical_json_hash({"at": datetime(2026, 9, 7, 8, 30, tzinfo=UTC)})) == 64


def test_canonical_json_hash_refuses_values_it_cannot_hash_deterministically() -> None:
    """A YAML !!set stringifies in an order that varies with PYTHONHASHSEED."""
    with pytest.raises(TypeError):
        canonical_json_hash({"tags": {"muoi", "huyet-ap"}})


def test_replace_directory_atomic_preserves_backup_after_promotion_and_restore_fail(
    tmp_path, monkeypatch
) -> None:
    source = tmp_path / "staging"
    destination = tmp_path / "publish"
    source.mkdir()
    destination.mkdir()
    (source / "new.txt").write_text("new", encoding="utf-8")
    (destination / "old.txt").write_text("old", encoding="utf-8")
    real_replace = files.os.replace

    def fail_promotion_and_restore(old: Path, new: Path) -> None:
        if old == source and new == destination:
            raise OSError("promotion failed")
        if old.name.startswith(".publish.superseded-") and new == destination:
            raise OSError("restore failed")
        real_replace(old, new)

    monkeypatch.setattr(files.os, "replace", fail_promotion_and_restore)

    with pytest.raises(DirectoryPromotionError) as raised:
        files.replace_directory_atomic(source, destination)

    backup = next(tmp_path.glob(".publish.superseded-*"))
    assert "promotion failed" in str(raised.value)
    assert "restore failed" in str(raised.value)
    assert str(backup) in str(raised.value)
    assert not destination.exists()
    assert (backup / "old.txt").read_text(encoding="utf-8") == "old"

    monkeypatch.undo()
    files.replace_directory_atomic(source, destination)

    assert (destination / "new.txt").read_text(encoding="utf-8") == "new"
    assert list(tmp_path.glob(".publish.superseded-*")) == []
