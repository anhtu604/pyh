"""Version inspection and safe self-update (detached relaunch) for the PYH dashboard app.

Never runs mutating git commands (no pull/reset/checkout) and never kills active
agent or production jobs.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from healthvideo.company import REPO_ROOT
from healthvideo.env import (
    background_popen_kwargs,
    background_python,
    hide_child_consoles,
)
from healthvideo.process import is_same_process, process_token
from healthvideo.storage.files import write_text_atomic

LATEST_CACHE_TTL_SECONDS = 20.0
DRAIN_POLL_SECONDS = 10.0
UPDATE_LOG_FILE = 'cache/app-update.log'
UPDATE_JOB_FILE = 'cache/app-update-job.json'
UPDATE_PENDING_FILE = 'cache/app-update-pending.json'
TOKEN_FILE = 'cache/dashboard-token.txt'
QUEUED_UPDATE_MESSAGE = 'Sẽ cập nhật ngay khi xưởng làm xong việc đang dở.'

_LATEST_CACHE_LOCK = threading.Lock()
_LATEST_CACHE: dict[Path, tuple[float, dict[str, str | None]]] = {}


def _git_creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0


def read_git_head(
    repo_dir: Path | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, str | None]:
    """Read short hash, commit ISO date, and subject of HEAD without mutating git state."""
    target = (repo_dir or REPO_ROOT).resolve()
    try:
        rev = runner(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=target,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=5,
            check=False,
            shell=False,
            creationflags=_git_creationflags(),
        )
        if rev.returncode != 0:
            return {'hash': None, 'date': None, 'subject': None}
        short_hash = (rev.stdout or '').strip()
        if not short_hash:
            return {'hash': None, 'date': None, 'subject': None}

        log = runner(
            ['git', 'log', '-1', '--format=%cI%x00%s'],
            cwd=target,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=5,
            check=False,
            shell=False,
            creationflags=_git_creationflags(),
        )
        commit_date: str | None = None
        subject: str | None = None
        if log.returncode == 0 and log.stdout:
            parts = log.stdout.strip().split('\x00', 1)
            commit_date = parts[0].strip() or None
            if len(parts) > 1:
                subject = parts[1].strip() or None
        return {'hash': short_hash, 'date': commit_date, 'subject': subject}
    except (OSError, subprocess.SubprocessError, TypeError):
        return {'hash': None, 'date': None, 'subject': None}


def read_running_version(
    repo_dir: Path | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, str | None]:
    """Capture the running app's git hash and commit date once at startup."""
    head = read_git_head(repo_dir, runner=runner)
    return {'hash': head['hash'], 'date': head['date']}


_STARTUP_VERSION: dict[str, str | None] = read_running_version(REPO_ROOT)


def startup_version() -> dict[str, str | None]:
    """Return the version captured once when this process started."""
    return dict(_STARTUP_VERSION)


def clear_latest_cache() -> None:
    """Clear the short-lived HEAD cache (useful in tests)."""
    with _LATEST_CACHE_LOCK:
        _LATEST_CACHE.clear()


def read_latest_version(
    repo_dir: Path | None = None,
    *,
    ttl_seconds: float = LATEST_CACHE_TTL_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, str | None]:
    """Read current repo HEAD with a short TTL cache (<= 30s)."""
    target = (repo_dir or REPO_ROOT).resolve()
    ttl = max(0.0, min(30.0, float(ttl_seconds)))
    now = monotonic()
    with _LATEST_CACHE_LOCK:
        cached = _LATEST_CACHE.get(target)
        if cached is not None and (now - cached[0]) < ttl:
            return dict(cached[1])
    fresh = read_git_head(target, runner=runner)
    with _LATEST_CACHE_LOCK:
        _LATEST_CACHE[target] = (now, dict(fresh))
    return fresh


def pending_update_path(root: Path) -> Path:
    """Return the path to the pending-update marker file."""
    return root / UPDATE_PENDING_FILE


def read_pending_update(root: Path) -> dict[str, Any] | None:
    """Read cache/app-update-pending.json if present and valid, else None."""
    path = pending_update_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    requested_at = data.get('requested_at')
    if not isinstance(requested_at, str) or not requested_at.strip():
        return None
    return {
        'requested_at': requested_at.strip(),
        'restart_factory': bool(data.get('restart_factory', False)),
    }


