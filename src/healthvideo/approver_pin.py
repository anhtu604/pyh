"""Interactive approver PIN storage and verification using scrypt."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from pathlib import Path

from healthvideo.storage.files import write_text_atomic

_PIN_VERSION = 1
_MIN_PIN_LENGTH = 6
_SALT_BYTES = 16
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32


class PinError(ValueError):
    """Raised when setting or resetting an approver PIN fails validation."""


def pin_path() -> Path:
    """Return the default approver PIN file path under the user's home directory."""
    return Path.home() / ".healthvideo" / "approver-pin.json"


def _derive_hash(pin: str, *, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        pin.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=_DKLEN,
    )


def set_pin(
    pin: str,
    *,
    old_pin: str | None = None,
    path: Path | None = None,
) -> None:
    """Set or update the approver PIN atomically."""
    if len(pin) < _MIN_PIN_LENGTH:
        raise PinError(f"PIN must be at least {_MIN_PIN_LENGTH} characters long.")

    target = pin_path() if path is None else path
    if target.exists() and (old_pin is None or not verify_pin(old_pin, path=target)):
        raise PinError("Existing PIN must be verified before setting a new PIN.")

    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _derive_hash(
        pin,
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
    )
    payload = {
        "version": _PIN_VERSION,
        "salt": salt.hex(),
        "hash": digest.hex(),
        "n": _SCRYPT_N,
        "r": _SCRYPT_R,
        "p": _SCRYPT_P,
    }
    write_text_atomic(target, json.dumps(payload, indent=2) + "\n")


def verify_pin(pin: str, *, path: Path | None = None) -> bool:
    """Verify a candidate PIN against the stored scrypt record."""
    target = pin_path() if path is None else path
    if not target.is_file():
        return False

    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("version") != _PIN_VERSION:
            return False
        salt_hex = raw["salt"]
        hash_hex = raw["hash"]
        n = raw["n"]
        r = raw["r"]
        p = raw["p"]
        if not isinstance(salt_hex, str) or not isinstance(hash_hex, str):
            return False
        if (
            not isinstance(n, int)
            or not isinstance(r, int)
            or not isinstance(p, int)
            or isinstance(n, bool)
            or isinstance(r, bool)
            or isinstance(p, bool)
        ):
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        if len(salt) != _SALT_BYTES or len(expected) != _DKLEN:
            return False
        actual = _derive_hash(pin, salt=salt, n=n, r=r, p=p)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False

    return hmac.compare_digest(actual, expected)
