import datetime
import hashlib
import json
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


def _hashable_date(value: Any) -> str:
    """Encode YAML dates, and refuse every other value JSON cannot represent.

    Narrow on purpose: a blanket `default=str` would also stringify values with
    no stable text form (a `set` from YAML `!!set` iterates in an order that
    varies with PYTHONHASHSEED), turning "not hashable" into a wrong hash.
    """
    if isinstance(value, datetime.date):  # datetime.datetime is a date subclass
        return str(value)
    raise TypeError(
        f"canonical_json_hash cannot hash {type(value).__name__} deterministically"
    )


def canonical_json_hash(payload: Any) -> str:
    """Hash a payload by meaning: canonical JSON with sorted keys, then SHA-256.

    Dates parsed from YAML are hashed as their string form so a document stays
    hashable without a second scheme; anything else JSON cannot represent
    raises `TypeError` rather than hashing to a value that may not repeat.
    """
    canonical = json.dumps(
        payload,
        default=_hashable_date,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
