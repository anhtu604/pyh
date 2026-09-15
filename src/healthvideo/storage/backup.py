"""Snapshot tree primitives: hash files into entries, copy them, verify a tree matches."""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import mkdtemp

from healthvideo.domain.backup import BackupEntry
from healthvideo.storage.files import sha256_file

MANIFEST_NAME = "backup-manifest.json"


def is_link_or_reparse(path: Path) -> bool:
    attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _raise(error: OSError) -> None:
    raise error


def tree_files(
    root: Path, *, skip: Callable[[str], bool] = lambda _relative: False
) -> list[str]:
    """List regular files under `root` as sorted POSIX paths.

    Every visited entry must be a plain file or directory: a symlink, junction
    or other reparse point fails closed. `skip` prunes a path from the result
    and stops descent into it, but a skipped entry is still link-checked.
    """
    if is_link_or_reparse(root):
        raise ValueError(f"refusing link or reparse point: {root}")
    files: list[str] = []
    for current, directories, names in os.walk(root, onerror=_raise):
        base = Path(current)
        for name in [*directories, *names]:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if is_link_or_reparse(path):
                raise ValueError(f"refusing link or reparse point: {relative}")
            if name in names and not stat.S_ISREG(os.lstat(path).st_mode):
                raise ValueError(f"refusing non-regular file: {relative}")
        directories[:] = [
            name
            for name in directories
            if not skip((base / name).relative_to(root).as_posix())
        ]
        files += [
            relative
            for name in names
            if not skip(relative := (base / name).relative_to(root).as_posix())
        ]
    return sorted(files)


def build_entries(root: Path, files: Iterable[Path]) -> tuple[BackupEntry, ...]:
    entries = [
        BackupEntry(
            path=file.relative_to(root).as_posix(),
            size=file.stat().st_size,
            sha256=sha256_file(file),
        )
        for file in files
    ]
    return tuple(sorted(entries, key=lambda entry: entry.path))


def copy_entries(
    source_root: Path, destination_root: Path, entries: Iterable[BackupEntry]
) -> None:
    for entry in entries:
        parts = entry.path.split("/")
        target = destination_root.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root.joinpath(*parts), target, follow_symlinks=False)


def verify_snapshot_tree(root: Path, entries: Iterable[BackupEntry]) -> None:
    """Refuse unless `root` holds exactly `entries`, byte for byte, plus its manifest."""
    expected = {entry.path: entry for entry in entries}
    actual = set(tree_files(root, skip=lambda relative: relative == MANIFEST_NAME))
    missing = sorted(expected.keys() - actual)
    if missing:
        raise FileNotFoundError(f"snapshot is missing entries: {', '.join(missing)}")
    extra = sorted(actual - expected.keys())
    if extra:
        raise ValueError(f"snapshot has extra entries: {', '.join(extra)}")
    for path, entry in expected.items():
        file = root.joinpath(*path.split("/"))
        if file.stat().st_size != entry.size or sha256_file(file) != entry.sha256:
            raise ValueError(f"snapshot entry was tampered: {path}")


@contextmanager
def staging_directory(destination: Path) -> Iterator[Path]:
    """Stage beside `destination`; on failure remove it or name it for the operator."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent)
    )
    try:
        yield staging
    except BaseException as error:
        try:
            shutil.rmtree(staging)
        except OSError:
            error.add_note(f"staging retained for operator cleanup: {staging}")
        raise
