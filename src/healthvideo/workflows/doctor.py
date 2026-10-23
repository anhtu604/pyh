"""Local runtime diagnostics for the HealthVideo toolchain."""

import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from healthvideo.audio.music import music_python, music_weights
from healthvideo.process import prepare_subprocess_argv, resolve_pnpm_argv
from healthvideo.visuals.flux import flux_python, flux_weights, validate_flux_weights

REPO_ROOT = Path(__file__).resolve().parents[3]
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
        *_pyh_checks(),
        *_music_checks(),
        *_flux_checks(),
        _projects_check(REPO_ROOT),
        _telegram_check(),
    ]
    return results


def _telegram_check() -> CheckResult:
    from healthvideo.workflows.telegram import configured

    ok = configured()
    return CheckResult('telegram', ok, 'đã cấu hình' if ok else 'chưa cấu hình',
                       'optional', 'Chạy healthvideo notify-setup.')


def _projects_check(root: Path) -> CheckResult:
    """Flag project folders the factory cannot load (old schemas, misplaced nesting)."""
    from healthvideo.domain.project_v2 import ProjectManifestV2

    projects_dir = root / "projects"
    bad: list[str] = []
    for manifest in sorted(projects_dir.rglob("project.yaml")) if projects_dir.is_dir() else []:
        relative = manifest.relative_to(projects_dir)
        if "revisions" in relative.parts:
            continue
        if len(relative.parts) != 2:
            bad.append(f"{relative.parent.as_posix()} (sai vị trí)")
            continue
        try:
            ProjectManifestV2.model_validate(yaml.safe_load(manifest.read_text(encoding="utf-8")))
        except ValueError:
            bad.append(f"{relative.parent.as_posix()} (schema cũ/hỏng)")
    return CheckResult(
        "projects", not bad, "; ".join(bad) or "ok", "recommended",
        "Xóa hoặc chuyển các thư mục này ra khỏi projects/; xưởng sẽ bỏ qua chúng.",
    )


def _flux_checks() -> list[CheckResult]:
    python = flux_python(REPO_ROOT)
    weights = flux_weights(REPO_ROOT)
    ok, detected = True, str(weights)
    try:
        validate_flux_weights(weights)
    except ValueError as error:
        ok, detected = False, str(error)
    return [
        CheckResult("flux_venv", python.is_file(), str(python), "recommended",
                    "Install CUDA torch, diffusers and transformers in cache/flux-venv or set HEALTHVIDEO_FLUX_PYTHON."),
        CheckResult("flux_weights", ok, detected, "recommended",
                    "Install local Apache-2.0 FLUX.2 klein 4B in cache/models/flux2-klein-4b; never use 9B/dev."),
    ]


def _music_checks() -> list[CheckResult]:
    python = music_python(REPO_ROOT)
    weights = music_weights(REPO_ROOT)
    required = (
        "acestep-v15-turbo/model.safetensors",
        "acestep-5Hz-lm-1.7B/model.safetensors",
        "Qwen3-Embedding-0.6B/model.safetensors",
        "vae/diffusion_pytorch_model.safetensors",
        "config.json",
    )
    missing = [name for name in required if not (weights / name).is_file()]
    return [
        CheckResult("music_venv", python.is_file(), str(python), "recommended",
                    "Install ACE-Step in cache/music-venv or set HEALTHVIDEO_MUSIC_PYTHON."),
        CheckResult("music_weights", not missing, str(weights) if not missing else f"missing: {', '.join(missing)}",
                    "recommended", "Install ACE-Step 1.5 turbo, LM 1.7B, text encoder and VAE in cache/models/ace-step-1.5."),
    ]


def _pyh_checks() -> list[CheckResult]:
    skill = REPO_ROOT / ".agents" / "skills" / "pyh" / "SKILL.md"
    command = REPO_ROOT / ".claude" / "commands" / "pyh.md"
    tts = Path(os.environ.get(
        "HEALTHVIDEO_TTS_PYTHON",
        str(REPO_ROOT / "cache" / "tts-venv" / "Scripts" / "python.exe"),
    ))
    skill_ok = False
    try:
        lines = skill.read_text(encoding="utf-8-sig").splitlines()
        if lines and lines[0] == "---":
            end = lines.index("---", 1)
            metadata = yaml.safe_load("\n".join(lines[1:end]))
            skill_ok = (
                isinstance(metadata, dict)
                and metadata.get("name") == "pyh"
                and isinstance(metadata.get("description"), str)
                and bool(metadata["description"].strip())
            )
    except (OSError, UnicodeError, ValueError, yaml.YAMLError):
        pass
    try:
        command_ok = ".agents/skills/pyh/SKILL.md" in command.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        command_ok = False
    return [
        CheckResult(
            "pyh_skill", skill_ok, "valid" if skill_ok else "missing or invalid",
            "required", "Restore .agents/skills/pyh/SKILL.md with name: pyh and a non-empty description in YAML frontmatter.",
        ),
        CheckResult(
            "pyh_claude_command", command_ok, "valid" if command_ok else "missing or invalid",
            "required", "Restore .claude/commands/pyh.md referencing .agents/skills/pyh/SKILL.md.",
        ),
        CheckResult(
            "tts_venv", tts.is_file(), "present" if tts.is_file() else "missing",
            "optional", "Rerun install/install.ps1 without -SkipTts.",
        ),
    ]


def run_command(argv: list[str]) -> tuple[int, str]:
    """Run a diagnostic command with argv, never through a command shell."""
    try:
        if argv and argv[0].casefold() == "pnpm":
            resolved_argv = resolve_pnpm_argv(argv[1:])
        elif len(argv) >= 2 and [item.casefold() for item in argv[:2]] == [
            "corepack",
            "pnpm",
        ]:
            resolved_argv = resolve_pnpm_argv(argv[2:])
        else:
            resolved_argv = prepare_subprocess_argv(argv)
        completed = subprocess.run(
            resolved_argv,
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
    except (OSError, RuntimeError) as error:
        return 1, str(error)
    return completed.returncode, (completed.stdout or completed.stderr).strip()

def has_mandatory_failure(results: list[CheckResult]) -> bool:
    """Return whether a missing mandatory prerequisite blocks the toolchain."""
    return any(not result.ok and result.required not in {"optional", "recommended"} for result in results)


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
