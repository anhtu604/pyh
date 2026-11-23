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


@pytest.mark.parametrize("winerror", [5, 32])
def test_write_text_atomic_retries_transient_windows_locks_and_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, winerror: int
) -> None:
    path = tmp_path / "code-review.yaml"
    path.write_text("before\n", encoding="utf-8")
    real_replace = files.os.replace
    attempts = 0
    sleeps: list[float] = []

    def flaky_replace(old: Path, new: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts <= 4:
            error = PermissionError("Access is denied" if winerror == 5 else "Sharing violation")
            error.winerror = winerror
            raise error
        real_replace(old, new)

    monkeypatch.setattr(files.os, "replace", flaky_replace)
    monkeypatch.setattr(files.time, "sleep", lambda seconds: sleeps.append(seconds))

    files.write_text_atomic(path, "after\n")

    assert attempts == 5
    assert sleeps == [0.005, 0.015, 0.03, 0.06]
    assert path.read_text(encoding="utf-8") == "after\n"
    assert [item.name for item in tmp_path.iterdir()] == ["code-review.yaml"]


def test_write_text_atomic_exhausts_bounded_retries_and_fails_fast_for_real_perm_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "locked.txt"
    attempts = 0
    sleeps: list[float] = []

    def always_winerror5(old: Path, new: Path) -> None:
        nonlocal attempts
        attempts += 1
        error = PermissionError("Access is denied")
        error.winerror = 5
        raise error

    monkeypatch.setattr(files.os, "replace", always_winerror5)
    monkeypatch.setattr(files.time, "sleep", lambda seconds: sleeps.append(seconds))

    with pytest.raises(PermissionError):
        files.write_text_atomic(path, "new")

    assert attempts == len(files._REPLACE_RETRY_DELAYS)
    assert len(sleeps) == len(files._REPLACE_RETRY_DELAYS) - 1
    assert list(tmp_path.iterdir()) == []

    # Non-5/32 PermissionError must fail immediately without sleeping.
    attempts = 0
    sleeps.clear()

    def posix_perm_error(old: Path, new: Path) -> None:
        nonlocal attempts
        attempts += 1
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(files.os, "replace", posix_perm_error)
    with pytest.raises(PermissionError):
        files.write_text_atomic(path, "new")

    assert attempts == 1
    assert sleeps == []


def test_write_text_atomic_concurrent_readers_and_writers_on_same_file(tmp_path: Path) -> None:
    path = tmp_path / "shared.yaml"
    files.write_yaml_atomic(path, {"step": "init"})
    errors: list[Exception] = []

    def reader() -> None:
        for _ in range(60):
            try:
                data = files.read_yaml(path)
                assert str(data["step"]).startswith(("init", "1-", "2-"))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    def writer(worker_id: int) -> None:
        for idx in range(25):
            try:
                files.write_yaml_atomic(path, {"step": f"{worker_id}-{idx}"})
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(reader), pool.submit(reader), pool.submit(writer, 1), pool.submit(writer, 2)]
        for future in futures:
            future.result()

    assert errors == []
    assert files.read_yaml(path)["step"].startswith(("1-", "2-"))


def test_read_yaml_closes_file_handle_before_safe_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "sample.yaml"
    path.write_text("key: value\n", encoding="utf-8")
    opened_streams = []
    closed_during_parse: list[bool] = []
    real_open = Path.open
    real_safe_load = files.yaml.safe_load

    def tracking_open(self: Path, *args, **kwargs):
        stream = real_open(self, *args, **kwargs)
        if self == path:
            opened_streams.append(stream)
        return stream

    def tracking_safe_load(payload):
        assert isinstance(payload, str)
        assert opened_streams
        closed_during_parse.append(opened_streams[-1].closed)
        return real_safe_load(payload)

    monkeypatch.setattr(Path, "open", tracking_open)
    monkeypatch.setattr(files.yaml, "safe_load", tracking_safe_load)

    assert files.read_yaml(path) == {"key": "value"}
    assert closed_during_parse == [True]


@pytest.mark.parametrize("winerror", [5, 32])
def test_replace_with_retry_survives_eight_transient_windows_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, winerror: int
) -> None:
    source = tmp_path / "source.tmp"
    destination = tmp_path / "dest.yaml"
    source.write_text("new\n", encoding="utf-8")
    destination.write_text("old\n", encoding="utf-8")
    real_replace = files.os.replace
    attempts = 0
    sleeps: list[float] = []

    def flaky_replace(old: Path, new: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts <= 8:
            error = PermissionError("Access is denied" if winerror == 5 else "Sharing violation")
            error.winerror = winerror
            raise error
        real_replace(old, new)

    monkeypatch.setattr(files.os, "replace", flaky_replace)
    monkeypatch.setattr(files.time, "sleep", lambda seconds: sleeps.append(seconds))

    files._replace_with_retry(source, destination)

    assert attempts == 9
    assert sleeps == list(files._REPLACE_RETRY_DELAYS[1:9])
    assert destination.read_text(encoding="utf-8") == "new\n"


def test_rmtree_long_path_removes_deep_directory_tree(tmp_path: Path) -> None:
    import os

    root_dir = tmp_path / "deep-root"
    deep_dir = root_dir / ("a" * 120) / ("b" * 120)
    deep_file = deep_dir / "nested-asset.svg"
    deep_str = files._win_long_path(deep_file)
    assert len(str(deep_file.resolve())) > 260
    os.makedirs(os.path.dirname(deep_str), exist_ok=True)
    with open(deep_str, "w", encoding="utf-8") as handle:
        handle.write("<svg/>")
    assert os.path.isfile(deep_str)

    files.rmtree_long_path(root_dir)
    assert not root_dir.exists()
    assert not os.path.exists(deep_str)
