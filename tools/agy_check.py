"""Fixed verification entry point for headless Antigravity (agy) runs.

agy's CLI allow-list matches whole command lines, so coding agents get exactly
``python tools/agy_check.py`` instead of free-form shell access. It sets
PYTHONPATH to this checkout's ``src`` so worktrees test their own code.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEPS = (
    ("ruff", [sys.executable, "-m", "ruff", "check", "src", "tests"]),
    ("pytest", [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]),
)


def main() -> int:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    failed = [
        name
        for name, argv in STEPS
        if subprocess.run(argv, cwd=ROOT, env=env, check=False).returncode != 0
    ]
    print("AGY_CHECK:", f"FAIL ({', '.join(failed)})" if failed else "PASS", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
