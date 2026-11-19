"""Shared failure classification and bounded file contention."""
import subprocess

import pytest

from healthvideo.failures import classify_failure


@pytest.mark.parametrize("value,expected", [
    ("being used by another process", "transient"),
    ("sharing violation", "transient"),
    ("Access is denied while renaming temporary file", "transient"),
    ("Access is denied", "configuration"),
    ("HTTP 429", "transient"), ("HTTP 502", "transient"),
    ("HTTP 503", "transient"), ("HTTP 504", "transient"),
    ("rate limit", "transient"), ("quota", "transient"),
    ("temporarily unavailable", "transient"),
    (ConnectionError("offline"), "transient"),
    (TimeoutError("late"), "transient"),
    (subprocess.TimeoutExpired("ffmpeg", 120), "transient"),
    (FileNotFoundError("binary"), "configuration"),
    (PermissionError("permission denied"), "configuration"),
    (RuntimeError("unknown fault"), "agent_error"),
    ("WinError 50", "agent_error"),
    ("WinError 32", "transient"),
])
def test_classify_failure(value, expected):
    assert classify_failure(value) == expected


@pytest.mark.parametrize("code", [5, 32, 33])
@pytest.mark.parametrize("error_type", [OSError, PermissionError])
def test_windows_contention_is_bounded(code, error_type):
    error = error_type("locked")
    error.winerror = code
    assert classify_failure(error, consecutive_failures=4) == "transient"
    assert classify_failure(error, consecutive_failures=5) == "configuration"
