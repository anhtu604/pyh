from pathlib import Path

import pytest

from healthvideo.storage.backup import build_entries, verify_snapshot_tree


def test_build_entries_hashes_bytes_and_sorts_posix_paths(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "z").mkdir(parents=True)
    (root / "z" / "b.bin").write_bytes(b"two")
    (root / "a.txt").write_bytes(b"one")

    entries = build_entries(root, [root / "z" / "b.bin", root / "a.txt"])

    assert [entry.path for entry in entries] == ["a.txt", "z/b.bin"]
    assert [entry.size for entry in entries] == [3, 3]
    assert entries[0].sha256 == (
        "7692c3ad3540bb803c020b3aee66cd8887123234ea0c6e7143c0add73ff431ed"
    )


@pytest.mark.parametrize("change", ["missing", "extra", "tampered"])
def test_verify_snapshot_tree_refuses_nonidentical_tree(
    tmp_path: Path, change: str
) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    file = root / "project.yaml"
    file.write_bytes(b"project")
    entries = build_entries(root, [file])
    if change == "missing":
        file.unlink()
    elif change == "extra":
        (root / "extra.txt").write_text("extra", encoding="utf-8")
    else:
        file.write_bytes(b"changed")

    with pytest.raises((FileNotFoundError, ValueError), match=change):
        verify_snapshot_tree(root, entries)


def test_verify_snapshot_tree_refuses_symlink(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    target = tmp_path / "outside"
    target.write_text("outside", encoding="utf-8")
    link = root / "project.yaml"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")

    with pytest.raises(ValueError, match="link|reparse"):
        verify_snapshot_tree(root, [])

