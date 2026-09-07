import hashlib
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, Mapping):
        raise TypeError(f"YAML root must be a mapping: {path}")
    return dict(data)


def write_yaml_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as stream:
        yaml.safe_dump(dict(data), stream, allow_unicode=True, sort_keys=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary_path, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(64 * 1024):
            digest.update(block)
    return digest.hexdigest()
