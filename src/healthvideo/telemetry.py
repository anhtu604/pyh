"""Telemetry for agent CLI token usage, monotonic durations, and Python/GPU stations."""

from __future__ import annotations

import contextvars
import json
import os
import re
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from healthvideo.process import process_token

ACTIVITY_FILE = Path("topics/logs/activity.jsonl")
STATION_TELEMETRY_FILE = Path("topics/logs/station-telemetry.jsonl")
KNOWN_STATIONS: frozenset[str] = frozenset({
    "produce",
    "tts",
    "flux",
    "render",
    "qa",
    "package",
})
WAIT_STATIONS: frozenset[str] = frozenset({
    "wait",
    "doctor_wait",
    "lock_wait",
    "model_wait",
})

_FOOTER_RE = re.compile(
    r"(?:^|\r?\n)tokens used\r?\n([0-9][0-9,]*)\s*\Z",
    re.IGNORECASE,
)
_TELEMETRY_LOCK = threading.Lock()
_ACTIVE_SPAN_STACK: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
    "pyh_active_station_spans",
    default=(),
)


@dataclass(frozen=True)
class CliUsage:
    """Measured CLI token usage from log output; never estimated from text length."""

    usage_available: bool
    cli_total_tokens: int | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    usage_source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "usage_available": self.usage_available,
            "cli_total_tokens": self.cli_total_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "usage_source": self.usage_source,
        }


def _nonneg_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _extract_usage_dict(obj: Mapping[str, Any]) -> dict[str, int | None] | None:
    candidate: Mapping[str, Any] = obj
    raw_usage = obj.get("usage")
    if isinstance(raw_usage, Mapping):
        candidate = raw_usage
    elif not any(
        key in obj
        for key in (
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "reasoning_tokens",
            "total_tokens",
        )
    ):
        return None

    input_tokens = _nonneg_int(candidate.get("input_tokens"))
    output_tokens = _nonneg_int(candidate.get("output_tokens"))
    cached_tokens = _nonneg_int(candidate.get("cached_tokens"))
    if cached_tokens is None:
        cached_tokens = _nonneg_int(candidate.get("cached_input_tokens"))
    if cached_tokens is None:
        cached_tokens = _nonneg_int(candidate.get("cache_read_input_tokens"))
    if cached_tokens is None and isinstance(candidate.get("input_tokens_details"), Mapping):
        cached_tokens = _nonneg_int(candidate["input_tokens_details"].get("cached_tokens"))

    reasoning_tokens = _nonneg_int(candidate.get("reasoning_tokens"))
    if reasoning_tokens is None and isinstance(candidate.get("output_tokens_details"), Mapping):
        reasoning_tokens = _nonneg_int(candidate["output_tokens_details"].get("reasoning_tokens"))

    total_tokens = _nonneg_int(candidate.get("total_tokens"))
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        # Cached and reasoning counts are subsets of input/output tokens; never double-add them.
        total_tokens = (input_tokens or 0) + (output_tokens or 0)

    if (
        total_tokens is None
        and input_tokens is None
        and output_tokens is None
        and cached_tokens is None
        and reasoning_tokens is None
    ):
        return None

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
    }


