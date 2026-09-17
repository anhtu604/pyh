"""Keep the M7 operator instructions tied to the public CLI."""

import re
import shlex
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from healthvideo.cli import app

RUNBOOK = Path("docs/operations/m7-hardening-runbook.md")
COMMAND_PREFIX = r"& .venv\Scripts\healthvideo.exe "
GROUPS = {"operator", "lease", "backup"}


def test_every_documented_healthvideo_command_exists() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    commands = [line.removeprefix(COMMAND_PREFIX) for line in text.splitlines() if line.startswith(COMMAND_PREFIX)]
    assert len(commands) >= 8
    runner = CliRunner()
    for command in commands:
        args = shlex.split(command)
        path = args[:2] if args[0] in GROUPS else args[:1]
        result = runner.invoke(app, [*path, "--help"])
        assert result.exit_code == 0, (command, result.stdout)
        for option in re.findall(r"(?<!\w)--[a-z][a-z-]*", command):
            assert option in result.stdout, (command, option)


def test_documented_git_audit_commands_run_read_only() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    commands = [line for line in text.splitlines() if line.startswith("git ")]
    assert commands == ["git status --short", "git diff --check", "git ls-files"]
    for command in commands:
        result = subprocess.run(
            shlex.split(command), cwd=Path(__file__).resolve().parents[2],
            capture_output=True, check=False,
        )
        assert result.returncode == 0, command


def test_runbook_covers_failure_and_human_boundaries() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for phrase in (
        "exclusive_create", "atomic_rename", "TTL", "PID", "foreign-host",
        "backup-manifest.json", "same-host", "medical", "video", "packaged",
        "Git", "không tự động xuất bản",
    ):
        assert phrase in text
    assert "C:\\Users\\" not in text
    assert "E:\\Protect Your Health" not in text


def test_agents_and_pyh_link_runbook_without_changing_doctor_gates() -> None:
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    skill = Path(".agents/skills/pyh/SKILL.md").read_text(encoding="utf-8")
    for text in (agents, skill):
        assert "m7-hardening-runbook.md" in text
        assert "doctor --project" in text
        assert "security-audit" in text
        assert "hai cổng duyệt" in text or "cổng duyệt y khoa" in text
        assert "không tự động xuất bản" in text
