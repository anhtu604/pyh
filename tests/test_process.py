import json
import os
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from healthvideo import process


def test_bounded_timeout_kills_descendants_and_retains_output(tmp_path):
    written = tmp_path / 'child-finished'
    child = 'import time,pathlib;time.sleep(2);pathlib.Path(' + repr(str(written)) + ').touch()'
    parent = ('import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",'
              + repr(child) + ']);print("partial diagnostic",flush=True);time.sleep(30)')
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        process.run_bounded([sys.executable, '-c', parent], timeout=.5,
                            capture_output=True, text=True)
    assert 'partial diagnostic' in caught.value.output
    time.sleep(2)
    assert not written.exists()


def test_process_identity_rejects_reused_or_dead_pid():
    token = process.process_token(os.getpid())
    assert isinstance(token, str) and token
    assert process.is_same_process(os.getpid(), token)
    assert not process.is_same_process(os.getpid(), token + '-stale')
    assert not process.is_same_process(os.getpid(), None)
    assert process.process_token(-1) is None


def test_identity_rejects_exited_process_even_while_handle_is_open():
    child = subprocess.Popen([sys.executable, '-c', 'pass'])
    child.wait(timeout=5)
    assert process.process_token(child.pid) is None


def test_identity_rejects_exit_259_even_while_handle_is_open():
    child = subprocess.Popen([sys.executable, '-c',
        'import time;print("ready",flush=True);time.sleep(.2);raise SystemExit(259)'],
        stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == 'ready'
        token = process.process_token(child.pid)
        assert token
        child.wait(timeout=5)
        assert process.process_token(child.pid) is None
        assert not process.is_same_process(child.pid, token)
    finally:
        child.stdout.close()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


@pytest.mark.parametrize('timeout', [0, -1, float('inf'), float('nan'), None])
def test_bounded_rejects_unbounded_deadline(timeout):
    with pytest.raises(ValueError, match='positive and finite'):
        process.run_bounded(['never-launched'], timeout=timeout)


def test_bounded_interrupt_kills_owned_process_and_propagates(monkeypatch):
    identities = []

    def interrupt(child, *args, **kwargs):
        identities.append((child.pid, process.process_token(child.pid)))
        raise KeyboardInterrupt()

    monkeypatch.setattr(process.subprocess.Popen, 'communicate', interrupt)
    with pytest.raises(KeyboardInterrupt):
        process.run_bounded([sys.executable, '-c', 'import time;time.sleep(30)'], timeout=5)
    assert identities[0][1]
    assert not process.is_same_process(*identities[0])


def test_posix_timeout_uses_owned_session_and_kills_process_group(monkeypatch):
    killed, options = [], {}

    class Child:
        pid = 12345
        returncode = -9
        stdin = stdout = stderr = None
        calls = 0

        def communicate(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired('isolated', .01, output=b'partial')
            return b'partial', b'detail'

        def poll(self):
            return self.returncode

    def popen(argv, **kwargs):
        options.update(kwargs)
        return Child()

    monkeypatch.setattr(process, 'os', SimpleNamespace(name='posix', killpg=lambda *a: killed.append(a)))
    monkeypatch.setattr(process, 'signal', SimpleNamespace(SIGKILL=9))
    monkeypatch.setattr(process.subprocess, 'Popen', popen)
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        process.run_bounded(['isolated'], timeout=.01, capture_output=True)
    assert options['start_new_session'] is True
    assert killed == [(12345, process.signal.SIGKILL)]
    assert caught.value.output == b'partial' and caught.value.stderr == b'detail'


def test_bounded_preserves_run_input_and_check_contract():
    result = process.run_bounded([sys.executable, '-c', 'import sys;print(input());sys.exit(2)'],
                                 timeout=5, input='hello\n', capture_output=True, text=True)
    assert result.returncode == 2 and result.stdout.strip() == 'hello'
    with pytest.raises(subprocess.CalledProcessError):
        process.run_bounded([sys.executable, '-c', 'raise SystemExit(2)'], timeout=5, check=True)


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
