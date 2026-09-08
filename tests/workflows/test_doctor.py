from healthvideo.workflows import doctor
from healthvideo.workflows.doctor import check_environment


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


def test_runner_resolves_a_windows_cmd_shim_without_a_shell(monkeypatch) -> None:
    """A bare pnpm command must use its .cmd executable on Windows."""
    captured: list[object] = []

    class Completed:
        returncode = 0
        stdout = "11.19.0\n"
        stderr = ""

    monkeypatch.setattr(doctor.sys, "platform", "win32")
    monkeypatch.setattr(
        doctor.shutil,
        "which",
        lambda name: r"C:\\tools\\pnpm.cmd" if name == "pnpm.cmd" else None,
    )

    def fake_subprocess_run(argv, **kwargs):
        captured.extend([argv, kwargs])
        return Completed()

    monkeypatch.setattr(doctor.subprocess, "run", fake_subprocess_run)

    assert doctor.run_command(["pnpm", "--version"]) == (0, "11.19.0")
    assert captured[0] == [r"C:\\tools\\pnpm.cmd", "--version"]
    assert captured[1]["shell"] is False
