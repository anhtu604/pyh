"""Offline subprocess worker for the M7 process-boundary E2E tests.

`hold` and `race` report one JSON event per stdout line and wait for parent
commands on stdin, so tests synchronize on pipes, never on sleeps. `cli` runs
the real healthvideo CLI with only Remotion replaced by this worker's `render`
command; network sockets and the Veo transport fail loudly if reached.
"""

from __future__ import annotations

import json
import socket
import sys
from datetime import timedelta
from pathlib import Path

WORKER = Path(__file__).resolve()


def _forbidden(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("offline E2E worker reached a network or provider boundary")


def _emit(event: str) -> None:
    print(json.dumps({"event": event}), flush=True)


def _command() -> str:
    return sys.stdin.readline().strip()


def _render(arguments: list[str]) -> int:
    output = Path(arguments[arguments.index("--output") + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"offline-e2e-mp4")
    return 0


def _cli(arguments: list[str]) -> None:
    from healthvideo import cli
    from healthvideo.video_ai.veo import GoogleVeoTransport

    GoogleVeoTransport.generate = _forbidden  # type: ignore[method-assign]
    cli.resolve_pnpm_argv = lambda args: [sys.executable, str(WORKER), "render", *args]
    cli.main()
    cli.app(args=arguments, prog_name="healthvideo")


def _hold(project: Path, *, expired: bool) -> None:
    from healthvideo.storage.lease import acquire_write_lease
    from healthvideo.workflows.operations import current_lease_owner, current_time

    now = current_time()
    handle = acquire_write_lease(
        project,
        operation="e2e_holder",
        active_revision=None,
        owner=current_lease_owner(),
        now=now - timedelta(hours=1) if expired else now,
        ttl_seconds=5 if expired else 300,
    )
    _emit("ready")
    if _command() == "release":
        handle.release()
        _emit("released")


def _race(project: Path) -> None:
    from healthvideo.storage.lease import LeaseBusyError
    from healthvideo.workflows.operations import mutation_lease

    _emit("armed")
    if _command() != "go":
        raise SystemExit("barrier closed before go")
    try:
        with mutation_lease(project, "e2e_race"):
            _emit("acquired")
            if _command() != "release":
                raise SystemExit("parent closed before release")
    except LeaseBusyError:
        _emit("busy")
        return
    _emit("released")


def main(argv: list[str]) -> int:
    socket.socket.connect = _forbidden  # type: ignore[method-assign]
    command, *arguments = argv
    if command == "render":
        return _render(arguments)
    if command == "cli":
        _cli(arguments)
    elif command == "hold":
        _hold(Path(arguments[0]), expired="--expired" in arguments[1:])
    elif command == "race":
        _race(Path(arguments[0]))
    else:
        raise SystemExit(f"unknown worker command: {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
