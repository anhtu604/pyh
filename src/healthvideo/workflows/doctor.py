"""Local runtime diagnostics for the HealthVideo toolchain."""

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

RunCommand = Callable[[list[str]], tuple[int, str]]
Version = tuple[int, ...]


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one environment prerequisite check."""

    name: str
    ok: bool
    detected: str
    required: str
    remedy: str


def check_environment(run: RunCommand) -> list[CheckResult]:
    """Check local prerequisites without invoking a command shell."""
    results = [
        _version_check(
            run,
            "python",
            [sys.executable, "--version"],
            (3, 11),
            "Install Python 3.11 or newer and recreate .venv.",
        ),
        _version_check(
            run,
            "node",
            ["node", "--version"],
            (22,),
            "Install Node.js 22 or newer.",
        ),
        _pnpm_check(run),
        _version_check(
            run,
            "ffmpeg",
            ["ffmpeg", "-version"],
            (8,),
            "Install FFmpeg 8 or newer and make it available on PATH.",
        ),
        _font_check(),
        _cuda_check(run),
    ]
    return results


def run_command(argv: list[str]) -> tuple[int, str]:
    """Run a diagnostic command with argv, never through a command shell."""
    resolved_argv = [_resolve_command(argv[0]), *argv[1:]]
    try:
        completed = subprocess.run(
            resolved_argv,
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
    except OSError as error:
        return 1, str(error)
    return completed.returncode, (completed.stdout or completed.stderr).strip()


def _resolve_command(command: str) -> str:
    if sys.platform == "win32":
        return shutil.which(f"{command}.cmd") or command
    return command


def has_mandatory_failure(results: list[CheckResult]) -> bool:
    """Return whether a missing mandatory prerequisite blocks the toolchain."""
    return any(not result.ok and result.required != "optional" for result in results)


def _version_check(
    run: RunCommand,
    name: str,
    argv: list[str],
    minimum: Version,
    remedy: str,
) -> CheckResult:
    code, output = run(argv)
    version = _parse_version(output) if code == 0 else None
    return CheckResult(
        name=name,
        ok=version is not None and version >= minimum,
        detected=_display_version(version, output),
        required=f">={_format_version(minimum)}",
        remedy=remedy,
    )


def _pnpm_check(run: RunCommand) -> CheckResult:
    direct_code, direct_output = run(["pnpm", "--version"])
    if direct_code == 0:
        version = _parse_version(direct_output)
        detected = _display_version(version, direct_output)
    else:
        fallback_code, fallback_output = run(["corepack", "pnpm", "--version"])
        version = _parse_version(fallback_output) if fallback_code == 0 else None
        detected = f"{_display_version(version, fallback_output)} (via corepack)"
    return CheckResult(
        name="pnpm",
        ok=version is not None and version >= (11,),
        detected=detected,
        required=">=11",
        remedy="Install pnpm 11 or newer, or enable it with Corepack.",
    )


def _font_check() -> CheckResult:
    found_font = _find_supported_font()
    return CheckResult(
        name="font",
        ok=found_font is not None,
        detected=found_font or "not found",
        required="Arial or Noto Sans",
        remedy="Install Arial or Noto Sans for readable video text.",
    )


def _cuda_check(run: RunCommand) -> CheckResult:
    code, output = run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    return CheckResult(
        name="cuda",
        ok=code == 0,
        detected=output.splitlines()[0] if code == 0 and output else "not detected",
        required="optional",
        remedy="CUDA is optional; install an NVIDIA driver only for GPU acceleration.",
    )


def _find_supported_font() -> str | None:
    font_directories = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".local" / "share" / "fonts",
    ]
    for directory in font_directories:
        if not directory.is_dir():
            continue
        for font in directory.rglob("*"):
            if not font.is_file():
                continue
            normalized_name = font.stem.casefold().replace(" ", "")
            if normalized_name.startswith("arial"):
                return "Arial"
            if normalized_name.startswith("notosans"):
                return "Noto Sans"
    return None


def _parse_version(output: str) -> Version | None:
    match = re.search(r"\d+(?:\.\d+)+", output)
    if match is None:
        return None
    return tuple(int(part) for part in match.group().split("."))


def _display_version(version: Version | None, output: str) -> str:
    if version is not None:
        return _format_version(version)
    return output.strip() or "not found"


def _format_version(version: Version) -> str:
    return ".".join(str(part) for part in version)
