"""Safe argv preparation for cross-platform subprocess launchers."""

import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

_BATCH_SUFFIXES = {".cmd", ".bat"}


class UnsafeBatchLauncherError(RuntimeError):
    """Raised when argv execution would require the Windows command shell."""


def resolve_pnpm_argv(arguments: Sequence[str]) -> list[str]:
    """Resolve pnpm directly or through Corepack, preserving argv execution."""
    direct = shutil.which("pnpm")
    if direct is not None and not _is_windows_batch(direct):
        return prepare_subprocess_argv([direct, *arguments])

    corepack = shutil.which("corepack")
    if corepack is not None and not _is_windows_batch(corepack):
        return prepare_subprocess_argv([corepack, "pnpm", *arguments])

    if sys.platform == "win32":
        return _resolve_windows_pnpm_argv(arguments, direct, corepack)

    return prepare_subprocess_argv(["pnpm", *arguments])


def prepare_subprocess_argv(argv: Sequence[str]) -> list[str]:
    """Resolve argv[0] while refusing launchers that require a command shell."""
    if not argv:
        raise ValueError("Subprocess argv must not be empty")
    executable = _resolve_executable(argv[0])
    if _is_windows_batch(executable):
        raise UnsafeBatchLauncherError(
            f"Refusing Windows batch launcher without a safe native entrypoint: {executable}"
        )
    return [executable, *argv[1:]]


def _resolve_windows_pnpm_argv(
    arguments: Sequence[str],
    pnpm_shim: str | None,
    corepack_shim: str | None,
) -> list[str]:
    node = shutil.which("node")
    if node is None or _is_windows_batch(node):
        raise UnsafeBatchLauncherError(
            "Cannot launch pnpm safely: install Node.js so node.exe is available on PATH."
        )

    if pnpm_shim is not None:
        pnpm_entrypoint = (
            Path(pnpm_shim).parent / "node_modules" / "pnpm" / "bin" / "pnpm.cjs"
        )
        if pnpm_entrypoint.is_file():
            return [node, str(pnpm_entrypoint), *arguments]

    corepack_roots = [Path(node).parent]
    if corepack_shim is not None:
        corepack_roots.insert(0, Path(corepack_shim).parent)
    for root in dict.fromkeys(corepack_roots):
        corepack_entrypoint = root / "node_modules" / "corepack" / "dist" / "corepack.js"
        if corepack_entrypoint.is_file():
            return [node, str(corepack_entrypoint), "pnpm", *arguments]

    raise UnsafeBatchLauncherError(
        "Cannot launch pnpm safely: no pnpm.cjs or Corepack corepack.js entrypoint was found."
    )


def _is_windows_batch(executable: str) -> bool:
    return (
        sys.platform == "win32"
        and Path(executable).suffix.casefold() in _BATCH_SUFFIXES
    )


def _resolve_executable(command: str) -> str:
    if Path(command).is_absolute():
        return command
    return shutil.which(command) or command
