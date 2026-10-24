"""Load environment variables from a local .env file safely."""

from __future__ import annotations

import os
from pathlib import Path


def child_env() -> dict[str, str]:
    """Agents do not need notification credentials, tokens, secrets or approval PINs."""
    return {key: value for key, value in os.environ.items()
            if not any(word in key.upper()
                       for word in ('TELEGRAM_', 'TOKEN', 'SECRET', 'PIN', 'API_KEY'))}


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