def _iter_json_objects(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return [parsed]
        except ValueError:
            pass
    objects: list[dict[str, Any]] = []
    for line in text.splitlines():
        line_str = line.strip()
        if not line_str.startswith("{"):
            continue
        try:
            parsed = json.loads(line_str)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            objects.append(parsed)
    return objects


def _sum_usage_dicts(items: list[dict[str, int | None]]) -> dict[str, int | None]:
    def _sum_field(field_name: str) -> int | None:
        values = [item[field_name] for item in items if item[field_name] is not None]
        return sum(values) if values else None

    return {
        "input_tokens": _sum_field("input_tokens"),
        "output_tokens": _sum_field("output_tokens"),
        "cached_tokens": _sum_field("cached_tokens"),
        "reasoning_tokens": _sum_field("reasoning_tokens"),
        "total_tokens": _sum_field("total_tokens"),
    }


def extract_cli_usage(text: str) -> CliUsage:
    """Extract real token usage from CLI footer or JSON usage fields; None if missing."""
    footer_total: int | None = None
    footer_match = _FOOTER_RE.search(text or "")
    if footer_match:
        footer_total = int(footer_match.group(1).replace(",", ""))

    json_objects = _iter_json_objects(text or "")
    summary_usages: list[dict[str, int | None]] = []
    turn_usages: list[dict[str, int | None]] = []
    any_usages: list[dict[str, int | None]] = []
    for obj in json_objects:
        extracted = _extract_usage_dict(obj)
        if extracted is None:
            continue
        any_usages.append(extracted)
        event_type = str(obj.get("type") or "").casefold()
        if event_type in {"result", "response.completed", "final"}:
            summary_usages.append(extracted)
        elif event_type == "turn.completed":
            turn_usages.append(extracted)

    chosen: dict[str, int | None] | None = None
    if summary_usages:
        chosen = summary_usages[-1]
    elif turn_usages:
        chosen = _sum_usage_dicts(turn_usages)
    elif any_usages:
        chosen = any_usages[-1]

    if chosen is not None and (
        chosen["total_tokens"] is not None
        or chosen["input_tokens"] is not None
        or chosen["output_tokens"] is not None
    ):
        total = chosen["total_tokens"] if chosen["total_tokens"] is not None else footer_total
        return CliUsage(
            usage_available=total is not None,
            cli_total_tokens=total,
            input_tokens=chosen["input_tokens"],
            output_tokens=chosen["output_tokens"],
            cached_tokens=chosen["cached_tokens"],
            reasoning_tokens=chosen["reasoning_tokens"],
            usage_source="json",
        )

    if footer_total is not None:
        return CliUsage(
            usage_available=True,
            cli_total_tokens=footer_total,
            usage_source="footer",
        )

    return CliUsage(usage_available=False, cli_total_tokens=None, usage_source=None)


def extract_cli_usage_from_log(log_path: Path) -> CliUsage:
    """Read a CLI log file safely and extract its reported token usage."""
    if not log_path.is_file():
        return CliUsage(usage_available=False, cli_total_tokens=None, usage_source=None)
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return CliUsage(usage_available=False, cli_total_tokens=None, usage_source=None)
    return extract_cli_usage(content)


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    line = json.dumps(dict(row), ensure_ascii=False) + "\n"
    with _TELEMETRY_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(line)


@dataclass
class StationSpan:
    """Mutable telemetry handle yielded by :func:`station_span`."""

    span_id: str
    station: str
    slug: str
    revision: str
    gpu: bool
    wait_s: float = 0.0
    parent_span_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def add_wait(self, seconds: float) -> None:
        if seconds > 0:
            self.wait_s += float(seconds)

    def set_meta(self, **fields: Any) -> None:
        self.meta.update(fields)


@contextmanager
def station_span(
    root: Path,
    slug: str,
    station: str,
    *,
    revision: str = "",
    gpu: bool = False,
    wait_s: float = 0.0,
    metadata: Mapping[str, Any] | None = None,
    now: Callable[[], datetime] | None = None,
) -> Iterator[StationSpan]:
    """Record monotonic start/end, wait_s, and GPU flag for a Python/GPU station."""
    station_name = str(station).strip()
    if not station_name:
        raise ValueError("station name must not be blank")
    clock = now or (lambda: datetime.now().astimezone())
    telemetry_path = root / STATION_TELEMETRY_FILE
    span_id = uuid.uuid4().hex
    stack = _ACTIVE_SPAN_STACK.get()
    parent_span_id = stack[-1] if stack else None
    span = StationSpan(
        span_id=span_id,
        station=station_name,
        slug=slug,
        revision=revision,
        gpu=bool(gpu),
        wait_s=max(0.0, float(wait_s)),
        parent_span_id=parent_span_id,
        meta=dict(metadata or {}),
    )
    pid = os.getpid()
    proc_tok = process_token(pid)
    _append_jsonl(
        telemetry_path,
        {
            "at": clock().isoformat(timespec="seconds"),
            "event": "start",
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "slug": slug,
            "station": station_name,
            "revision": revision,
            "gpu": span.gpu,
            "pid": pid,
            "process_token": proc_tok,
        },
    )
    token = _ACTIVE_SPAN_STACK.set((*stack, span_id))
    t0 = time.monotonic()
    ok = False
    error_kind: str | None = None
    try:
        yield span
        ok = True
    except BaseException as exc:
        error_kind = type(exc).__name__
        raise
    finally:
        _ACTIVE_SPAN_STACK.reset(token)
        duration_s = round(max(0.0, time.monotonic() - t0), 3)
        recorded_wait = round(max(0.0, float(span.wait_s)), 3)
        end_row: dict[str, Any] = {
            "at": clock().isoformat(timespec="seconds"),
            "event": "end",
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "slug": slug,
            "station": station_name,
            "revision": revision,
            "gpu": span.gpu,
            "ok": ok,
            "duration_s": duration_s,
            "wait_s": recorded_wait,
            "pid": pid,
            "process_token": proc_tok,
        }
        if error_kind is not None:
            end_row["error_kind"] = error_kind
        if span.meta:
            end_row["meta"] = dict(span.meta)
        _append_jsonl(telemetry_path, end_row)


def record_wait_event(
    root: Path,
    slug: str,
    reason: str,
    wait_s: float,
    *,
    revision: str = "",
    now: Callable[[], datetime] | None = None,
) -> None:
    """Append an explicit wait record (doctor/lock/model) to station-telemetry.jsonl."""
    clock = now or (lambda: datetime.now().astimezone())
    duration = round(max(0.0, float(wait_s)), 3)
    _append_jsonl(
        root / STATION_TELEMETRY_FILE,
        {
            "at": clock().isoformat(timespec="seconds"),
            "event": "wait",
            "span_id": uuid.uuid4().hex,
            "slug": slug,
            "station": "wait",
            "reason": reason,
            "revision": revision,
            "gpu": False,
            "ok": True,
            "duration_s": duration,
            "wait_s": duration,
            "pid": os.getpid(),
            "process_token": process_token(os.getpid()),
        },
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for raw in lines:
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _parse_iso(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo else parsed.astimezone()
    except (ValueError, OSError, OverflowError):
        return None


def _numeric_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0.0, float(value))
    return None


def _summarize_agents(rows: list[dict[str, Any]]) -> dict[str, Any]:
    open_starts: dict[tuple[str, ...], dict[str, Any]] = {}
    by_step: dict[str, dict[str, Any]] = {}
    by_role: dict[str, dict[str, Any]] = {}
    failure_kinds: Counter[str] = Counter()
    total_runs = 0
    ok_runs = 0
    failed_runs = 0
    duration_s = 0.0
    reported_runs = 0
    missing_runs = 0
    total_tokens = 0

    def _bucket(mapping: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
        return mapping.setdefault(
            key,
            {
                "runs": 0,
                "ok_runs": 0,
                "failed_runs": 0,
                "duration_s": 0.0,
                "cli_total_tokens": None,
                "usage_available": False,
                "reported_runs": 0,
                "missing_runs": 0,
                "_tokens_sum": 0,
            },
        )

    for row in rows:
        raw_job_id = row.get("job_id")
        job_id = raw_job_id.strip() if isinstance(raw_job_id, str) else ""
        key: tuple[str, ...] = (
            ("job", job_id)
            if job_id
            else (
                "legacy",
                str(row.get("slug") or ""),
                str(row.get("step") or ""),
                str(row.get("role") or ""),
                str(row.get("cli") or ""),
                str(row.get("model") or ""),
            )
        )
        event = row.get("event")
        if event == "start":
            open_starts[key] = row
            continue
        if event != "end":
            continue

        prior = open_starts.pop(key, None)
        run_duration = _numeric_float(row.get("duration_s"))
        if run_duration is None and prior is not None:
            start_dt = _parse_iso(prior.get("at"))
            end_dt = _parse_iso(row.get("at"))
            if start_dt is not None and end_dt is not None:
                run_duration = max(0.0, (end_dt - start_dt).total_seconds())
        run_duration = run_duration or 0.0

        ok = row.get("ok") is True
        total_runs += 1
        if ok:
            ok_runs += 1
        else:
            failed_runs += 1
            kind = str(row.get("failure_kind") or "unknown")
            failure_kinds[kind] += 1
        duration_s += run_duration

        tokens = _nonneg_int(row.get("cli_total_tokens"))
        has_usage = row.get("usage_available") is True and tokens is not None
        if has_usage:
            assert tokens is not None
            reported_runs += 1
            total_tokens += tokens
        else:
            missing_runs += 1

        step_name = str(row.get("step") or "unknown")
        role_name = str(row.get("role") or "unknown")
        for bucket in (_bucket(by_step, step_name), _bucket(by_role, role_name)):
            bucket["runs"] += 1
            bucket["ok_runs"] += 1 if ok else 0
            bucket["failed_runs"] += 0 if ok else 1
            bucket["duration_s"] += run_duration
            if has_usage:
                assert tokens is not None
                bucket["reported_runs"] += 1
                bucket["_tokens_sum"] += tokens
                bucket["usage_available"] = True
                bucket["cli_total_tokens"] = bucket["_tokens_sum"]
            else:
                bucket["missing_runs"] += 1

    for mapping in (by_step, by_role):
        for bucket in mapping.values():
            bucket.pop("_tokens_sum", None)
            bucket["duration_s"] = round(bucket["duration_s"], 3)

    return {
        "runs": total_runs,
        "ok_runs": ok_runs,
        "failed_runs": failed_runs,
        "open_starts": len(open_starts),
        "duration_s": round(duration_s, 3),
        "usage_available": reported_runs > 0,
        "cli_total_tokens": total_tokens if reported_runs > 0 else None,
        "partial_usage": reported_runs > 0 and missing_runs > 0,
        "usage_coverage": {
            "reported_runs": reported_runs,
            "missing_runs": missing_runs,
            "total_runs": total_runs,
        },
        "failure_kinds": dict(failure_kinds),
        "by_step": by_step,
        "by_role": by_role,
    }


def _summarize_stations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    starts: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    span_ids: set[str] = set()

    for row in rows:
        event = row.get("event")
        span_id = str(row.get("span_id") or "")
        if event == "start":
            if span_id:
                starts[span_id] = row
            continue
        if event not in {"end", "wait"}:
            continue
        prior = starts.pop(span_id, None) if span_id else None
        station = str(row.get("station") or (prior or {}).get("station") or "unknown")
        parent_id = row.get("parent_span_id")
        if parent_id is None and prior is not None:
            parent_id = prior.get("parent_span_id")
        gpu = bool(row.get("gpu") if "gpu" in row else (prior or {}).get("gpu", False))
        duration = _numeric_float(row.get("duration_s"))
        if duration is None and prior is not None:
            start_dt = _parse_iso(prior.get("at"))
            end_dt = _parse_iso(row.get("at"))
            if start_dt is not None and end_dt is not None:
                duration = max(0.0, (end_dt - start_dt).total_seconds())
        duration = duration or 0.0
        wait = _numeric_float(row.get("wait_s")) or 0.0
        if event == "wait" or station in WAIT_STATIONS:
            wait = max(wait, duration)
            active = 0.0
        else:
            active = max(0.0, duration - wait)
        if span_id:
            span_ids.add(span_id)
        records.append({
            "span_id": span_id,
            "parent_span_id": str(parent_id) if parent_id else None,
            "station": station,
            "event": event,
            "gpu": gpu,
            "ok": row.get("ok") is True,
            "duration_s": duration,
            "active_s": active,
            "wait_s": wait,
        })

    by_id = {rec["span_id"]: rec for rec in records if rec["span_id"]}
    by_station: dict[str, dict[str, Any]] = {}
    python_gpu_s = 0.0
    gpu_s = 0.0
    total_wait_s = 0.0
    work_runs = 0

    def _has_gpu_ancestor(rec: dict[str, Any]) -> bool:
        cur = rec.get("parent_span_id")
        seen: set[str] = set()
        while cur and cur not in seen:
            seen.add(cur)
            parent = by_id.get(cur)
            if parent is None:
                break
            if parent["gpu"]:
                return True
            cur = parent.get("parent_span_id")
        return False

    for rec in records:
        station = rec["station"]
        is_wait_only = rec["event"] == "wait" or station in WAIT_STATIONS
        if not is_wait_only:
            work_runs += 1
            bucket = by_station.setdefault(
                station,
                {
                    "runs": 0,
                    "ok_runs": 0,
                    "failed_runs": 0,
                    "duration_s": 0.0,
                    "active_s": 0.0,
                    "wait_s": 0.0,
                    "gpu_runs": 0,
                    "gpu_s": 0.0,
                },
            )
            bucket["runs"] += 1
            bucket["ok_runs"] += 1 if rec["ok"] else 0
            bucket["failed_runs"] += 0 if rec["ok"] else 1
            bucket["duration_s"] += rec["duration_s"]
            bucket["active_s"] += rec["active_s"]
            bucket["wait_s"] += rec["wait_s"]
            if rec["gpu"]:
                bucket["gpu_runs"] += 1
                bucket["gpu_s"] += rec["active_s"]

        has_parent = bool(rec["parent_span_id"] and rec["parent_span_id"] in span_ids)
        if not has_parent:
            python_gpu_s += rec["active_s"]
            total_wait_s += rec["wait_s"]
        if rec["gpu"] and not _has_gpu_ancestor(rec):
            gpu_s += rec["active_s"]

    for bucket in by_station.values():
        for field_name in ("duration_s", "active_s", "wait_s", "gpu_s"):
            bucket[field_name] = round(bucket[field_name], 3)

    return {
        "runs": work_runs,
        "open_starts": len(starts),
        "python_gpu_s": round(python_gpu_s, 3),
        "gpu_s": round(gpu_s, 3),
        "python_s": round(max(0.0, python_gpu_s - gpu_s), 3),
        "wait_s": round(total_wait_s, 3),
        "by_station": by_station,
    }


def _build_summary(
    agent_rows: list[dict[str, Any]],
    station_rows: list[dict[str, Any]],
    slug: str | None,
) -> dict[str, Any]:
    agent_summary = _summarize_agents(agent_rows)
    station_summary = _summarize_stations(station_rows)
    active_agent_s = float(agent_summary["duration_s"])
    python_gpu_s = float(station_summary["python_gpu_s"])
    wait_s = float(station_summary["wait_s"])
    return {
        "slug": slug,
        "active_agent_s": round(active_agent_s, 3),
        "python_gpu_s": round(python_gpu_s, 3),
        "python_s": station_summary["python_s"],
        "gpu_s": station_summary["gpu_s"],
        "wait_s": round(wait_s, 3),
        "total_active_s": round(active_agent_s + python_gpu_s, 3),
        "usage_available": agent_summary["usage_available"],
        "cli_total_tokens": agent_summary["cli_total_tokens"],
        "partial_usage": agent_summary["partial_usage"],
        "usage_coverage": agent_summary["usage_coverage"],
        "agents": agent_summary,
        "stations": station_summary,
    }


def summarize_telemetry(root: Path, slug: str | None = None) -> dict[str, Any]:
    """Summarize active agent, Python/GPU, wait durations, and reported CLI tokens."""
    all_agent_rows = _read_jsonl(root / ACTIVITY_FILE)
    all_station_rows = _read_jsonl(root / STATION_TELEMETRY_FILE)

    if slug is not None:
        agent_rows = [row for row in all_agent_rows if str(row.get("slug") or "") == slug]
        station_rows = [row for row in all_station_rows if str(row.get("slug") or "") == slug]
        return _build_summary(agent_rows, station_rows, slug)

    summary = _build_summary(all_agent_rows, all_station_rows, None)
    slugs = sorted({
        str(row.get("slug") or "")
        for row in (*all_agent_rows, *all_station_rows)
        if str(row.get("slug") or "").strip()
    })
    summary["projects"] = {
        proj_slug: _build_summary(
            [row for row in all_agent_rows if str(row.get("slug") or "") == proj_slug],
            [row for row in all_station_rows if str(row.get("slug") or "") == proj_slug],
            proj_slug,
        )
        for proj_slug in slugs
    }
    return summary
