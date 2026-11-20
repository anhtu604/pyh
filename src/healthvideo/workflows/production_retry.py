"""Classify production failures and bound automatic retries per input fingerprint."""

from __future__ import annotations

import os
import re
import stat
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml

from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.failures import classify_failure, is_file_contention
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)

MAX_TRANSIENT_ATTEMPTS = 3
TRANSIENT_BACKOFF_SECONDS: dict[int, int] = {
    1: 120,
    2: 600,
}
_SECRET_ENV_KEYS = (
    "VIBI_API_KEY",
    "ELEVENLABS_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "YOUTUBE_API_KEY",
    "NCBI_API_KEY",
)
_TRANSIENT_ERROR_PATTERNS = (
    "os error 1455",
    "paging file is too small",
    "cannot allocate memory",
    "vibi connection failed",
    "3221225477",
    "3221226505",
    "memory allocation",
    "connection reset",
    "connection refused",
    "connection timed out",
    "timed out",
    "temporarily unavailable",
    "service unavailable",
    "http 502",
    "http 503",
    "http 504",
)
_WINDOWS_TRANSIENT_UNLINK_ERRORS = frozenset({5, 32, 33})
_CODE_HASH_CACHE: dict[tuple[str, int, int], str] = {}
_STATIC_CODE_FILES_CACHE: dict[tuple[str, bool], list[tuple[str, Path]]] = {}
_SKIP_CODE_WALK_DIRS = frozenset({
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "out",
    ".pytest_cache",
    ".ruff_cache",
})


def _is_transient_production_error(error: Exception) -> bool:
    if not isinstance(error, ValueError):
        return True
    detail = str(error).lower()
    return (classify_failure(error) == "transient"
            or any(pattern in detail for pattern in _TRANSIENT_ERROR_PATTERNS))


def _unlink_with_retry(path: Path) -> None:
    for delay in (0.0, 0.01, 0.03, 0.08):
        if delay:
            time.sleep(delay)
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError as error:
            if getattr(error, "winerror", None) not in _WINDOWS_TRANSIENT_UNLINK_ERRORS:
                raise
    path.unlink(missing_ok=True)


def _now() -> datetime:
    return datetime.now(UTC)


def _retry_path(root: Path, slug: str) -> Path:
    return root / "topics" / "logs" / slug / "production-retry.yaml"


def _hash_path(path: Path, *, cacheable: bool) -> str:
    if not cacheable:
        return sha256_file(path)
    st = path.stat()
    key = (str(path), st.st_mtime_ns, st.st_size)
    cached = _CODE_HASH_CACHE.get(key)
    if cached is None:
        cached = sha256_file(path)
        _CODE_HASH_CACHE[key] = cached
    return cached


def _hash_cached_entry(path: Path) -> str | None:
    try:
        st = path.stat()
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    key = (str(path), st.st_mtime_ns, st.st_size)
    cached = _CODE_HASH_CACHE.get(key)
    if cached is None:
        try:
            cached = sha256_file(path)
        except OSError:
            return None
        _CODE_HASH_CACHE[key] = cached
    return cached


_CODE_SUFFIXES: dict[str, tuple[str, ...]] = {
    "profiles": (".yaml",),
    "tools": (".py",),
    "video/src": (".ts", ".tsx"),
}


def _walk_code_files(base: Path, *, include_agent_inputs: bool) -> list[Path]:
    found: list[Path] = []
    prompts_dir = (base / "src/healthvideo/prompts").resolve()
    folders: tuple[str, ...] = (
        ("profiles", "src/healthvideo", ".agents/skills", "tools", "video/src")
        if include_agent_inputs
        else ("profiles", "src/healthvideo", "tools", "video/src")
    )
    for folder in folders:
        start = base / folder
        if not start.is_dir():
            continue
        suffixes = _CODE_SUFFIXES.get(folder)
        for dirpath, dirnames, filenames in os.walk(start):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_CODE_WALK_DIRS]
            dir_path = Path(dirpath)
            if suffixes is not None:
                found.extend(dir_path / name for name in filenames if name.endswith(suffixes))
            elif folder == ".agents/skills":
                found.extend(dir_path / name for name in filenames if name == "SKILL.md")
            elif folder == "src/healthvideo":
                in_prompts = include_agent_inputs and (
                    dir_path == prompts_dir or dir_path.resolve().is_relative_to(prompts_dir)
                )
                for name in filenames:
                    if name.endswith(".py") or (in_prompts and name.endswith(".md")):
                        found.append(dir_path / name)
    return found


