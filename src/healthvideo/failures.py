"""Failure policy shared by tools and workflows; retry budgets belong to callers."""

from __future__ import annotations

import re
import subprocess
from typing import Literal

FailureKind = Literal["transient", "configuration", "agent_error"]
# Five identical consecutive file-contention failures require operator attention.
# Callers persist this count per task/input, never in process-global state.
MAX_FILE_LOCK_FAILURES = 5
_CONFIGURATION = (
    "auto-denied", "permission denied", "access is denied", "unauthorized",
    "authentication failed", "not logged in", "invalid api key",
)
_TRANSIENT = (
    "no capacity available", "high traffic", "code 503", "overloaded",
    "connection reset", "connection refused", "connection timed out",
    "network error", "network is unreachable", "temporary failure", "timed out",
    "econnreset", "enotfound", "rate limit", "quota", "temporarily unavailable",
    "service unavailable",
)


def is_file_contention(value: BaseException | str) -> bool:
    text = str(value).lower()
    return (
        isinstance(value, OSError) and getattr(value, "winerror", None) in {5, 32, 33}
        or any(pattern in text for pattern in (
            "being used by another process", "sharing violation",
        ))
        or bool(re.search(r"\bwinerror\s+(?:5|32|33)\b", text))
        or "access is denied" in text and any(marker in text for marker in (
            "temporary", ".tmp", "rename", "renaming", "unlink", "delete", "deleting",
        ))
    )


def classify_failure(value: BaseException | str, *, consecutive_failures: int = 1) -> FailureKind:
    """Classify without shared state; count includes the current identical failure.

    Bare access/permission denial retains configuration semantics. File contention
    takes precedence over that wording, while missing binaries stay configuration.
    """
    if isinstance(value, FileNotFoundError):
        return "configuration"
    if is_file_contention(value):
        return "configuration" if consecutive_failures >= MAX_FILE_LOCK_FAILURES else "transient"
    text = str(value).lower()
    if (isinstance(value, (ConnectionError, TimeoutError, subprocess.TimeoutExpired))
            or re.search(r"\b(?:429|502|503|504)\b", text)
            or any(pattern in text for pattern in _TRANSIENT)):
        return "transient"
    if isinstance(value, PermissionError) or any(pattern in text for pattern in _CONFIGURATION):
        return "configuration"
    return "agent_error"
