"""Invoke coding agents with quota-exhaustion failover."""

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from healthvideo.env import child_env

RUNNING_MARKER = ".agent-running"


@dataclass(frozen=True)
class AgentCli:
    """CLI configuration for an external coding agent."""

    name: str
    argv: tuple[str, ...]
    prompt_via_stdin: bool


CODEX = AgentCli(
    "codex",
    ("codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "-"),
    True,
)
AGY = AgentCli(
    "agy",
    (
        "agy",
        "-p",
        "{prompt}",
        "--mode",
        "accept-edits",
        # Headless mode cannot prompt; without this, shell tools are
        # auto-denied and the agent silently does nothing. Parity with
        # Codex's bypass flag; approval gates still need the TTY PIN.
        "--dangerously-skip-permissions",
        "--print-timeout",
        "0s",
        "--model",
        "gemini-4-argon-medium",
    ),
    False,
)
# Claude runs headless with a fixed tool allowlist instead of bypassing permissions;
# anything outside the list is refused, and the user's hooks stay on.
CLAUDE = AgentCli(
    "claude",
    (
        "claude",
        "-p",
        "--permission-mode",
        "acceptEdits",
        "--allowedTools",
        "Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,Bash(healthvideo:*),PowerShell(healthvideo:*)",
        "--model",
        "opus",
    ),
    True,
)
# agy first: the doctor routes work to agy because Codex is near its token limit.
# Hard steps are routed to Claude per step in factory_deps.STEP_AGENTS.
DEFAULT_AGENTS: tuple[AgentCli, ...] = (AGY, CODEX)

QUOTA_PATTERNS: tuple[str, ...] = (
    "usage limit",
    "rate limit",
    "quota",
    "resource_exhausted",
    "429",
    "limit reached",
    "hit your limit",
    # Claude CLI login without a usable plan: fail over instead of blocking the topic.
    "can't use your claude subscription",
)

PERMISSION_DENIED_PATTERNS: tuple[str, ...] = ("auto-denied",)


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
    marker = log_dir / RUNNING_MARKER
    marker.write_text(f"{agent.name}\n{datetime.now(UTC).isoformat()}\n", encoding="utf-8")

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
    finally:
        marker.unlink(missing_ok=True)

    output = f"{completed.stdout or ''}{completed.stderr or ''}"
    log_path.write_text(output, encoding="utf-8")
    lower_output = output.lower()
    ok = completed.returncode == 0 and not any(
        pattern in lower_output for pattern in PERMISSION_DENIED_PATTERNS
    )
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