def update_pending(root: Path) -> bool:
    """Return True when an app update is queued and waiting for the factory to drain."""
    return read_pending_update(root) is not None


def write_pending_update(
    root: Path,
    *,
    restart_factory: bool,
    requested_at: str | None = None,
) -> dict[str, Any]:
    """Atomically persist cache/app-update-pending.json."""
    payload = {
        'requested_at': requested_at or datetime.now(UTC).isoformat(timespec='seconds'),
        'restart_factory': bool(restart_factory),
    }
    write_text_atomic(
        pending_update_path(root),
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
    return payload


def clear_pending_update(root: Path) -> bool:
    """Delete cache/app-update-pending.json if it exists. Returns True if removed."""
    path = pending_update_path(root)
    if not path.exists():
        return False
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def version_payload(
    running: dict[str, str | None],
    *,
    repo_dir: Path | None = None,
    root: Path | None = None,
    ttl_seconds: float = LATEST_CACHE_TTL_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, Any]:
    """Build the GET /api/version response payload."""
    latest = read_latest_version(
        repo_dir,
        ttl_seconds=ttl_seconds,
        monotonic=monotonic,
        runner=runner,
    )
    run_hash = running.get('hash') or None
    lat_hash = latest.get('hash') or None
    update_available = bool(run_hash and lat_hash and run_hash != lat_hash)
    pending = read_pending_update(root) if root is not None else None
    return {
        'running': {
            'hash': run_hash,
            'date': running.get('date') or None,
        },
        'latest': {
            'hash': lat_hash,
            'date': latest.get('date') or None,
            'subject': latest.get('subject') or None,
        },
        'update_available': update_available,
        'update_pending': {'requested_at': pending['requested_at']} if pending else None,
    }


def build_relaunch_argv(
    *,
    argv: list[str] | None = None,
    orig_argv: list[str] | None = None,
    python_exe: str | None = None,
) -> list[str]:
    """Reconstruct the exact command line to relaunch this app using pythonw on Windows."""
    py = python_exe or background_python()
    raw_argv = list(sys.argv if argv is None else argv)
    raw_orig = list(getattr(sys, 'orig_argv', []) if orig_argv is None else orig_argv)

    if raw_orig:
        exe_name = Path(raw_orig[0]).name.lower()
        if exe_name.startswith('python'):
            return [py, *raw_orig[1:]]
        return raw_orig

    if not raw_argv:
        return [py, '-c', 'from healthvideo.cli import app; app()', 'app']

    if raw_argv[0] == '-c':
        return [py, '-c', 'from healthvideo.cli import app; app()', *raw_argv[1:]]

    first = Path(raw_argv[0])
    if first.suffix.lower() == '.exe':
        return raw_argv
    return [py, *raw_argv]


def _append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec='seconds')
    with log_path.open('a', encoding='utf-8') as handle:
        handle.write(f'{stamp} {message}\n')


def _pid_alive(pid: int, token: str | None) -> bool:
    if pid <= 0:
        return False
    if token:
        return is_same_process(pid, token)
    if sys.platform == 'win32':
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == 259  # STILL_ACTIVE
            return False
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def spawn_relaunch_helper(
    *,
    root: Path,
    port: int,
    restart_factory: bool,
    old_pid: int | None = None,
    old_process_token: str | None = None,
    relaunch_argv: list[str] | None = None,
    cwd: Path | None = None,
    popen: Callable[..., Any] = subprocess.Popen,
) -> Path:
    """Write the update job metadata (no tokens) and spawn the detached helper process."""
    resolved_root = root.resolve()
    pid = os.getpid() if old_pid is None else old_pid
    ptoken = process_token(pid) if old_process_token is None else old_process_token
    argv_to_run = build_relaunch_argv() if relaunch_argv is None else list(relaunch_argv)
    work_dir = (cwd or Path.cwd()).resolve()

    job = {
        'old_pid': pid,
        'old_process_token': ptoken,
        'relaunch_argv': argv_to_run,
        'cwd': str(work_dir),
        'root': str(resolved_root),
        'port': int(port),
        'restart_factory': bool(restart_factory),
        'wait_timeout_s': 60,
    }
    job_path = resolved_root / UPDATE_JOB_FILE
    write_text_atomic(job_path, json.dumps(job, ensure_ascii=False, indent=2))

    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parents[2])
    existing_pp = [p for p in env.get('PYTHONPATH', '').split(os.pathsep) if p]
    if src_dir not in existing_pp:
        env['PYTHONPATH'] = os.pathsep.join([src_dir, *existing_pp])

    helper_argv = [
        background_python(),
        '-m',
        'healthvideo.workflows.app_update',
        '--job',
        str(job_path),
    ]
    popen_kwargs: dict[str, Any] = {
        'cwd': str(work_dir),
        'env': env,
        'stdin': subprocess.DEVNULL,
        'stdout': subprocess.DEVNULL,
        'stderr': subprocess.DEVNULL,
        'shell': False,
        **background_popen_kwargs(),
    }
    if sys.platform == 'win32' and popen is subprocess.Popen:
        breakaway = getattr(subprocess, 'CREATE_BREAKAWAY_FROM_JOB', 0x01000000)
        try:
            popen(
                helper_argv,
                **{
                    **popen_kwargs,
                    'creationflags': int(popen_kwargs.get('creationflags', 0)) | breakaway,
                },
            )
            return job_path
        except OSError:
            pass
    popen(helper_argv, **popen_kwargs)
    return job_path


