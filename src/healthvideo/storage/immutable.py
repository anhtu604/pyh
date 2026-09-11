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
