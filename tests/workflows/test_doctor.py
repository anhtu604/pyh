from pathlib import Path

import pytest

from healthvideo.workflows import doctor
from healthvideo.workflows.doctor import check_environment


def test_doctor_uses_tts_python_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(doctor, "REPO_ROOT", tmp_path)
    external_python = tmp_path / "external-tts" / "python.exe"
    external_python.parent.mkdir()
    external_python.touch()
    monkeypatch.setenv("HEALTHVIDEO_TTS_PYTHON", str(external_python))
    checks = {item.name: item for item in check_environment(lambda _: (0, "24.14.0"))}
    assert checks["tts_venv"].ok
    external_python.unlink()
    default_python = tmp_path / "cache/tts-venv/Scripts/python.exe"
    default_python.parent.mkdir(parents=True)
    default_python.touch()
    checks = {item.name: item for item in check_environment(lambda _: (0, "24.14.0"))}
    assert not checks["tts_venv"].ok
    monkeypatch.delenv("HEALTHVIDEO_TTS_PYTHON")
    checks = {item.name: item for item in check_environment(lambda _: (0, "24.14.0"))}
    assert checks["tts_venv"].ok


def test_pyh_entry_points_pass_from_repo_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(doctor, "REPO_ROOT", tmp_path, raising=False)
    skill = tmp_path / ".agents/skills/pyh/SKILL.md"
    command = tmp_path / ".claude/commands/pyh.md"
    tts = tmp_path / "cache/tts-venv/Scripts/python.exe"
    for path in (skill, command, tts):
        path.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text('---\nname: pyh\ndescription: >\n  Operate pyh\n---\n', encoding="utf-8")
    command.write_text("Read `.agents/skills/pyh/SKILL.md`.", encoding="utf-8")
    tts.touch()
    checks = {item.name: item for item in check_environment(lambda _: (0, "24.14.0"))}
    for name in ("pyh_skill", "pyh_claude_command", "tts_venv"):
        assert checks[name].ok


@pytest.mark.parametrize("frontmatter", [
    None, "", "name: pyh\ndescription: hi", "---\nname: wrong\ndescription: hi\n---\n",
    "---\nname: pyh\ndescription: '  '\n---\n", "---\nname: [\n---\n",
    "---\n- pyh\n---\n", "---\nname: pyh\ndescription: 42\n---\n",
])
def test_pyh_missing_or_invalid_entries_fail_closed(tmp_path: Path, monkeypatch, frontmatter) -> None:
    monkeypatch.setattr(doctor, "REPO_ROOT", tmp_path, raising=False)
    if frontmatter is not None:
        skill = tmp_path / ".agents/skills/pyh/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(frontmatter, encoding="utf-8")
    checks = {item.name: item for item in check_environment(lambda _: (0, "24.14.0"))}
    assert not checks["pyh_skill"].ok
    assert checks["pyh_skill"].required == "required"
    assert not checks["pyh_claude_command"].ok
    assert checks["pyh_claude_command"].required == "required"
    assert not checks["tts_venv"].ok
    assert checks["tts_venv"].required == "optional"
    assert "-SkipTts" in checks["tts_venv"].remedy
    assert doctor.has_mandatory_failure(list(checks.values()))