def _collect_code_hashes(
    files: dict[str, Any],
    root: Path,
    project_dir: Path,
    *,
    include_agent_inputs: bool,
) -> None:
    code_root = Path(__file__).resolve().parents[3]
    root_resolved = root.resolve()
    project_resolved = project_dir.resolve()
    for base in dict.fromkeys((root_resolved, code_root)):
        in_work_root = base.is_relative_to(root_resolved) or base.is_relative_to(
            project_resolved
        )
        if in_work_root:
            for path in _walk_code_files(base, include_agent_inputs=include_agent_inputs):
                try:
                    resolved = path.resolve()
                    if not resolved.is_file():
                        continue
                    files[str(resolved)] = _hash_path(resolved, cacheable=False)
                except OSError:
                    continue
        else:
            cache_key = (str(base), include_agent_inputs)
            entries = _STATIC_CODE_FILES_CACHE.get(cache_key)
            if entries is None:
                scanned: list[tuple[str, Path]] = []
                for path in _walk_code_files(base, include_agent_inputs=include_agent_inputs):
                    try:
                        resolved = path.resolve()
                        if resolved.is_file():
                            scanned.append((str(resolved), resolved))
                    except OSError:
                        continue
                entries = scanned
                _STATIC_CODE_FILES_CACHE[cache_key] = entries
            for resolved_str, resolved in entries:
                digest = _hash_cached_entry(resolved)
                if digest is not None:
                    files[resolved_str] = digest


def production_fingerprint(root: Path, project_dir: Path, state: WorkflowState) -> str:
    """Ignore generated audio/renders/logs; retry validation only after an input fix."""
    paths = {project_dir / "project.yaml"}
    for folder in ("script", "storyboard", "evidence", "explainer", "assets", "posts"):
        paths.update((project_dir / "revisions").glob(f"*/{folder}/**/*.yaml"))
    paths.update((project_dir / "revisions").glob("*/assets/**/*"))
    for relative in (
        "reviews/visual-review.yaml",
        "reviews/visual/candidates.yaml",
        "reviews/medical-approval.yaml",
        "reviews/changes/*requested.yaml",
    ):
        paths.update((project_dir / "revisions").glob(f"*/{relative}"))
    files: dict[str, str] = {}
    for path in sorted(paths):
        if not path.is_file():
            continue
        resolved = path.resolve()
        files[str(resolved)] = _hash_path(resolved, cacheable=False)
    _collect_code_hashes(files, root, project_dir, include_agent_inputs=False)
    guidance = root / "topics/logs" / project_dir.name / "leader-guidance.yaml"
    if guidance.is_file():
        resolved = guidance.resolve()
        files[str(resolved)] = _hash_path(resolved, cacheable=False)
    return canonical_json_hash({"state": state.value, "files": files})


def _sanitize_reason(error: Exception) -> str:
    text = " ".join(f"{type(error).__name__}: {error}".split())
    for env_key in _SECRET_ENV_KEYS:
        secret = os.environ.get(env_key, "").strip()
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(
        r"(?i)\b(xi-api-key|api[_-]?key|token|secret|password|authorization)\s*([:=])\s*\S+",
        r"\1\2[REDACTED]",
        text,
    )
    return text or type(error).__name__


def _read_retry_yaml(path: Path) -> dict[str, Any]:
    """Retry short file locks, preserving OSError if still unavailable.

    Never mistake unreadable metadata for corrupt metadata, or reset its budget.
    The runner can try again on its next scan; no paid work runs without a read.
    """
    for attempt, delay in enumerate((0.0, 0.01, 0.03, 0.08, 0.15)):
        if delay:
            time.sleep(delay)
        try:
            return read_yaml(path)
        except OSError as error:
            if classify_failure(error) != 'transient' or attempt == 4:
                raise
    raise AssertionError('unreachable')


