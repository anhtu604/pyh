"""Invoke coding agents with quota-exhaustion failover."""

import json
import os
import re
import subprocess
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from healthvideo.company import REPO_ROOT, ModelSlot
from healthvideo.env import child_env
from healthvideo.process import prepare_subprocess_argv
from healthvideo.storage.files import read_yaml, write_yaml_atomic

RUNNING_MARKER = ".agent-running"
QUOTA_FILE = Path("cache/agent-quota.yaml")
ACTIVITY_FILE = Path("topics/logs/activity.jsonl")
# A CLI that does not say when its quota resets rests this long.
DEFAULT_REST = timedelta(hours=5)
# Prompts longer than this reach argv-only CLIs (agy) through a file.
MAX_ARGV_PROMPT = 8000


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
AGENT_CLIS: dict[str, AgentCli] = {"claude": CLAUDE, "codex": CODEX, "agy": AGY}

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

# Provider overload (seen 2026-11-13: agy 503 "No capacity available for model ...").
BUSY_PATTERNS: tuple[str, ...] = ("no capacity available", "high traffic", "code 503", "overloaded")
BUSY_REST = timedelta(minutes=10)


@dataclass(frozen=True)
class AgentResult:
    """Outcome of a single agent CLI invocation."""

    agent: str
    ok: bool
    quota_exhausted: bool
    log_path: Path
    model: str = ""


class AllAgentsExhausted(RuntimeError):
    """Raised when every slot of a chain is resting or just ran out of quota."""

    def __init__(self, earliest_return: datetime | None = None) -> None:
        self.earliest_return = earliest_return
        when = earliest_return.strftime("%H:%M %d/%m") if earliest_return else "chưa rõ"
        super().__init__(f"Mọi model trong chuỗi đều hết lượt; sớm nhất trở lại: {when}")


def argv_for(slot: ModelSlot) -> tuple[AgentCli, list[str]]:
    """Return the CLI for a slot and its argv with the slot's model flag."""
    cli = AGENT_CLIS[slot.cli]
    argv = list(cli.argv)
    if "--model" in argv:  # claude, agy
        argv[argv.index("--model") + 1] = slot.model
    else:  # codex reads the prompt from the trailing "-"
        dash = argv.index("-")
        argv[dash:dash] = ["-m", slot.model]
    return cli, argv


def _when(value: object) -> datetime:
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return moment if moment.tzinfo else moment.astimezone()