def test_pyh_command_must_reference_canonical_skill(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(doctor, "REPO_ROOT", tmp_path, raising=False)
    command = tmp_path / ".claude/commands/pyh.md"
    command.parent.mkdir(parents=True)
    command.write_text("Use a different workflow.", encoding="utf-8")
    checks = {item.name: item for item in check_environment(lambda _: (0, "24.14.0"))}
    assert not checks["pyh_claude_command"].ok


def test_doctor_reports_missing_ffmpeg() -> None:
    """Removing the FFmpeg probe must make the mandatory check fail."""

    def fake_run(argv: list[str]) -> tuple[int, str]:
        return (1, "not found") if argv[0] == "ffmpeg" else (0, "24.14.0")

    results = check_environment(fake_run)

    ffmpeg = next(item for item in results if item.name == "ffmpeg")
    assert ffmpeg.ok is False
    assert "FFmpeg 8" in ffmpeg.remedy


def test_doctor_uses_corepack_when_pnpm_is_not_directly_available() -> None:
    """A missing direct pnpm binary must fall back to Corepack's pnpm."""
    calls: list[list[str]] = []

    def fake_run(argv: list[str]) -> tuple[int, str]:
        calls.append(argv)
        if argv == ["pnpm", "--version"]:
            return 1, "not found"
        if argv == ["corepack", "pnpm", "--version"]:
            return 0, "11.19.0"
        if argv[0] == "nvidia-smi":
            return 1, "not found"
        return 0, "24.14.0"

    results = check_environment(fake_run)

    pnpm = next(item for item in results if item.name == "pnpm")
    assert pnpm.ok is True
    assert pnpm.detected == "11.19.0 (via corepack)"
    assert ["corepack", "pnpm", "--version"] in calls


def test_doctor_rejects_an_outdated_corepack_pnpm() -> None:
    """The fallback must meet the same pnpm 11 minimum as direct pnpm."""

    def fake_run(argv: list[str]) -> tuple[int, str]:
        if argv == ["pnpm", "--version"]:
            return 1, "not found"
        if argv == ["corepack", "pnpm", "--version"]:
            return 0, "10.9.0"
        if argv[0] == "nvidia-smi":
            return 1, "not found"
        return 0, "24.14.0"

    results = check_environment(fake_run)

    pnpm = next(item for item in results if item.name == "pnpm")
    assert pnpm.ok is False
    assert pnpm.detected == "10.9.0 (via corepack)"
    assert pnpm.required == ">=11"


def test_cuda_is_reported_as_an_optional_warning() -> None:
    """A machine without CUDA must remain usable for CPU-only workflows."""

    def fake_run(argv: list[str]) -> tuple[int, str]:
        return (1, "not found") if argv[0] == "nvidia-smi" else (0, "24.14.0")

    results = check_environment(fake_run)

    cuda = next(item for item in results if item.name == "cuda")
    assert cuda.ok is False
    assert cuda.required == "optional"


def test_runner_resolves_windows_pnpm_through_node(tmp_path, monkeypatch) -> None:
    """Putting cmd.exe back in the doctor path must fail this test."""
    captured: list[object] = []

    class Completed:
        returncode = 0
        stdout = "11.19.0\n"
        stderr = ""

    from healthvideo import process

    pnpm_shim = tmp_path / "pnpm.cmd"
    pnpm_shim.write_text("@echo off\r\n", encoding="utf-8")
    node = tmp_path / "node.exe"
    node.write_bytes(b"")
    corepack_shim = tmp_path / "corepack.cmd"
    corepack_shim.write_text("@echo off\r\n", encoding="utf-8")
    corepack_entrypoint = (
        tmp_path / "node_modules" / "corepack" / "dist" / "corepack.js"
    )
    corepack_entrypoint.parent.mkdir(parents=True)
    corepack_entrypoint.write_text("", encoding="utf-8")

    monkeypatch.setattr(process.sys, "platform", "win32")
    monkeypatch.setattr(
        process.shutil,
        "which",
        lambda name: {
            "pnpm": str(pnpm_shim),
            "corepack": str(corepack_shim),
            "node": str(node),
        }.get(name),
    )

    def fake_subprocess_run(argv, **kwargs):
        captured.extend([argv, kwargs])
        return Completed()

    monkeypatch.setattr(doctor.subprocess, "run", fake_subprocess_run)

    assert doctor.run_command(["pnpm", "--version"]) == (0, "11.19.0")
    assert captured[0] == [
        str(node),
        str(corepack_entrypoint),
        "pnpm",
        "--version",
    ]
    assert captured[1]["shell"] is False


def test_runner_reports_when_no_safe_windows_pnpm_launcher(monkeypatch) -> None:
    """Losing every safe entrypoint must produce a diagnostic, not a traceback."""
    from healthvideo import process

    monkeypatch.setattr(process.sys, "platform", "win32")
    monkeypatch.setattr(
        process.shutil,
        "which",
        lambda name: r"C:\tools\pnpm.cmd" if name == "pnpm" else None,
    )

    code, output = doctor.run_command(["pnpm", "--version"])

    assert code == 1
    assert "Cannot launch pnpm safely" in output
