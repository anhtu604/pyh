import json
import shutil
import subprocess

import pytest

from healthvideo import process


def test_windows_pnpm_cmd_uses_node_entrypoint_and_preserves_arguments(
    tmp_path, monkeypatch
) -> None:
    """Routing a pnpm shim back through cmd.exe must fail this test."""
    node = shutil.which("node")
    assert node is not None
    pnpm_shim = tmp_path / "pnpm.cmd"
    pnpm_shim.write_text("@echo off\r\n", encoding="utf-8")
    pnpm_entrypoint = tmp_path / "node_modules" / "pnpm" / "bin" / "pnpm.cjs"
    pnpm_entrypoint.parent.mkdir(parents=True)
    pnpm_entrypoint.write_text(
        "const fs=require('node:fs');"
        "fs.writeFileSync(process.argv[3], JSON.stringify(process.argv.slice(2)));",
        encoding="utf-8",
    )
    output = tmp_path / "captured arguments.json"
    unsafe_looking = r"C:\Health & Science\100%!^ care\Việt Nam"

    monkeypatch.setattr(process.sys, "platform", "win32")
    monkeypatch.setattr(
        process.shutil,
        "which",
        lambda name: str(pnpm_shim) if name == "pnpm" else node if name == "node" else None,
    )

    argv = process.resolve_pnpm_argv([unsafe_looking, str(output)])

    assert argv == [
        node,
        str(pnpm_entrypoint),
        unsafe_looking,
        str(output),
    ]
    subprocess.run(argv, check=True, shell=False)
    assert json.loads(output.read_text(encoding="utf-8")) == [
        unsafe_looking,
        str(output),
    ]


def test_windows_rejects_generic_batch_launchers(monkeypatch) -> None:
    """A generic batch file must never be smuggled through cmd.exe."""
    monkeypatch.setattr(process.sys, "platform", "win32")
    monkeypatch.setattr(
        process.shutil,
        "which",
        lambda name: r"C:\tools\helper.cmd" if name == "helper" else None,
    )

    with pytest.raises(RuntimeError, match="batch launcher"):
        process.prepare_subprocess_argv(["helper", "safe&whoami"])


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
