from __future__ import annotations

import ctypes
import hashlib
import inspect
import os
import platform
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

import click

from healthvideo.domain.lease import LeaseOwner
from healthvideo.storage.lease import (
    LeaseBusyError,
    WriteLeaseHandle,
    acquire_write_lease,
)

P = ParamSpec("P")
R = TypeVar("R")
DEFAULT_LEASE_TTL_SECONDS = 300
_SELF_START_FALLBACK = f"self-{os.getpid()}-{time.monotonic_ns()}"


def current_time():
    from datetime import datetime

    return datetime.now().astimezone()


def _host_id() -> str:
    raw = platform.node().strip() or "unknown-host"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _windows_process_start(pid: int) -> str | None:
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        creation = ctypes.c_uint64()
        exit_time = ctypes.c_uint64()
        kernel = ctypes.c_uint64()
        user = ctypes.c_uint64()
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        return str(creation.value) if ok else None
    finally:
        kernel32.CloseHandle(handle)


def process_start_fingerprint(pid: int) -> str | None:
    if os.name == "nt":
        return _windows_process_start(pid)
    stat = Path("/proc") / str(pid) / "stat"
    try:
        fields = stat.read_text(encoding="utf-8").split()
    except (FileNotFoundError, PermissionError, OSError):
        return None
    return fields[21] if len(fields) > 21 else None


def current_lease_owner() -> LeaseOwner:
    pid = os.getpid()
    fingerprint = process_start_fingerprint(pid)
    if fingerprint is None:
        fingerprint = _SELF_START_FALLBACK
    return LeaseOwner(
        host_id=_host_id(),
        pid=pid,
        process_start_fingerprint=fingerprint,
    )


@contextmanager
def mutation_lease(project_dir: Path, operation: str) -> Iterator[WriteLeaseHandle]:
    handle = acquire_write_lease(
        project_dir,
        operation=operation,
        active_revision=None,
        owner=current_lease_owner(),
        now=current_time(),
        ttl_seconds=DEFAULT_LEASE_TTL_SECONDS,
    )
    try:
        yield handle
    finally:
        handle.release()


def project_mutation(
    operation: str,
    *,
    skip_when: Callable[[Mapping[str, Any]], bool] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        signature = inspect.signature(function)

        @wraps(function)
        def guarded(*args: P.args, **kwargs: P.kwargs) -> R:
            values = signature.bind(*args, **kwargs).arguments
            if skip_when is not None and skip_when(values):
                return function(*args, **kwargs)
            project_dir = Path(values["project_dir"])
            try:
                with mutation_lease(project_dir, operation):
                    return function(*args, **kwargs)
            except LeaseBusyError as error:
                click.echo(f"Project busy: another writer owns {operation}.")
                raise click.exceptions.Exit(1) from error

        return guarded

    return decorate