def trigger_app_update(
    *,
    root: Path,
    port: int,
    check_active_jobs: Callable[[], str | None],
    is_factory_running: Callable[[], bool],
    stop_factory: Callable[[], object],
    stop_telegram: Callable[[], object],
    quit_app: Callable[[], object],
    spawn_helper: Callable[..., Path] | None = None,
    restart_factory: bool | None = None,
) -> dict[str, Any]:
    """Queue drain when busy, or stop factory, spawn detached relauncher, and quit cleanly."""
    existing = read_pending_update(root)
    was_factory_running = bool(is_factory_running())
    effective_restart = (
        bool(restart_factory)
        if restart_factory is not None
        else bool(was_factory_running or (existing and existing.get('restart_factory')))
    )

    busy_reason = check_active_jobs()
    if busy_reason:
        pending = write_pending_update(
            root,
            restart_factory=effective_restart,
            requested_at=existing['requested_at'] if existing else None,
        )
        return {
            'queued': True,
            'requested_at': pending['requested_at'],
            'restart_factory': pending['restart_factory'],
            'message': QUEUED_UPDATE_MESSAGE,
        }

    if was_factory_running:
        stop_factory()

    launcher = spawn_relaunch_helper if spawn_helper is None else spawn_helper
    try:
        launcher(
            root=root,
            port=port,
            restart_factory=effective_restart,
        )
    except Exception as exc:
        _append_log(
            root / UPDATE_LOG_FILE,
            f'spawn relaunch helper failed: {type(exc).__name__}: {exc}',
        )
        raise

    with contextlib.suppress(OSError, RuntimeError, ValueError):
        stop_telegram()
    quit_app()
    return {
        'updating': True,
        'restart_factory': effective_restart,
        'message': 'Đang cập nhật code mới và khởi động lại app…',
    }


def process_pending_update(
    *,
    root: Path,
    port: int,
    check_active_jobs: Callable[[], str | None],
    is_factory_running: Callable[[], bool],
    stop_factory: Callable[[], object],
    stop_telegram: Callable[[], object],
    quit_app: Callable[[], object],
    spawn_helper: Callable[..., Path] | None = None,
) -> dict[str, Any] | None:
    """If an update is pending and no active work remains, trigger the update path."""
    pending = read_pending_update(root)
    if pending is None:
        return None
    if check_active_jobs():
        return None
    try:
        result = trigger_app_update(
            root=root,
            port=port,
            check_active_jobs=check_active_jobs,
            is_factory_running=is_factory_running,
            stop_factory=stop_factory,
            stop_telegram=stop_telegram,
            quit_app=quit_app,
            spawn_helper=spawn_helper,
            restart_factory=bool(pending.get('restart_factory', False)),
        )
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        # Keep cache/app-update-pending.json intact; trigger_app_update already logged spawn errors.
        return None
    return result if result.get('updating') else None


