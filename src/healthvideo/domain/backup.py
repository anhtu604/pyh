"""Backup snapshot manifest: canonical relative paths with size and SHA-256 per file."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_UNPORTABLE = re.compile(r'[\x00-\x1f<>:"\\|?*]')


def canonical_relative_path(value: str) -> str:
    """Return `value` only if it is a portable relative POSIX path with no escape.

    Rejects absolute, drive-qualified, backslash, empty, `.`/`..` segments and
    segments Windows would silently rewrite (trailing dot or space).
    """
    for part in value.split("/"):
        if not part or part != part.rstrip(" .") or _UNPORTABLE.search(part):
            raise ValueError(f"path must be canonical relative POSIX: {value!r}")
    return value


class BackupEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def _canonical_path(cls, value: str) -> str:
        return canonical_relative_path(value)


class BackupManifest(BaseModel):
    """Closed manifest of one immutable snapshot; it lists every file except itself."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    backup_id: str = Field(pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
    project_schema_version: Literal["1.0", "2.0"]
    slug: str = Field(pattern=r"\S")
    active_revision: str | None = Field(pattern=r"^[0-9]{3}$")
    created_at: datetime
    entries: tuple[BackupEntry, ...]

    @field_validator("created_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @field_validator("entries")
    @classmethod
    def _canonical_entries(
        cls, entries: tuple[BackupEntry, ...]
    ) -> tuple[BackupEntry, ...]:
        seen: set[str] = set()
        for entry in entries:
            key = entry.path.casefold()
            if key in seen:
                raise ValueError(f"backup path collision: {entry.path}")
            seen.add(key)
        return tuple(sorted(entries, key=lambda entry: entry.path))