def _read_retry_record(path: Path) -> dict[str, Any]:
    try:
        data = _read_retry_yaml(path)
        fingerprint = data.get("fingerprint")
        kind = data.get("kind")
        attempts = data.get("attempts")
        reason = data.get("reason")
        retry_after = data.get("retry_after")
    except OSError as error:
        if classify_failure(error) == "transient":
            raise
        raise ValueError(f"Invalid production retry record in {path}") from error
    except (ValueError, TypeError, AttributeError, yaml.YAMLError) as error:
        raise ValueError(
            f"Invalid production retry record in {path}; restore or remove it before retrying"
        ) from error
    if (
        type(fingerprint) is not str
        or not fingerprint.strip()
        or kind not in {"validation", "transient"}
        or type(attempts) is not int
        or attempts < 1
        or type(reason) is not str
        or not reason.strip()
    ):
        raise ValueError(
            f"Invalid production retry record in {path}; restore or remove it before retrying"
        )
    if retry_after is not None:
        if type(retry_after) is not str:
            raise ValueError(
                f"Invalid production retry record in {path}; restore or remove it before retrying"
            )
        try:
            parsed = datetime.fromisoformat(retry_after)
        except ValueError as error:
            raise ValueError(
                f"Invalid production retry record in {path}; restore or remove it before retrying"
            ) from error
        if parsed.tzinfo is None:
            raise ValueError(
                f"Invalid production retry record in {path}; restore or remove it before retrying"
            )
    if kind == "transient" and attempts < MAX_TRANSIENT_ATTEMPTS and retry_after is None:
        raise ValueError(
            f"Invalid production retry record in {path}; restore or remove it before retrying"
        )
    return {
        "fingerprint": fingerprint,
        "kind": kind,
        "attempts": attempts,
        "reason": reason,
        "retry_after": retry_after,
    }


def retry_status(root: Path, project_dir: Path, state: WorkflowState) -> dict[str, Any]:
    """Return whether production may run without making any network calls."""
    path = _retry_path(root, project_dir.name)
    if not path.exists():
        return {
            "allowed": True,
            "kind": None,
            "attempts": 0,
            "reason": None,
            "retry_after": None,
        }
    record = _read_retry_record(path)
    current_fp = production_fingerprint(root, project_dir, state)
    if record["fingerprint"] != current_fp:
        return {
            "allowed": True,
            "kind": None,
            "attempts": 0,
            "reason": None,
            "retry_after": None,
        }
    if record["kind"] == "validation" or record["attempts"] >= MAX_TRANSIENT_ATTEMPTS:
        return {
            "allowed": False,
            "kind": record["kind"],
            "attempts": record["attempts"],
            "reason": record["reason"],
            "retry_after": None,
        }
    retry_after_dt = datetime.fromisoformat(record["retry_after"])
    return {
        "allowed": _now() >= retry_after_dt,
        "kind": "transient",
        "attempts": record["attempts"],
        "reason": record["reason"],
        "retry_after": record["retry_after"],
    }


def record_failure(
    root: Path, project_dir: Path, state: WorkflowState, error: Exception
) -> None:
    """Persist validation hold or bounded transient retry metadata atomically."""
    path = _retry_path(root, project_dir.name)
    existing = _read_retry_record(path) if path.exists() else None
    fingerprint = production_fingerprint(root, project_dir, state)
    kind: Literal["validation", "transient"] = (
        "transient" if _is_transient_production_error(error) else "validation"
    )
    if (
        existing is not None
        and existing["fingerprint"] == fingerprint
        and existing["kind"] == kind
    ):
        attempts = existing["attempts"] + 1
    else:
        attempts = 1
    retry_after: str | None = None
    if kind == "transient" and attempts < MAX_TRANSIENT_ATTEMPTS:
        delay = TRANSIENT_BACKOFF_SECONDS[attempts]
        retry_after = (_now() + timedelta(seconds=delay)).isoformat()
    write_yaml_atomic(
        path,
        {
            "fingerprint": fingerprint,
            "kind": kind,
            "attempts": attempts,
            "reason": _sanitize_reason(error),
            "retry_after": retry_after,
        },
    )


