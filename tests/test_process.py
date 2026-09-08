import subprocess

from healthvideo import process


def test_windows_pnpm_cmd_is_wrapped_by_command_processor(monkeypatch) -> None:
    monkeypatch.setattr(process.sys, "platform", "win32")
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    monkeypatch.setattr(
        process.shutil,
        "which",
        lambda name: r"C:\tools\pnpm.CMD" if name.casefold() == "pnpm" else None,
    )

    argv = process.resolve_pnpm_argv(["--dir", r"C:\work dir\video", "test"])

    assert argv == [
        r"C:\Windows\System32\cmd.exe",
        "/d",
        "/s",
        "/c",
        "call",
        r"C:\tools\pnpm.CMD",
        "--dir",
        r"C:\work dir\video",
        "test",
    ]
    assert subprocess.list2cmdline(argv).endswith(
        r'--dir "C:\work dir\video" test'
    )


def test_pnpm_uses_corepack_fallback_without_a_shell(monkeypatch) -> None:
    monkeypatch.setattr(process.sys, "platform", "linux")
    monkeypatch.setattr(
        process.shutil,
        "which",
        lambda name: "/usr/bin/corepack" if name == "corepack" else None,
    )

    assert process.resolve_pnpm_argv(["--version"]) == [
        "/usr/bin/corepack",
        "pnpm",
        "--version",
    ]


def test_direct_pnpm_executable_is_used_when_available(monkeypatch) -> None:
    monkeypatch.setattr(process.sys, "platform", "win32")
    monkeypatch.setattr(
        process.shutil,
        "which",
        lambda name: r"C:\tools\pnpm.exe" if name.casefold() == "pnpm" else None,
    )

    assert process.resolve_pnpm_argv(["test"]) == [r"C:\tools\pnpm.exe", "test"]
