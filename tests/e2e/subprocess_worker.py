"""Offline CLI and fake-render worker for process-boundary E2E tests.

Network sockets fail loudly if reached.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

WORKER = Path(__file__).resolve()


def _forbidden(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("offline E2E worker reached a network or provider boundary")


def _render(arguments: list[str]) -> int:
    output = Path(arguments[arguments.index("--output") + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"offline-e2e-mp4")
    return 0


def _cli(arguments: list[str]) -> None:
    from healthvideo import cli
    from healthvideo.workflows import produce

    produce.generate_music = _forbidden
    # Silent fixture WAVs have no pronunciation to assess; keep the process
    # boundary test independent of any installed Whisper runtime/model.
    produce.align_lines = lambda *args, **kwargs: {}
    if arguments and arguments[0] == "produce":
        arguments = [*arguments, "--no-music"]
    cli.resolve_pnpm_argv = lambda args: [sys.executable, str(WORKER), "render", *args]
    cli.main()
    cli.app(args=arguments, prog_name="healthvideo")


def main(argv: list[str]) -> int:
    socket.socket.connect = _forbidden  # type: ignore[method-assign]
    command, *arguments = argv
    if command == "render":
        return _render(arguments)
    if command == "cli":
        _cli(arguments)
    else:
        raise SystemExit(f"unknown worker command: {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