def clear_retry(root: Path, slug: str) -> None:
    """Remove only the production retry record, preserving unrelated block notes."""
    _unlink_with_retry(_retry_path(root, slug))


# Agent budgets are independent of the existing production budget. Only a clearly
# classified transient CLI failure can spend another automatic attempt.
AGENT_RETRY_FILE = "agent-retry.yaml"
_AGENT_FAILURE_KINDS = {"transient", "validation", "configuration", "agent_error"}
_AGENT_INPUTS = {
    "research": ("script/questions.yaml", "script/script.yaml"),
    "draft": ("evidence/**", "explainer/**", "script/questions.yaml", "reviews/script-review-log.yaml"),
    "storyboard_design": ("script/script.yaml", "script/outline.yaml", "explainer/**", "evidence/**"),
    "voice_prep": ("script/script.yaml",),
    "revise_medical": ("evidence/**", "explainer/**", "script/questions.yaml"),
    "script_review": ("script/**", "storyboard/**", "evidence/**", "explainer/**", "assets/*.yaml"),
    "posts": ("script/**", "storyboard/**", "evidence/**"),
    "shorts_plan": ("script/**", "storyboard/**", "evidence/**"),
    "visual_review": ("storyboard/**", "assets/*.yaml", "reviews/visual/candidates.yaml",
                      "posts/shorts-plan.yaml"),
    "produce": ("script/**", "storyboard/**", "evidence/**", "explainer/**", "assets/**", "posts/**",
                "reviews/visual-review.yaml", "reviews/medical-approval.yaml"),
    "product_review": ("script/**", "storyboard/**", "posts/**", "renders/render-manifest.json",
                       "renders/scene-timing.json", "renders/render-input.json", "reviews/video-qa.json"),
    "revise_product": ("script/**", "storyboard/**", "evidence/**", "explainer/**",
                       "reviews/product-review-log.yaml", "renders/render-input*.json"),
    "revise_production": ("script/**", "evidence/**", "explainer/**"),
}


def agent_fingerprint(root: Path, project_dir: Path, step: str, prompt: str) -> str:
    """Hash consumed inputs, excluding the step's own mutable output and logs.

    A research retry must not receive a fresh budget for writing a partial ledger;
    similarly a writer's partial script is an output, not a new writing brief.
    Questions are normalized because the expert writes their answer in that file.
    """
    manifest = project_dir / "project.yaml"
    revision = str(read_yaml(manifest).get("active_revision", "001")) if manifest.exists() else "001"
    if not re.fullmatch(r"\d{3}", revision):
        raise ValueError("Invalid active_revision for agent retry fingerprint")
    revision_dir = project_dir / "revisions" / revision
    paths: set[Path] = set()
    for pattern in _AGENT_INPUTS.get(step, ()):
        # pathlib's terminal ** matches directories; append * to include all files.
        paths.update(revision_dir.glob(pattern + "/*" if pattern.endswith("/**") else pattern))
    for pattern in ("reviews/**/*rejected*.yaml", "reviews/**/*reopened*.yaml",
                    "reviews/changes/*requested.yaml", "workflow.yaml"):
        paths.update(revision_dir.glob(pattern))
    files: dict[str, Any] = {}
    for path in sorted(paths):
        if not path.is_file():
            continue
        if path == revision_dir / "script/questions.yaml" and step in {"research", "draft", "revise_medical"}:
            data = read_yaml(path)
            questions = data.get("questions", [])
            if not isinstance(questions, list) or not all(isinstance(q, dict) for q in questions):
                raise ValueError("Invalid writer questions for agent retry fingerprint")
            if step == "research":
                questions = [{key: value for key, value in question.items()
                              if key not in {"answer", "claim_ids"}} for question in questions]
            else:
                questions = [question for question in questions if str(question.get("answer") or "").strip()]
            # An absent questions file and no consumed questions are equivalent.
            if questions:
                files[str(path.resolve())] = questions
        elif path == revision_dir / "workflow.yaml":
            reason = read_yaml(path).get("reason")
            if reason:
                files[str(path.resolve())] = {"reason": reason}
        elif path in {revision_dir / "reviews/product-review-log.yaml",
                      revision_dir / "reviews/script-review-log.yaml"}:
            rounds = read_yaml(path).get("rounds", [])
            if not isinstance(rounds, list) or not all(isinstance(item, dict) for item in rounds):
                raise ValueError("Invalid product review history for agent retry fingerprint")
            if rounds:
                files[str(path.resolve())] = {key: value for key, value in rounds[-1].items()
                                             if key != "fix_attempted"}
        else:
            files[str(path.resolve())] = _hash_path(path, cacheable=False)
    _collect_code_hashes(files, root, project_dir, include_agent_inputs=True)
    guidance = root / "topics/logs" / project_dir.name / "leader-guidance.yaml"
    if guidance.is_file():
        resolved = guidance.resolve()
        files[str(resolved)] = _hash_path(resolved, cacheable=False)
    return canonical_json_hash({"step": step, "revision": revision, "prompt": prompt, "files": files})