@contextmanager
def _quota_lock(path: Path):
    """Serialize quota read/modify/write across factory and dashboard processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + '.lock').open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'\0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class QuotaBook:
    """Slots resting after a quota hit; ``model: '*'`` rests every model of a CLI."""

    def __init__(self, path: Path = REPO_ROOT / QUOTA_FILE) -> None:
        self.path = path

    def _entries(self) -> list[dict]:
        if not self.path.is_file():
            return []
        return list(read_yaml(self.path).get("entries") or [])

    def _until(self, slot: ModelSlot, now: datetime) -> datetime | None:
        times = [
            _when(entry["resting_until"]) for entry in self._entries()
            if entry["cli"] == slot.cli and entry["model"] in (slot.model, "*")
        ]
        return max((moment for moment in times if moment > now), default=None)

    def resting(self, slot: ModelSlot, now: datetime) -> bool:
        return self._until(slot, now) is not None

    def rest(self, slot: ModelSlot, until: datetime, reason: str) -> None:
        with _quota_lock(self.path):
            entries = [
                entry for entry in self._entries()
                if (entry["cli"], entry["model"]) != (slot.cli, slot.model)
            ]
            entries.append({
                "cli": slot.cli,
                "model": slot.model,
                "resting_until": until.isoformat(timespec="seconds"),
                "reason": reason,
            })
            write_yaml_atomic(self.path, {"version": 1, "entries": entries})

    def earliest_return(self, slots: Sequence[ModelSlot], now: datetime) -> datetime | None:
        times = [self._until(slot, now) for slot in slots]
        return min((moment for moment in times if moment is not None), default=None)

    def snapshot(self, now: datetime) -> list[dict]:
        return [entry for entry in self._entries() if _when(entry["resting_until"]) > now]


_RESET_AT = re.compile(r"try again at\s+(\d{1,2}):(\d{2})\s*(am|pm)?", re.IGNORECASE)
_RESET_IN = re.compile(
    r"(?:resets?|try again)\s+in\s+(\d+)\s*(hours?|hrs?|minutes?|mins?)", re.IGNORECASE
)
_ACCOUNT = re.compile(r"\b(account|plan)\b", re.IGNORECASE)


def parse_reset(output: str, now: datetime) -> datetime | None:
    """Read the reset time a CLI printed; None when it gave none."""
    match = _RESET_AT.search(output)
    if match:
        hour, minute, half = int(match[1]), int(match[2]), (match[3] or "").lower()
        if half:
            hour = hour % 12 + (12 if half == "pm" else 0)
        if hour > 23 or minute > 59:
            return None
        moment = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return moment if moment > now else moment + timedelta(days=1)
    match = _RESET_IN.search(output)
    if match:
        unit = "hours" if match[2].lower().startswith("h") else "minutes"
        return now + timedelta(**{unit: int(match[1])})
    return None


def _quota_reason(output: str) -> str:
    for line in output.splitlines():
        if any(pattern in line.lower() for pattern in QUOTA_PATTERNS):
            return line.strip()[:200]
    return "hết lượt"


def invoke(
    agent: AgentCli,
    prompt: str,
    *,
    cwd: Path,
    log_dir: Path,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> AgentResult:
    """Invoke a single agent CLI and capture its output to a UTF-8 log file."""
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    log_path = log_dir / f"{timestamp}-{agent.name}.log"
    if agent.prompt_via_stdin:
        argv = list(agent.argv)
        stdin_input: str | None = prompt
    else:
        if len(prompt) > MAX_ARGV_PROMPT:
            # Windows caps a command line at 32,767 chars; long prompts go through a file.
            prompt_path = (log_dir / f"{timestamp}-{agent.name}-prompt.md").resolve()
            prompt_path.write_text(prompt, encoding="utf-8")
            prompt = f"Đọc và làm đúng theo toàn bộ nội dung file {prompt_path}"
        argv = [prompt if token == "{prompt}" else token for token in agent.argv]
        stdin_input = None

    env = child_env()
    marker = log_dir / RUNNING_MARKER
    marker.write_text(f"{agent.name}\n{datetime.now(UTC).isoformat()}\n", encoding="utf-8")

    try:
        completed = runner(
            prepare_subprocess_argv(argv),
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
    slots: Sequence[ModelSlot],
    prompt: str,
    *,
    cwd: Path,
    log_dir: Path,
    role: str,
    slug: str,
    step: str,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    quota: QuotaBook | None = None,
    activity: Path | None = None,
) -> AgentResult:
    """Try each non-resting slot in order, failing over only on quota exhaustion.

    ``quota`` and ``activity`` default to ``cache/`` and ``topics/logs/`` under ``cwd``.
    """
    quota = quota or QuotaBook(cwd / QUOTA_FILE)
    activity = activity or cwd / ACTIVITY_FILE

    def log(slot: ModelSlot, event: str, ok: bool | None) -> None:
        row = {"at": now().isoformat(timespec="seconds"), "role": role, "cli": slot.cli,
               "model": slot.model, "slug": slug, "step": step, "event": event, "ok": ok,
               "pid": os.getpid()}
        activity.parent.mkdir(parents=True, exist_ok=True)
        with activity.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    for slot in slots:
        if quota.resting(slot, now()):
            continue
        cli, argv = argv_for(slot)
        log(slot, "start", None)
        result = invoke(replace(cli, argv=tuple(argv)), prompt, cwd=cwd, log_dir=log_dir,
                        runner=runner)
        result = replace(result, model=slot.model)
        log(slot, "end", result.ok)
        if not result.ok and not result.quota_exhausted:
            output = result.log_path.read_text(encoding="utf-8", errors="replace").lower()
            if any(pattern in output for pattern in BUSY_PATTERNS):
                # Server overload is not our quota: rest briefly and try the next model.
                log(slot, "busy", False)
                quota.rest(slot, now() + BUSY_REST, "máy chủ quá tải")
                continue
        if result.ok or not result.quota_exhausted:
            return result
        log(slot, "quota", False)
        output = result.log_path.read_text(encoding="utf-8", errors="replace")
        moment = now()
        until = parse_reset(output, moment) or moment + DEFAULT_REST
        # Quota is per CLI account; only an account-wide message rests every model.
        rested = ModelSlot(cli=slot.cli, model="*") if _ACCOUNT.search(output) else slot
        quota.rest(rested, until, _quota_reason(output))

    raise AllAgentsExhausted(quota.earliest_return(slots, now()))
