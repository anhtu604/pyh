"""Safe argv preparation for cross-platform subprocess launchers."""

import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path


def resolve_pnpm_argv(arguments: Sequence[str]) -> list[str]:
    """Resolve pnpm directly or through Corepack, preserving argv execution."""
    direct = shutil.which("pnpm")
    if direct is not None:
        return prepare_subprocess_argv([direct, *arguments])
    corepack = shutil.which("corepack")
    if corepack is not None:
        return prepare_subprocess_argv([corepack, "pnpm", *arguments])
    return prepare_subprocess_argv(["pnpm", *arguments])


def prepare_subprocess_argv(argv: Sequence[str]) -> list[str]:
    """Resolve argv[0] and safely wrap Windows batch launchers with cmd.exe."""
    if not argv:
        raise ValueError("Subprocess argv must not be empty")
    executable = _resolve_executable(argv[0])
    resolved = [executable, *argv[1:]]
    if sys.platform == "win32" and Path(executable).suffix.casefold() in {".cmd", ".bat"}:
        command_processor = os.environ.get("COMSPEC") or shutil.which("cmd.exe") or "cmd.exe"
        return [
            command_processor,
            "/d",
            "/s",
            "/c",
            "call",
            *resolved,
        ]
    return resolved


def _resolve_executable(command: str) -> str:
    if Path(command).is_absolute():
        return command
    return shutil.which(command) or command
