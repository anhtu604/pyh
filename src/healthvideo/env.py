"""Load environment variables from a local .env file safely."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def background_python() -> str:
    """Return pythonw.exe on Windows when available so background services never allocate a console."""
    exe = Path(sys.executable)
    if sys.platform == 'win32':
        pythonw = exe.with_name('pythonw.exe')
        if pythonw.is_file():
            return str(pythonw)
    return str(exe)


def background_popen_kwargs() -> dict[str, object]:
    """Return Popen keyword arguments for silent background daemons without console allocation."""
    if sys.platform == 'win32':
        return {
            'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            'close_fds': True,
        }
    return {'start_new_session': True}


def hide_child_consoles(*, has_console: bool | None = None) -> None:
    """Ensure child console processes (git, ffmpeg, node, agents) do not flash or open terminal windows.

    A child opened with CREATE_NEW_CONSOLE (the doctor's PIN window) stays visible.
    """
    if sys.platform != 'win32' or getattr(subprocess.Popen, '_hides_console', False):
        return
    if has_console:
        return
    original = subprocess.Popen.__init__

    def init(self, *args, creationflags=0, **kwargs):
        if not creationflags & subprocess.CREATE_NEW_CONSOLE:
            creationflags = (creationflags & ~subprocess.DETACHED_PROCESS) | subprocess.CREATE_NO_WINDOW
        original(self, *args, creationflags=creationflags, **kwargs)

    subprocess.Popen.__init__ = init
    subprocess.Popen._hides_console = True


def child_env() -> dict[str, str]:
    """Agents do not need notification credentials, tokens, secrets or approval PINs."""
    # CLAUDE*/ANTHROPIC_* come from a parent Claude session; a child CLI must use its own login.
    env = {key: value for key, value in os.environ.items()
           if not any(word in key.upper()
                      for word in ('TELEGRAM_', 'TOKEN', 'SECRET', 'PIN', 'API_KEY'))
           and not key.upper().startswith(('CLAUDE', 'ANTHROPIC_'))}
    # Agents call `healthvideo`; it lives beside this interpreter in the venv, not on the user PATH.
    path_key = next((key for key in env if key.upper() == 'PATH'), 'PATH')
    env[path_key] = os.pathsep.join([str(Path(sys.executable).parent), env.get(path_key, '')])
    # Windows pipes default Python child stdio to cp1252 unless UTF-8 mode is requested.
    for var, default in (('PYTHONUTF8', '1'), ('PYTHONIOENCODING', 'utf-8')):
        existing = next((key for key in env if key.upper() == var), None)
        if existing is None or not env[existing]:
            env[existing or var] = default
    return env


def _parse_value(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    if value[0] in {'"', "'"}:
        quote = value[0]
        end_idx = value.find(quote, 1)
        if end_idx != -1:
            trailing = value[end_idx + 1 :].strip()
            if not trailing or trailing.startswith("#"):
                return value[1:end_idx]
    for index, char in enumerate(value):
        if char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value


def load_dotenv(path: Path) -> dict[str, str]:
    """Load KEY=VALUE pairs from ``path`` into ``os.environ`` if not already set.

    Skips blank lines, comment lines starting with ``#``, existing environment
    variables, and any key containing ``PIN`` (case-insensitive). Returns a
    dictionary of the keys that were set.
    """
    if not path.is_file():
        return {}

    loaded: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export ") and "=" in stripped:
            stripped = stripped[len("export ") :].lstrip()
        key, sep, raw_value = stripped.partition("=")
        if not sep:
            continue
        key = key.strip()
        if not key or "pin" in key.lower():
            continue
        value = _parse_value(raw_value)
        if key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded
