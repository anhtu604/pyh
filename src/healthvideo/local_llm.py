"""Bounded Ollama ~4B local router for lightweight non-medical tasks."""

from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypeVar
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from healthvideo.env import child_env
from healthvideo.process import is_same_process, prepare_subprocess_argv
from healthvideo.storage.files import read_yaml

T = TypeVar("T")

LOCAL_ALLOWED_TASKS: frozenset[str] = frozenset({
    "feedback_inbox",
    "chat_status_summary",
    "topic_dedupe_hint",
})
NEVER_LOCAL_ROLES: frozenset[str] = frozenset({
    "medical_expert",
    "writer",
    "script_critic",
    "product_critic",
    "art_director",
    "storyboard_director",
    "editor",
    "repair_engineer",
    "coordinator_senior",
})

DEFAULT_OLLAMA_ENDPOINT = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:4b"
DEFAULT_NUM_CTX = 4096
DEFAULT_VRAM_HEADROOM_MIB = 2048
DEFAULT_MIN_FREE_RAM_MIB = 8192
LOCAL_LLM_CONFIG_PATH = Path("profiles/local-llm.yaml")
GPU_WORKER_PATH = Path("cache/gpu-worker")
GPU_WORKER_LOCK_PATH = Path("cache/gpu-worker.lock")
GPU_MUTEX_LOCK_PATH = Path("cache/gpu-mutex.lock")

_LOCAL_GPU_LOCK = threading.Lock()
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*\Z", re.DOTALL | re.IGNORECASE)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class LocalFeedbackTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["san_pham", "xuong", "chuan_kenh"]
    target: str = Field(min_length=1)
    request: str = Field(min_length=1)
    done_when: str = Field(min_length=1)


class LocalFeedbackAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    tasks: list[LocalFeedbackTask] = Field(min_length=1)


class ChatStatusSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply: str = Field(min_length=1)
    action: Literal["status", "none"] = "status"
    escalate: bool = False
    highlights: list[str] = Field(default_factory=list)


class TopicDedupeHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_potential_duplicate: bool
    matched_slug: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)


TASK_SCHEMAS: dict[str, type[BaseModel]] = {
    "feedback_inbox": LocalFeedbackAnalysis,
    "chat_status_summary": ChatStatusSummary,
    "topic_dedupe_hint": TopicDedupeHint,
}


class LocalLLMConfig(BaseModel):
    """Runtime settings for optional ~4B local routing; off by default until benchmarked."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    benchmark_verified: bool = True
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT
    model: str = DEFAULT_MODEL
    peak_vram_mib: int = Field(default=3500, ge=0)
    vram_headroom_mib: int = Field(default=DEFAULT_VRAM_HEADROOM_MIB, ge=0)
    min_free_ram_mib: int = Field(default=DEFAULT_MIN_FREE_RAM_MIB, ge=0)
    num_ctx: int = Field(default=DEFAULT_NUM_CTX, ge=256, le=4096)
    timeout_s: float = Field(default=45.0, gt=0.0)
    allowed_tasks: tuple[str, ...] = tuple(sorted(LOCAL_ALLOWED_TASKS))

    @field_validator("endpoint")
    @classmethod
    def _loopback_endpoint(cls, value: str) -> str:
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != ""
        ):
            raise ValueError("Ollama endpoint phải là HTTP loopback gốc (vd. http://127.0.0.1:11434).")
        return f"{parsed.scheme}://{parsed.netloc}"

    @field_validator("allowed_tasks")
    @classmethod
    def _subset_allowlist(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        disallowed = sorted(set(value) - LOCAL_ALLOWED_TASKS)
        if disallowed:
            raise ValueError(f"Task không thuộc allowlist local LLM: {', '.join(disallowed)}")
        return value


@dataclass(frozen=True)
class LocalAttempt:
    """Result of one bounded local Ollama attempt."""

    ok: bool
    used_local: bool
    reason: str | None = None
    failure_kind: str | None = None
    model: str = ""
    data: BaseModel | None = None
    raw_response: str = ""
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    total_duration_s: float = 0.0
    eval_tok_per_s: float | None = None
    vram_mib: dict[str, int] | None = None
    free_ram_mib: int | None = None
    ps_info: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int | None:
        if self.prompt_eval_count is None and self.eval_count is None:
            return None
        return (self.prompt_eval_count or 0) + (self.eval_count or 0)


@dataclass(frozen=True)
class LocalRouteOutcome:
    """Unified return object for :func:`route_local_or_fallback`."""

    used_local: bool
    ok: bool
    data: BaseModel | None = None
    fallback_result: Any = None
    fallback_reason: str | None = None
    attempt: LocalAttempt | None = None


def validate_local_policy(task: str, *, role: str | None = None) -> None:
    """Enforce hard role exclusions and the local task allowlist."""
    if role is not None and role in NEVER_LOCAL_ROLES:
        raise ValueError(f"Vai {role!r} bị cấm tuyệt đối chạy local LLM.")
    if task not in LOCAL_ALLOWED_TASKS:
        raise ValueError(f"Tác vụ {task!r} không nằm trong allowlist local LLM.")


def load_local_llm_config(root: Path) -> LocalLLMConfig:
    """Load ``profiles/local-llm.yaml`` when present; otherwise disabled by default."""
    path = root / LOCAL_LLM_CONFIG_PATH
    if not path.is_file():
        return LocalLLMConfig(enabled=False)
    return LocalLLMConfig.model_validate(read_yaml(path))


def measure_vram_mib(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, int] | None:
    """Measure real GPU VRAM in MiB using ``nvidia-smi``; returns None if unavailable."""
    argv = ["nvidia-smi", "--query-gpu=memory.free,memory.total,memory.used", "--format=csv,noheader,nounits"]
    try:
        prepared = prepare_subprocess_argv(argv)
    except (OSError, ValueError):
        prepared = argv
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 5.0,
        "check": False,
        "shell": False,
        "env": child_env(),
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = runner(prepared, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    best: dict[str, int] | None = None
    for line in (completed.stdout or "").splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            free_mib, total_mib, used_mib = int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
        except ValueError:
            continue
        candidate = {"free_mib": free_mib, "total_mib": total_mib, "used_mib": used_mib}
        if best is None or candidate["free_mib"] > best["free_mib"]:
            best = candidate
    return best


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def measure_free_ram_mib() -> int | None:
    """Measure real available physical RAM in MiB via Win32 GlobalMemoryStatusEx."""
    if sys.platform == "win32":
        try:
            stat = _MemoryStatusEx()
            stat.dwLength = ctypes.sizeof(_MemoryStatusEx)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return None
            return int(stat.ullAvailPhys // (1024 * 1024))
        except (AttributeError, OSError):
            return None
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        try:
            for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb // 1024
        except (OSError, ValueError, IndexError):
            return None
    return None


def _try_nonblocking_lock(path: Path) -> Any | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    try:
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        stream.close()
        return None
    return stream


def _unlock_stream(stream: Any) -> None:
    try:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        stream.close()


def _marker_is_live(marker: Path) -> bool:
    if not marker.is_file():
        return False
    try:
        raw = marker.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return True
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    pid = data.get("pid")
    token = data.get("process_token")
    if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
        return is_same_process(pid, str(token) if token is not None else None)
    return False


def _active_production_running(root: Path) -> bool:
    logs_dir = root / "topics" / "logs"
    if not logs_dir.is_dir():
        return False
    for marker in logs_dir.glob("*/.production-running"):
        if _marker_is_live(marker):
            return True
    return False


@contextmanager
def try_acquire_gpu_worker(root: Path) -> Iterator[bool]:
    """Try non-blocking acquisition of GPU worker mutexes; yields False if busy."""
    from healthvideo.workflows import factory
    from healthvideo.workflows import runner as runner_mod

    if _active_production_running(root):
        yield False
        return

    worker_path = root / GPU_WORKER_PATH
    if worker_path.is_dir():
        if factory.running_pid(worker_path) is not None:
            yield False
            return
    elif worker_path.is_file() and _marker_is_live(worker_path):
        yield False
        return

    acquired_local = _LOCAL_GPU_LOCK.acquire(blocking=False)
    if not acquired_local:
        yield False
        return
    acquired_runner = runner_mod._GPU_THREAD_LOCK.acquire(blocking=False)
    if not acquired_runner:
        _LOCAL_GPU_LOCK.release()
        yield False
        return

    streams: list[Any] = []
    try:
        for lock_path in (root / GPU_WORKER_LOCK_PATH, root / GPU_MUTEX_LOCK_PATH):
            stream = _try_nonblocking_lock(lock_path)
            if stream is None:
                yield False
                return
            streams.append(stream)
        if worker_path.is_file():
            worker_stream = _try_nonblocking_lock(worker_path)
            if worker_stream is None:
                yield False
                return
            streams.append(worker_stream)
        yield True
    finally:
        for stream in reversed(streams):
            _unlock_stream(stream)
        runner_mod._GPU_THREAD_LOCK.release()
        _LOCAL_GPU_LOCK.release()


def is_gpu_worker_free(root: Path) -> bool:
    """Non-blocking probe indicating whether the GPU worker mutex is free."""
    with try_acquire_gpu_worker(root) as free:
        return free


def _http_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 5.0,
    urlopen_fn: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    request = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    with urlopen_fn(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw) if raw.strip() else {}
    if not isinstance(parsed, dict):
        raise TypeError("Ollama JSON response must be an object")
    return parsed


def _model_matches(requested: str, installed: set[str]) -> bool:
    norm = requested.strip()
    return norm in installed or (":" not in norm and f"{norm}:latest" in installed)


def list_installed_models(
    endpoint: str,
    *,
    timeout: float = 2.0,
    urlopen_fn: Callable[..., Any] = urlopen,
) -> set[str]:
    """Query Ollama ``/api/tags`` for already installed local models (never pulls)."""
    data = _http_json(f"{endpoint.rstrip('/')}/api/tags", timeout=timeout, urlopen_fn=urlopen_fn)
    models = data.get("models")
    if not isinstance(models, list):
        return set()
    names: set[str] = set()
    for item in models:
        if not isinstance(item, dict):
            continue
        for key in ("name", "model"):
            val = item.get(key)
            if isinstance(val, str) and val.strip():
                names.add(val.strip())
    return names


def check_ps_gpu_only(
    endpoint: str,
    model: str,
    *,
    timeout: float = 2.0,
    urlopen_fn: Callable[..., Any] = urlopen,
) -> tuple[bool, dict[str, Any]]:
    """Inspect ``/api/ps`` to reject silent CPU offload (``size_vram < size``)."""
    data = _http_json(f"{endpoint.rstrip('/')}/api/ps", timeout=timeout, urlopen_fn=urlopen_fn)
    models = data.get("models")
    if not isinstance(models, list):
        raise TypeError("Invalid /api/ps payload")
    for item in models:
        if not isinstance(item, dict):
            continue
        item_names = {
            str(item.get("name") or "").strip(),
            str(item.get("model") or "").strip(),
        }
        if not _model_matches(model, {name for name in item_names if name}):
            continue
        size = int(item.get("size") or 0)
        size_vram = int(item.get("size_vram") or 0)
        offloaded = size > 0 and (size_vram <= 0 or size_vram < size)
        return (not offloaded), {
            "resident": True,
            "offloaded": offloaded,
            "size": size,
            "size_vram": size_vram,
        }
    return True, {"resident": False, "offloaded": False, "size": 0, "size_vram": 0}


def _unload_model_best_effort(
    endpoint: str,
    model: str,
    *,
    urlopen_fn: Callable[..., Any] = urlopen,
) -> None:
    try:
        _http_json(
            f"{endpoint.rstrip('/')}/api/generate",
            payload={"model": model, "prompt": "", "stream": False, "keep_alive": 0},
            timeout=2.0,
            urlopen_fn=urlopen_fn,
        )
    except (OSError, URLError, ValueError, TimeoutError):
        pass


def _parse_schema_response(raw_text: str, schema: type[BaseModel]) -> BaseModel:
    cleaned = _THINK_RE.sub("", raw_text or "").strip()
    fence = _FENCE_RE.match(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    payload = json.loads(cleaned)
    return schema.model_validate(payload)


def try_local_task(
    *,
    root: Path,
    task: str,
    prompt: str,
    role: str | None = None,
    schema: type[BaseModel] | None = None,
    config: LocalLLMConfig | None = None,
    vram_probe: Callable[[], dict[str, int] | None] = measure_vram_mib,
    ram_probe: Callable[[], int | None] = measure_free_ram_mib,
    urlopen_fn: Callable[..., Any] = urlopen,
) -> LocalAttempt:
    """Run all 5 pre-flight guards and call Ollama once; never pulls or retries."""
    if role is not None and role in NEVER_LOCAL_ROLES:
        raise ValueError(f"Vai {role!r} bị cấm tuyệt đối chạy local LLM.")

    cfg = config if config is not None else load_local_llm_config(root)

    # (1) Check allowlist and post-benchmark enable flag.
    if task not in LOCAL_ALLOWED_TASKS or task not in cfg.allowed_tasks:
        return LocalAttempt(ok=False, used_local=False, reason="task_not_allowed", failure_kind="policy")
    if not cfg.enabled or not cfg.benchmark_verified:
        return LocalAttempt(ok=False, used_local=False, reason="local_llm_disabled", failure_kind="disabled")

    target_schema = schema or TASK_SCHEMAS.get(task)
    if target_schema is None:
        return LocalAttempt(ok=False, used_local=False, reason="missing_schema", failure_kind="policy")

    # (2) Check GPU worker mutex is free and hold it across inference.
    with try_acquire_gpu_worker(root) as gpu_acquired:
        if not gpu_acquired:
            return LocalAttempt(ok=False, used_local=False, reason="gpu_worker_busy", failure_kind="resource")

        # (3) Measure real VRAM and RAM before loading model.
        vram = vram_probe()
        if vram is None:
            return LocalAttempt(ok=False, used_local=False, reason="vram_probe_failed", failure_kind="resource")
        required_vram = cfg.peak_vram_mib + cfg.vram_headroom_mib
        if vram["free_mib"] < required_vram:
            return LocalAttempt(
                ok=False,
                used_local=False,
                reason=f"insufficient_vram:{vram['free_mib']}<{required_vram}",
                failure_kind="resource",
                vram_mib=vram,
            )
        free_ram = ram_probe()
        if free_ram is None or free_ram < cfg.min_free_ram_mib:
            return LocalAttempt(
                ok=False,
                used_local=False,
                reason=f"insufficient_ram:{free_ram}<{cfg.min_free_ram_mib}",
                failure_kind="resource",
                vram_mib=vram,
                free_ram_mib=free_ram,
            )

        # (4) Confirm model is already installed via /api/tags (never pull in production).
        try:
            installed = list_installed_models(cfg.endpoint, timeout=2.0, urlopen_fn=urlopen_fn)
        except (OSError, URLError, ValueError, TypeError, TimeoutError) as exc:
            return LocalAttempt(
                ok=False,
                used_local=False,
                reason=f"ollama_tags_unavailable:{type(exc).__name__}",
                failure_kind="transient",
                vram_mib=vram,
                free_ram_mib=free_ram,
            )
        if not _model_matches(cfg.model, installed):
            return LocalAttempt(
                ok=False,
                used_local=False,
                reason=f"model_not_installed:{cfg.model}",
                failure_kind="configuration",
                vram_mib=vram,
                free_ram_mib=free_ram,
            )

        # (5) Call /api/generate (num_ctx: 4096, keep_alive: 0), verify /api/ps & schema.
        t0 = time.monotonic()
        try:
            gen_payload = {
                "model": cfg.model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": 0,
                "format": target_schema.model_json_schema(),
                "options": {
                    "num_ctx": cfg.num_ctx,
                    "temperature": 0.1,
                },
            }
            response = _http_json(
                f"{cfg.endpoint}/api/generate",
                payload=gen_payload,
                timeout=cfg.timeout_s,
                urlopen_fn=urlopen_fn,
            )
        except (OSError, URLError, ValueError, TypeError, TimeoutError) as exc:
            _unload_model_best_effort(cfg.endpoint, cfg.model, urlopen_fn=urlopen_fn)
            return LocalAttempt(
                ok=False,
                used_local=False,
                reason=f"ollama_generate_error:{type(exc).__name__}",
                failure_kind="transient",
                model=cfg.model,
                total_duration_s=round(max(0.0, time.monotonic() - t0), 3),
                vram_mib=vram,
                free_ram_mib=free_ram,
            )

        duration_s = round(max(0.0, time.monotonic() - t0), 3)
        if response.get("error"):
            _unload_model_best_effort(cfg.endpoint, cfg.model, urlopen_fn=urlopen_fn)
            return LocalAttempt(
                ok=False,
                used_local=False,
                reason=f"ollama_error:{response['error']}",
                failure_kind="transient",
                model=cfg.model,
                total_duration_s=duration_s,
                vram_mib=vram,
                free_ram_mib=free_ram,
            )

        try:
            gpu_only, ps_info = check_ps_gpu_only(
                cfg.endpoint,
                cfg.model,
                timeout=2.0,
                urlopen_fn=urlopen_fn,
            )
        except (OSError, URLError, ValueError, TypeError, TimeoutError) as exc:
            _unload_model_best_effort(cfg.endpoint, cfg.model, urlopen_fn=urlopen_fn)
            return LocalAttempt(
                ok=False,
                used_local=False,
                reason=f"ollama_ps_failed:{type(exc).__name__}",
                failure_kind="transient",
                model=cfg.model,
                total_duration_s=duration_s,
                vram_mib=vram,
                free_ram_mib=free_ram,
            )

        if not gpu_only:
            _unload_model_best_effort(cfg.endpoint, cfg.model, urlopen_fn=urlopen_fn)
            return LocalAttempt(
                ok=False,
                used_local=False,
                reason="cpu_offload_detected",
                failure_kind="resource",
                model=cfg.model,
                total_duration_s=duration_s,
                vram_mib=vram,
                free_ram_mib=free_ram,
                ps_info=ps_info,
            )
        if ps_info.get("resident"):
            _unload_model_best_effort(cfg.endpoint, cfg.model, urlopen_fn=urlopen_fn)

        raw_text = str(response.get("response") or "")
        try:
            validated = _parse_schema_response(raw_text, target_schema)
        except (ValueError, ValidationError) as exc:
            return LocalAttempt(
                ok=False,
                used_local=False,
                reason=f"schema_validation_failed:{type(exc).__name__}",
                failure_kind="validation",
                model=cfg.model,
                raw_response=raw_text,
                total_duration_s=duration_s,
                vram_mib=vram,
                free_ram_mib=free_ram,
                ps_info=ps_info,
            )

        prompt_eval = response.get("prompt_eval_count")
        eval_count = response.get("eval_count")
        eval_ns = response.get("eval_duration")
        tok_s = (
            round(float(eval_count) / (float(eval_ns) / 1_000_000_000.0), 2)
            if isinstance(eval_count, int)
            and isinstance(eval_ns, int)
            and eval_ns > 0
            else None
        )
        return LocalAttempt(
            ok=True,
            used_local=True,
            model=cfg.model,
            data=validated,
            raw_response=raw_text,
            prompt_eval_count=prompt_eval if isinstance(prompt_eval, int) else None,
            eval_count=eval_count if isinstance(eval_count, int) else None,
            total_duration_s=duration_s,
            eval_tok_per_s=tok_s,
            vram_mib=vram,
            free_ram_mib=free_ram,
            ps_info=ps_info,
        )


def route_local_or_fallback(
    *,
    root: Path,
    task: str,
    prompt: str,
    fallback: Callable[[], T],
    role: str | None = None,
    schema: type[BaseModel] | None = None,
    config: LocalLLMConfig | None = None,
    vram_probe: Callable[[], dict[str, int] | None] = measure_vram_mib,
    ram_probe: Callable[[], int | None] = measure_free_ram_mib,
    urlopen_fn: Callable[..., Any] = urlopen,
) -> LocalRouteOutcome:
    """Attempt local Ollama once when safe; fall back cleanly to OmniRoute exactly once."""
    attempt = try_local_task(
        root=root,
        task=task,
        prompt=prompt,
        role=role,
        schema=schema,
        config=config,
        vram_probe=vram_probe,
        ram_probe=ram_probe,
        urlopen_fn=urlopen_fn,
    )
    if attempt.ok:
        return LocalRouteOutcome(
            used_local=True,
            ok=True,
            data=attempt.data,
            attempt=attempt,
        )
    fallback_result = fallback()
    return LocalRouteOutcome(
        used_local=False,
        ok=bool(getattr(fallback_result, "ok", True)),
        fallback_result=fallback_result,
        fallback_reason=attempt.reason,
        attempt=attempt,
    )
