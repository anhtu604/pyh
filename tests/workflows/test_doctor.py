from pathlib import Path

from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.workflows import doctor
from healthvideo.workflows.doctor import check_environment, check_project_filesystem


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


def test_project_filesystem_probes_pass_and_leave_no_files(tmp_path: Path) -> None:
    project = tmp_path / "project with spaces"
    project.mkdir()
    (project / "existing.txt").write_text("keep", encoding="utf-8")
    results = check_project_filesystem(project)
    assert [(item.name, item.ok) for item in results] == [
        ("exclusive_create", True), ("atomic_rename", True)
    ]
    assert sorted(item.name for item in project.iterdir()) == ["existing.txt"]
    assert (project / "existing.txt").read_text(encoding="utf-8") == "keep"


def test_project_filesystem_refuses_unsupported_exclusive_create(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    original_open = Path.open

    def unsupported(self: Path, mode: str = "r", *args, **kwargs):
        if mode == "x":
            raise OSError("exclusive create unsupported")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", unsupported)
    results = check_project_filesystem(project)
    assert results[0].ok is False
    assert results[0].name == "exclusive_create"
    assert list(project.iterdir()) == []


def test_project_filesystem_refuses_failed_atomic_rename(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    def failed_rename(_source: Path, _destination: Path) -> None:
        raise OSError("atomic rename unsupported")

    monkeypatch.setattr(doctor.os, "replace", failed_rename)
    results = check_project_filesystem(project)
    assert results[1].ok is False
    assert results[1].name == "atomic_rename"
    assert list(project.iterdir()) == []


def test_project_filesystem_cleanup_preserves_foreign_bytes(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    def foreign_rename(source: Path, destination: Path) -> None:
        source.write_bytes(b"foreign bytes")
        raise OSError("rename interrupted")

    monkeypatch.setattr(doctor.os, "replace", foreign_rename)
    results = check_project_filesystem(project)
    assert results[1].ok is False
    assert any(path.read_bytes() == b"foreign bytes" for path in project.iterdir())


def test_project_filesystem_fails_if_probe_cleanup_fails(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    original_unlink = Path.unlink

    def blocked_unlink(self: Path, *args, **kwargs) -> None:
        if self.name.startswith(".healthvideo-doctor-"):
            raise PermissionError("probe file busy")
        original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", blocked_unlink)
    results = check_project_filesystem(project)
    assert all(not item.ok and item.detected == "probe cleanup incomplete" for item in results)
    assert list(project.iterdir())


def test_doctor_cli_checks_project_filesystem_with_spaces(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project with spaces"
    project.mkdir()
    monkeypatch.setattr("healthvideo.cli.check_environment", lambda _run: [])
    result = CliRunner().invoke(app, ["doctor", "--project", str(project)])
    assert result.exit_code == 0, result.stdout
    assert "OK exclusive_create" in result.stdout
    assert "OK atomic_rename" in result.stdout
    assert list(project.iterdir()) == []


def test_doctor_cli_fails_closed_for_missing_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("healthvideo.cli.check_environment", lambda _run: [])
    result = CliRunner().invoke(app, ["doctor", "--project", str(tmp_path / "missing")])
    assert result.exit_code == 1
    assert "FAIL exclusive_create" in result.stdout
    assert "FAIL atomic_rename" in result.stdout
    assert not (tmp_path / "missing").exists()
