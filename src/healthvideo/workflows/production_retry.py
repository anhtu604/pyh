"""Classify production failures and bound automatic retries per input fingerprint."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml

from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)

MAX_TRANSIENT_ATTEMPTS = 3
TRANSIENT_BACKOFF_SECONDS: dict[int, int] = {
    1: 120,
    2: 600,
}
_SECRET_ENV_KEYS = (
    "VIBI_API_KEY",
    "ELEVENLABS_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "YOUTUBE_API_KEY",
    "NCBI_API_KEY",
)
_CODE_HASH_CACHE: dict[tuple[str, int, int], str] = {}


def _now() -> datetime:
    return datetime.now(UTC)


def _retry_path(root: Path, slug: str) -> Path:
    return root / "topics" / "logs" / slug / "production-retry.yaml"


def _hash_path(path: Path, *, cacheable: bool) -> str:
    if not cacheable:
        return sha256_file(path)
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _CODE_HASH_CACHE.get(key)
    if cached is None:
        cached = sha256_file(path)
        _CODE_HASH_CACHE[key] = cached
    return cached


def production_fingerprint(root: Path, project_dir: Path, state: WorkflowState) -> str:
    """Ignore generated audio/renders/logs; retry validation only after an input fix."""
    paths = {project_dir / "project.yaml"}
    for folder in ("script", "storyboard", "evidence", "explainer", "assets", "posts"):
        paths.update((project_dir / "revisions").glob(f"*/{folder}/**/*.yaml"))
    paths.update((project_dir / "revisions").glob("*/assets/**/*"))
    for relative in (
        "reviews/visual-review.yaml",
        "reviews/visual/candidates.yaml",
        "reviews/medical-approval.yaml",
    ):
        paths.update((project_dir / "revisions").glob(f"*/{relative}"))
    code_root = Path(__file__).resolve().parents[3]
    root_resolved = root.resolve()
    project_resolved = project_dir.resolve()
    for base in {root, code_root}:
        for folder, patterns in (
            ("profiles", ("*.yaml",)),
            ("src/healthvideo", ("*.py",)),
            ("video/src", ("*.ts", "*.tsx")),
        ):
            for pattern in patterns:
                paths.update((base / folder).rglob(pattern))
    files: dict[str, str] = {}
    for path in sorted(paths):
        if not path.is_file():
            continue
        resolved = path.resolve()
        in_work_root = resolved.is_relative_to(root_resolved) or resolved.is_relative_to(
            project_resolved
        )
        files[str(resolved)] = _hash_path(resolved, cacheable=not in_work_root)
    return canonical_json_hash({"state": state.value, "files": files})


def _sanitize_reason(error: Exception) -> str:
    text = " ".join(f"{type(error).__name__}: {error}".split())
    for env_key in _SECRET_ENV_KEYS:
        secret = os.environ.get(env_key, "").strip()
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(
        r"(?i)\b(xi-api-key|api[_-]?key|token|secret|password|authorization)\s*([:=])\s*\S+",
        r"\1\2[REDACTED]",
        text,
    )
    return text or type(error).__name__


def _read_retry_record(path: Path) -> dict[str, Any]:
    try:
        data = read_yaml(path)
        fingerprint = data.get("fingerprint")
        kind = data.get("kind")
        attempts = data.get("attempts")
        reason = data.get("reason")
        retry_after = data.get("retry_after")
    except (OSError, ValueError, TypeError, AttributeError, yaml.YAMLError) as error:
        raise ValueError(
            f"Invalid production retry record in {path}; restore or remove it before retrying"
        ) from error
    if (
        type(fingerprint) is not str
        or not fingerprint.strip()
        or kind not in {"validation", "transient"}
        or type(attempts) is not int
        or attempts < 1
        or type(reason) is not str
        or not reason.strip()
    ):
        raise ValueError(
            f"Invalid production retry record in {path}; restore or remove it before retrying"
        )
    if retry_after is not None:
        if type(retry_after) is not str:
            raise ValueError(
                f"Invalid production retry record in {path}; restore or remove it before retrying"
            )
        try:
            parsed = datetime.fromisoformat(retry_after)
        except ValueError as error:
            raise ValueError(
                f"Invalid production retry record in {path}; restore or remove it before retrying"
            ) from error
        if parsed.tzinfo is None:
            raise ValueError(
                f"Invalid production retry record in {path}; restore or remove it before retrying"
            )
    if kind == "transient" and attempts < MAX_TRANSIENT_ATTEMPTS and retry_after is None:
        raise ValueError(
            f"Invalid production retry record in {path}; restore or remove it before retrying"
        )
    return {
        "fingerprint": fingerprint,
        "kind": kind,
        "attempts": attempts,
        "reason": reason,
        "retry_after": retry_after,
    }


def retry_status(root: Path, project_dir: Path, state: WorkflowState) -> dict[str, Any]:
    """Return whether production may run without making any network calls."""
    path = _retry_path(root, project_dir.name)
    if not path.exists():
        return {
            "allowed": True,
            "kind": None,
            "attempts": 0,
            "reason": None,
            "retry_after": None,
        }
    record = _read_retry_record(path)
    current_fp = production_fingerprint(root, project_dir, state)
    if record["fingerprint"] != current_fp:
        return {
            "allowed": True,
            "kind": None,
            "attempts": 0,
            "reason": None,
            "retry_after": None,
        }
    if record["kind"] == "validation" or record["attempts"] >= MAX_TRANSIENT_ATTEMPTS:
        return {
            "allowed": False,
            "kind": record["kind"],
            "attempts": record["attempts"],
            "reason": record["reason"],
            "retry_after": None,
        }
    retry_after_dt = datetime.fromisoformat(record["retry_after"])
    return {
        "allowed": _now() >= retry_after_dt,
        "kind": "transient",
        "attempts": record["attempts"],
        "reason": record["reason"],
        "retry_after": record["retry_after"],
    }


def record_failure(
    root: Path, project_dir: Path, state: WorkflowState, error: Exception
) -> None:
    """Persist validation hold or bounded transient retry metadata atomically."""
    path = _retry_path(root, project_dir.name)
    existing = _read_retry_record(path) if path.exists() else None
    fingerprint = production_fingerprint(root, project_dir, state)
    kind: Literal["validation", "transient"] = (
        "validation" if isinstance(error, ValueError) else "transient"
    )
    if (
        existing is not None
        and existing["fingerprint"] == fingerprint
        and existing["kind"] == kind
    ):
        attempts = existing["attempts"] + 1
    else:
        attempts = 1
    retry_after: str | None = None
    if kind == "transient" and attempts < MAX_TRANSIENT_ATTEMPTS:
        delay = TRANSIENT_BACKOFF_SECONDS[attempts]
        retry_after = (_now() + timedelta(seconds=delay)).isoformat()
    write_yaml_atomic(
        path,
        {
            "fingerprint": fingerprint,
            "kind": kind,
            "attempts": attempts,
            "reason": _sanitize_reason(error),
            "retry_after": retry_after,
        },
    )


def clear_retry(root: Path, slug: str) -> None:
    """Remove only the production retry record, preserving unrelated block notes."""
    _retry_path(root, slug).unlink(missing_ok=True)
