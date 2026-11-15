"""Safe argv preparation for cross-platform subprocess launchers."""

import math
import os
import shutil
import signal
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_BATCH_SUFFIXES = {".cmd", ".bat"}
_SUBPROCESS_RUN = subprocess.run


def process_token(pid: int) -> str | None:
    """Return an OS creation identity, never just a reusable PID."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    try:
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes

            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel.WaitForSingleObject.restype = wintypes.DWORD
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)  # QUERY_LIMITED_INFORMATION | SYNCHRONIZE
            if not handle:
                return None
            try:
                # A real exit code of 259 is indistinguishable from STILL_ACTIVE;
                # only an unsignaled process handle proves the process is alive.
                if kernel.WaitForSingleObject(handle, 0) != 0x102:  # WAIT_TIMEOUT
                    return None
                times = [wintypes.FILETIME() for _ in range(4)]
                if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                    return None
                return f'win:{times[0].dwHighDateTime:08x}{times[0].dwLowDateTime:08x}'
            finally:
                kernel.CloseHandle(handle)
        # Linux stat's command may contain spaces and parentheses.
        fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] == 'Z':
            return None
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        return f'linux:{boot}:{fields[19]}'
    except (OSError, ValueError, IndexError):
        return None


def is_same_process(pid: int, token: str | None) -> bool:
    """Fail closed when the process is gone or creation identity cannot be read."""
    return bool(token) and process_token(pid) == token


class _WindowsJob:
    """Contain the suspended child before it can start any descendants."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class Limits(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong),
                        ('PerJobUserTimeLimit', ctypes.c_longlong),
                        ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD),
                        ('SchedulingClass', wintypes.DWORD)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', Limits), ('IoInfo', ctypes.c_ulonglong * 6),
                        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def attach(self, child):
        import ctypes
        from ctypes import wintypes

        if not self.kernel.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(child._handle))):
            raise ctypes.WinError(ctypes.get_last_error())
        # Popen closes the primary thread handle; resume the contained process.
        resume = ctypes.WinDLL('ntdll').NtResumeProcess
        resume.argtypes = [wintypes.HANDLE]
        resume.restype = ctypes.c_long
        if resume(wintypes.HANDLE(int(child._handle))) != 0:
            raise OSError('Could not resume contained subprocess')

    def kill(self):
        self.kernel.TerminateJobObject(self.handle, 1)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def terminate_process_tree(pid: int) -> bool:
    """Force-terminate an external child process tree cleanly; never target self."""
    if not isinstance(pid, int) or pid <= 0 or pid == os.getpid():
        return False
    if os.name == 'nt':
        completed = subprocess.run(
            ['taskkill', '/PID', str(pid), '/T', '/F'],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=15,
        )
        return completed.returncode == 0
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGKILL)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
            return True
        except OSError:
            return False


def run_bounded(argv, *, timeout, on_spawn=None, **subprocess_run_kwargs):
    """Like subprocess.run, with a finite deadline and owned process-tree cleanup."""
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be positive and finite')
    options = dict(subprocess_run_kwargs)
    input_value = options.pop('input', None)
    check = options.pop('check', False)
    if options.pop('capture_output', False):
        if options.get('stdout') is not None or options.get('stderr') is not None:
            raise ValueError('stdout and stderr cannot be used with capture_output')
        options.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if input_value is not None:
        if options.get('stdin') is not None:
            raise ValueError('stdin and input cannot both be used')
        options['stdin'] = subprocess.PIPE
    if options.get('shell'):
        raise ValueError('run_bounded requires shell=False')
    job = _WindowsJob() if os.name == 'nt' else None
    if job:
        options['creationflags'] = options.get('creationflags', 0) | 0x4 | subprocess.CREATE_NO_WINDOW
    else:
        options['start_new_session'] = True
    child = None

    def kill_tree():
        if job:
            job.kill()
        elif child is not None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    try:
        child = subprocess.Popen(argv, **options)
        if job:
            job.attach(child)
        if on_spawn is not None and child.pid:
            on_spawn(child.pid, process_token(child.pid))
        try:
            stdout, stderr = child.communicate(input_value, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            kill_tree()
            stdout, stderr = child.communicate(timeout=5)
            raise subprocess.TimeoutExpired(argv, timeout, output=stdout or error.output,
                                            stderr=stderr or error.stderr) from None
        except BaseException:
            kill_tree()
            child.wait(timeout=5)
            raise
        result = subprocess.CompletedProcess(argv, child.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result
    finally:
        if child is not None and child.poll() is None:
            kill_tree()
            child.kill()  # Also handles failure before Windows job assignment.
            child.wait(timeout=5)
        if job:
            job.close()
        if child is not None:
            for pipe in (child.stdin, child.stdout, child.stderr):
                if pipe is not None:
                    pipe.close()


def run_with_deadline(argv, *, timeout, runner, on_spawn=None, **kwargs):
    """Preserve injected run-style adapters while containing real subprocesses."""
    if runner is _SUBPROCESS_RUN:
        return run_bounded(argv, timeout=timeout, on_spawn=on_spawn, **kwargs)
    return runner(argv, timeout=timeout, **kwargs)


def timeout_diagnostic(error: subprocess.TimeoutExpired) -> str:
    """Decode partial diagnostics without including argv (which may hold secrets)."""
    def decode(value):
        return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''

    return f'timed out after {error.timeout}s: {decode(error.output)}{decode(error.stderr)}'


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
