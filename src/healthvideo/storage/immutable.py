"""Write-once storage primitives so a published record can never be overwritten."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml


def write_yaml_once(path: Path, payload: Mapping[str, Any]) -> None:
    """Create ``path`` with ``payload`` as YAML, refusing to replace an existing file.

    The file is opened exclusively (``"x"`` mode), so a second writer
    targeting the same path fails with ``FileExistsError`` before a single
    byte of the existing file changes. A completed write is flushed and
    ``fsync``-ed so the bytes on disk survive a crash right after the call.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = yaml.safe_dump(dict(payload), allow_unicode=True, sort_keys=False)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized)
        stream.flush()
        os.fsync(stream.fileno())


def promote_directory_once(source_dir: Path, destination_dir: Path) -> None:
    """Publish a staged directory at ``destination_dir`` with a single rename.

    Refuses to replace an existing destination: if ``destination_dir`` already
    exists this raises ``FileExistsError`` before anything is touched, leaving
    both ``source_dir`` and ``destination_dir`` byte-unchanged. This is the
    directory-level counterpart to ``write_yaml_once`` — a completed record
    can never be silently overwritten by a second promotion.

    ``source_dir`` must be a sibling of ``destination_dir`` (same parent, same
    volume) so the promotion is one atomic rename rather than a copy.
    """
    if destination_dir.exists():
        raise FileExistsError(
            f"Refusing to replace an existing directory: {destination_dir}"
        )
    destination_dir.parent.mkdir(parents=True, exist_ok=True)
    os.rename(source_dir, destination_dir)