def _wait_for_port_ready(
    port: int,
    *,
    timeout_s: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    fetch: Callable[..., Any] = urlopen,
) -> dict[str, Any] | None:
    deadline = monotonic() + max(1.0, float(timeout_s))
    url = f'http://127.0.0.1:{port}/api/version'
    while monotonic() < deadline:
        try:
            with fetch(url, timeout=2) as response:
                if getattr(response, 'status', 200) == 200:
                    raw = response.read().decode('utf-8', errors='replace')
                    return json.loads(raw)
        except (OSError, URLError, ValueError):
            pass
        sleep(0.5)
    return None


def _restart_factory_via_http(
    root: Path,
    port: int,
    *,
    fetch: Callable[..., Any] = urlopen,
) -> tuple[bool, str]:
    token_path = root / TOKEN_FILE
    try:
        token = token_path.read_text(encoding='utf-8').strip()
    except OSError as exc:
        return False, f'không đọc được file token ({type(exc).__name__})'
    if not token:
        return False, 'file token rỗng'
    req = Request(
        f'http://127.0.0.1:{port}/api/factory/start',
        data=b'{}',
        method='POST',
        headers={
            'Host': f'127.0.0.1:{port}',
            'X-Dashboard-Token': token,
            'Content-Type': 'application/json',
        },
    )
    try:
        with fetch(req, timeout=10) as response:
            status = getattr(response, 'status', 200)
            body = response.read().decode('utf-8', errors='replace')
            safe_body = body.replace(token, '[REDACTED]')
            return (200 <= status < 300), f'HTTP {status}: {safe_body[:200]}'
    except HTTPError as exc:
        return False, f'HTTP {exc.code}'
    except (OSError, URLError) as exc:
        safe_exc = str(exc).replace(token, '[REDACTED]')
        return False, f'{type(exc).__name__}: {safe_exc}'


def run_update_job(
    job_path: Path,
    *,
    popen: Callable[..., Any] = subprocess.Popen,
    pid_alive: Callable[[int, str | None], bool] = _pid_alive,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    fetch: Callable[..., Any] = urlopen,
) -> bool:
    """Execute the detached relaunch job: wait for old PID, relaunch app, optionally restart factory."""
    hide_child_consoles()
    job = json.loads(job_path.read_text(encoding='utf-8'))
    root = Path(job['root'])
    log_path = root / UPDATE_LOG_FILE
    old_pid = int(job['old_pid'])
    old_token = job.get('old_process_token')
    relaunch_argv = list(job['relaunch_argv'])
    cwd = job['cwd']
    port = int(job['port'])
    restart_factory = bool(job.get('restart_factory', False))
    wait_timeout = float(job.get('wait_timeout_s', 60))

    _append_log(
        log_path,
        f'start update: old_pid={old_pid} port={port} restart_factory={restart_factory}',
    )

    exit_deadline = monotonic() + 30.0
    while pid_alive(old_pid, old_token) and monotonic() < exit_deadline:
        sleep(0.25)

    if pid_alive(old_pid, old_token):
        _append_log(log_path, f'abort: old_pid={old_pid} still alive after 30s')
        return False

    _append_log(log_path, f'old_pid={old_pid} exited; relaunching app')
    try:
        proc = popen(
            relaunch_argv,
            cwd=cwd,
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            **background_popen_kwargs(),
        )
    except OSError as exc:
        _append_log(log_path, f'relaunch failed: {type(exc).__name__}: {exc}')
        return False

    _append_log(log_path, f'relaunched pid={getattr(proc, "pid", None)}; waiting for port {port}')
    info = _wait_for_port_ready(
        port,
        timeout_s=wait_timeout,
        sleep=sleep,
        monotonic=monotonic,
        fetch=fetch,
    )
    if info is None:
        _append_log(log_path, f'timeout waiting for http://127.0.0.1:{port}/api/version')
        return False

    new_hash = (info.get('running') or {}).get('hash') or 'unknown'
    _append_log(log_path, f'new app ready on port {port}, version={new_hash}')

    if restart_factory:
        ok, detail = _restart_factory_via_http(root, port, fetch=fetch)
        _append_log(log_path, f'restart factory ok={ok} ({detail})')
        with contextlib.suppress(OSError):
            job_path.unlink(missing_ok=True)
        return ok

    with contextlib.suppress(OSError):
        job_path.unlink(missing_ok=True)
    _append_log(log_path, 'update complete')
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='PYH dashboard detached update helper')
    parser.add_argument('--job', required=True, help='Path to app-update-job.json')
    args = parser.parse_args(argv)
    ok = run_update_job(Path(args.job))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