def _agent_path(root: Path, slug: str) -> Path:
    return root / "topics" / "logs" / slug / AGENT_RETRY_FILE


def _agent_records(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        data = _read_retry_yaml(path)
        steps = data["steps"]
        if data.get("version") != 1 or not isinstance(steps, dict):
            raise ValueError("invalid agent retry schema")
        for step, record in steps.items():
            if step not in _AGENT_INPUTS or not isinstance(record, dict):
                raise ValueError("invalid agent retry step")
            if (not isinstance(record.get("fingerprint"), str) or not record["fingerprint"]
                    or record.get("kind") not in _AGENT_FAILURE_KINDS
                    or type(record.get("attempts")) is not int or record["attempts"] < 1
                    or not isinstance(record.get("reason"), str) or not record["reason"]):
                raise ValueError("invalid agent retry record")
            consecutive = record.get("consecutive_failures", 1)
            if type(consecutive) is not int or consecutive < 1:
                raise ValueError("invalid consecutive failure count")
            deadline = record.get("retry_after")
            if deadline is not None and (not isinstance(deadline, str)
                                         or datetime.fromisoformat(deadline).tzinfo is None):
                raise ValueError("invalid agent retry deadline")
            if (record["kind"] == "transient" and record["attempts"] < MAX_TRANSIENT_ATTEMPTS
                    and deadline is None):
                raise ValueError("missing agent retry deadline")
        return steps
    except OSError as exc:
        if classify_failure(exc) == "transient":
            raise
        raise ValueError(f"Invalid retry record in {path}") from exc
    except (ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
        raise ValueError(f"Invalid agent retry record in {path}; restore or remove it before retrying") from exc


def agent_retry_status(root: Path, project_dir: Path, step: str, fingerprint: str) -> dict[str, Any]:
    """Read a persisted budget before invoking a paid agent; corrupt records hold."""
    records = _agent_records(_agent_path(root, project_dir.name))
    record = records.get(step)
    if record is None or record["fingerprint"] != fingerprint:
        if record is not None:
            clear_agent_retry(root, project_dir.name, step)
        return {"allowed": True, "kind": None, "attempts": 0, "reason": None, "retry_after": None}
    allowed = (record["kind"] == "transient" and record["attempts"] < MAX_TRANSIENT_ATTEMPTS
               and _now() >= datetime.fromisoformat(record["retry_after"]))
    return {**record, "allowed": allowed}


def record_agent_failure(root: Path, project_dir: Path, step: str, fingerprint: str,
                         kind: str | None, error: Exception, *,
                         observed_fingerprint: str | None = None) -> None:
    path = _agent_path(root, project_dir.name)
    records = _agent_records(path)
    previous = records.get(step)
    attempts = (previous["attempts"] if previous and previous["fingerprint"] == fingerprint else 0) + 1
    reason = _sanitize_reason(error)
    consecutive = (previous.get("consecutive_failures", 1)
                   if previous and previous["fingerprint"] == fingerprint
                   and previous["reason"] == reason else 0) + 1
    kind = kind if kind in _AGENT_FAILURE_KINDS else "agent_error"
    if is_file_contention(error):
        kind = classify_failure(error, consecutive_failures=consecutive)
    deadline = None
    if kind == "transient" and attempts < MAX_TRANSIENT_ATTEMPTS:
        deadline = (_now() + timedelta(seconds=TRANSIENT_BACKOFF_SECONDS[attempts])).isoformat()
    records[step] = {"fingerprint": observed_fingerprint or fingerprint, "kind": kind, "attempts": attempts,
                     "reason": reason, "retry_after": deadline, "consecutive_failures": consecutive}
    write_yaml_atomic(path, {"version": 1, "steps": records})


def outstanding_agent_retry(root: Path, project_dir: Path,
                            brief_context: str) -> tuple[str, dict[str, Any]] | None:
    """Guard a failed step before its partial outputs can select a different role."""
    for step in _agent_records(_agent_path(root, project_dir.name)):
        fingerprint = agent_fingerprint(root, project_dir, step, brief_context)
        status = agent_retry_status(root, project_dir, step, fingerprint)
        if status["kind"] is not None:
            return step, status
    return None


def _model_resume_path(root: Path, slug: str) -> Path:
    return root / "topics" / "logs" / slug / "waiting-model-step.yaml"


def model_resume_step(root: Path, project_dir: Path, brief_context: str) -> str | None:
    """Bind quota resumption to the original task without spending a retry."""
    path = _model_resume_path(root, project_dir.name)
    if not path.exists():
        return None
    try:
        data = _read_retry_yaml(path)
        step, fingerprint = data["step"], data["fingerprint"]
        if (data.get("version") != 1 or step not in _AGENT_INPUTS
                or not isinstance(fingerprint, str) or not fingerprint):
            raise ValueError("invalid model resumption")
    except OSError as exc:
        if classify_failure(exc) == "transient":
            raise
        raise ValueError(f"Invalid retry record in {path}") from exc
    except (ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
        raise ValueError(f"Invalid model resume record in {path}; restore or remove it before retrying") from exc
    if agent_fingerprint(root, project_dir, step, brief_context) != fingerprint:
        _unlink_with_retry(path)
        return None
    return step


def record_model_resume(root: Path, project_dir: Path, step: str, brief_context: str) -> None:
    """Observe quota-attempt writes while keeping an existing budget unchanged."""
    model_resume_step(root, project_dir, brief_context)  # corrupt metadata always fails closed
    fingerprint = agent_fingerprint(root, project_dir, step, brief_context)
    path = _agent_path(root, project_dir.name)
    records = _agent_records(path)
    if step in records:
        records[step]["fingerprint"] = fingerprint
        write_yaml_atomic(path, {"version": 1, "steps": records})
    write_yaml_atomic(_model_resume_path(root, project_dir.name),
                      {"version": 1, "step": step, "fingerprint": fingerprint})


def clear_model_resume(root: Path, slug: str) -> None:
    _unlink_with_retry(_model_resume_path(root, slug))


def clear_agent_retry(root: Path, slug: str, step: str) -> None:
    path = _agent_path(root, slug)
    records = _agent_records(path)
    records.pop(step, None)
    if records:
        write_yaml_atomic(path, {"version": 1, "steps": records})
    else:
        _unlink_with_retry(path)


def retry_deadlines(root: Path, slug: str) -> list[datetime]:
    """Future retry wakeups; bad records remain held by the runner."""
    try:
        records = list(_agent_records(_agent_path(root, slug)).values())
        production = _retry_path(root, slug)
        if production.exists():
            records.append(_read_retry_record(production))
        return [moment for record in records if record.get("retry_after")
                and (moment := datetime.fromisoformat(record["retry_after"])) > _now()]
    except OSError:
        return []
    except ValueError:
        return []
