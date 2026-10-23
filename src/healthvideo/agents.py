"""Invoke coding agents with quota-exhaustion failover."""

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from healthvideo.env import child_env


@dataclass(frozen=True)
class AgentCli:
    """CLI configuration for an external coding agent."""

    name: str
    argv: tuple[str, ...]
    prompt_via_stdin: bool


DEFAULT_AGENTS: tuple[AgentCli, ...] = (
    AgentCli(
        "codex",
        ("codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "-"),
        True,
    ),
    AgentCli(
        "agy",
        (
            "agy",
            "-p",
            "{prompt}",
            "--mode",
            "accept-edits",
            "--print-timeout",
            "0s",
            "--model",
            "gemini-4-argon-medium",
        ),
        False,
    ),
)

QUOTA_PATTERNS: tuple[str, ...] = (
    "usage limit",
    "rate limit",
    "quota",
    "resource_exhausted",
    "429",
)


@dataclass(frozen=True)
class AgentResult:
    """Outcome of a single agent CLI invocation."""

    agent: str
    ok: bool
    quota_exhausted: bool
    log_path: Path


class AllAgentsExhausted(RuntimeError):
    """Raised when every configured agent fails due to quota exhaustion."""


def invoke(
    agent: AgentCli,
    prompt: str,
    *,
    cwd: Path,
    log_dir: Path,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> AgentResult:
    """Invoke a single agent CLI and capture its output to a UTF-8 log file."""
    if agent.prompt_via_stdin:
        argv = list(agent.argv)
        stdin_input: str | None = prompt
    else:
        argv = [prompt if token == "{prompt}" else token for token in agent.argv]
        stdin_input = None

    env = child_env()
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    log_path = log_dir / f"{timestamp}-{agent.name}.log"

    try:
        completed = runner(
            argv,
            cwd=cwd,
            input=stdin_input,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except FileNotFoundError as exc:
        log_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        return AgentResult(
            agent=agent.name,
            ok=False,
            quota_exhausted=False,
            log_path=log_path,
        )

    output = f"{completed.stdout or ''}{completed.stderr or ''}"
    log_path.write_text(output, encoding="utf-8")
    ok = completed.returncode == 0
    lower_output = output.lower()
    quota_exhausted = (not ok) and any(
        pattern.lower() in lower_output for pattern in QUOTA_PATTERNS
    )
    return AgentResult(
        agent=agent.name,
        ok=ok,
        quota_exhausted=quota_exhausted,
        log_path=log_path,
    )


def invoke_with_failover(
    agents: Sequence[AgentCli],
    prompt: str,
    *,
    cwd: Path,
    log_dir: Path,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> AgentResult:
    """Invoke agents in order, failing over only on quota exhaustion."""
    exhausted_names: list[str] = []
    for agent in agents:
        result = invoke(agent, prompt, cwd=cwd, log_dir=log_dir, runner=runner)
        if result.ok or not result.quota_exhausted:
            return result
        exhausted_names.append(agent.name)

    joined = ", ".join(exhausted_names)
    raise AllAgentsExhausted(f"All agents exhausted quota: {joined}")
