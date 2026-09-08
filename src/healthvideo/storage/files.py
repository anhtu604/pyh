import datetime
import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import yaml


class DirectoryPromotionError(OSError):
    """A replacement failed and the recoverable previous directory was retained."""

    def __init__(
        self,
        promotion_error: Exception,
        restore_error: Exception,
        backup_dir: Path,
    ) -> None:
        super().__init__(
            "Directory promotion failed "
            f"({promotion_error}); restoring the previous directory also failed "
            f"({restore_error}). Recoverable backup retained at: {backup_dir}"
        )
        self.promotion_error = promotion_error
        self.restore_error = restore_error
        self.backup_dir = backup_dir


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, Mapping):
        raise TypeError(f"YAML root must be a mapping: {path}")
    return dict(data)


def write_text_atomic(path: Path, text: str) -> None:
    """Write UTF-8 text through a sibling temporary file and one rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary_path, path)


def write_yaml_atomic(path: Path, data: Mapping[str, Any]) -> None:
    write_text_atomic(
        path, yaml.safe_dump(dict(data), allow_unicode=True, sort_keys=False)
    )


def replace_directory_atomic(source_dir: Path, destination_dir: Path) -> None:
    """Publish a staged directory with one rename, replacing what is there.

    ``os.replace`` refuses a non-empty destination directory on Windows, so an
    existing destination is renamed aside first and deleted only once the new
    directory is in place; a failed rename puts the old directory back.
    """
    _recover_missing_destination(destination_dir)
    if not destination_dir.exists():
        os.replace(source_dir, destination_dir)
        return
    superseded = Path(
        mkdtemp(
            prefix=f".{destination_dir.name}.superseded-", dir=destination_dir.parent
        )
    )
    superseded.rmdir()
    os.replace(destination_dir, superseded)
    try:
        os.replace(source_dir, destination_dir)
    except Exception as promotion_error:
        try:
            os.replace(superseded, destination_dir)
        except OSError as restore_error:
            raise DirectoryPromotionError(
                promotion_error, restore_error, superseded
            ) from promotion_error
        raise
    shutil.rmtree(superseded, ignore_errors=True)


def _recover_missing_destination(destination_dir: Path) -> None:
    """Restore the one preserved predecessor before attempting a new promotion."""
    if destination_dir.exists():
        return
    backups = sorted(
        destination_dir.parent.glob(f".{destination_dir.name}.superseded-*")
    )
    if not backups:
        return
    if len(backups) != 1:
        raise FileExistsError(
            "Cannot recover missing directory with multiple preserved backups: "
            + ", ".join(str(backup) for backup in backups)
        )
    os.replace(backups[0], destination_dir)


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
