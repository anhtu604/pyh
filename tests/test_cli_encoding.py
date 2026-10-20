import os
import subprocess
import sys


def test_help_uses_utf8_before_eager_help_without_pythonutf8() -> None:
    env = os.environ.copy()
    env.pop("PYTHONUTF8", None)
    env["PYTHONIOENCODING"] = "cp1252"
    result = subprocess.run(
        [sys.executable, "-c", "from healthvideo.cli import app; app()", "--help"],
        env=env,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert "Các lệnh healthvideo." in result.stdout.decode("utf-8")
