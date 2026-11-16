"""Select the next factory workflow step for a project state and run the queue."""

import inspect
import json
import os
import subprocess
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from healthvideo.agents import (
    ACTIVITY_FILE,
    AgentResult,
    AllAgentsExhausted,
    invoke_with_failover,
)
from healthvideo.company import (
    CRITIC_OF,
    Company,
    ModelSlot,
    load_company,
    role_skill_block,
)
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.process import process_token
from healthvideo.storage.files import (
    read_yaml,
    write_text_atomic,
    write_yaml_atomic,
)
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.storage.queue import load_queue
from healthvideo.workflows import change_request, chat, expert, product_review
from healthvideo.workflows.production_retry import (
    _sanitize_reason,
    agent_fingerprint,
    agent_retry_status,
    clear_agent_retry,
    clear_model_resume,
    clear_retry,
    model_resume_step,
    outstanding_agent_retry,
    record_agent_failure,
    record_failure,
    record_model_resume,
    retry_deadlines,
    retry_status,
)
from healthvideo.workflows.script_review import (
    next_script_action,
    record_review,
    revision_notes,
    script_hash,
)
from healthvideo.workflows.standards import prompt_block
from healthvideo.workflows.visual_review import review_pending

StepKind = Literal[
    "create",
    "research",
    "draft",
    "storyboard_design",
    "voice_prep",
    "script_review",
    "submit_medical",
    "posts",
    "shorts_plan",
    "produce",
    "visual_review",
    "product_review",
    "revise_product",
    "submit_video",
    "revise_medical",
    "revise_production",
]
AGENT_STEPS: frozenset[str] = frozenset(
    {
        "research",
        "draft",
        "storyboard_design",
        "voice_prep",
        "script_review",
        "posts",
        "shorts_plan",
        "visual_review",
        "product_review",
        "revise_product",
        "revise_medical",
        "revise_production",
    }
)

_STEP_BY_STATE: dict[WorkflowState, StepKind] = {
    WorkflowState.TOPIC_SELECTED: "research",
    WorkflowState.RESEARCH_IN_PROGRESS: "research",
    WorkflowState.EVIDENCE_READY: "draft",
    WorkflowState.DRAFT_READY: "script_review",
    WorkflowState.MEDICALLY_APPROVED: "produce",
    WorkflowState.PRODUCTION_IN_PROGRESS: "produce",
    WorkflowState.NEEDS_MEDICAL_REVISION: "revise_medical",
    WorkflowState.NEEDS_PRODUCTION_REVISION: "revise_production",
}


def next_step(state: WorkflowState | None) -> StepKind | None:
    """Return the next factory step for the given workflow state, or None."""
    if state is None:
        return "create"
    return _STEP_BY_STATE.get(state)


PROMPTS_DIR: Path = Path(__file__).resolve().parent.parent / "prompts"
PAUSED_FILE: str = "paused.yaml"


def is_project_paused(root: Path, slug: str) -> bool:
    """Return True if automation for this project has been paused by the doctor."""
    return (root / "topics" / "logs" / slug / PAUSED_FILE).is_file()

HARD_RULES: tuple[str, ...] = (
    "Không chép toàn văn hay đoạn dài từ nguồn vào project; trích dẫn ≤ 25 từ kèm locator.",
    "Không tự sinh SVG/PNG giả làm ảnh nguồn; diễn giải ledger dùng visual source_card, evidence_highlight chỉ dùng crop nguồn thật đã đăng ký giấy phép.",
    "Không bịa nguồn, DOI, PMID, số liệu, kết quả nghiên cứu hay trải nghiệm của bác sĩ; mọi khẳng định y khoa phải trỏ tới claim trong ledger.",
    "Không bao giờ chạy `healthvideo review approve` hay `healthvideo review set-pin`, không tạo hoặc sửa file approval; hai cổng duyệt chỉ do bác sĩ quyết.",
    "Không commit, không push, không đổi nhánh git.",
    "Chỉ sửa file trong thư mục project được giao; ngoại lệ duy nhất là thêm component SVG mới trong `video/src/anatomy/` kèm test.",
    "Không đăng bài hay tải gì lên mạng xã hội.",
)

PROMPT_FIELDS: tuple[str, ...] = (
    "project",
    "slug",
    "title",
    "question",
    "doctor_note",
    "reject_note",
)


def render_prompt(step: str, *, company: Company | None = None, **fields: str) -> str:
    """Render the fixed prompt template for an agent workflow step."""
    if step not in AGENT_STEPS:
        msg = f"Unknown agent step: {step!r}"
        raise ValueError(msg)
    unknown = set(fields) - set(PROMPT_FIELDS)
    if unknown:
        msg = f"Unknown prompt fields: {sorted(unknown)!r}"
        raise ValueError(msg)
    text = (PROMPTS_DIR / f"{step}.md").read_text(encoding="utf-8")
    for name in PROMPT_FIELDS:
        value = fields.get(name)
        replacement = value if value is not None else "(không có)"
        text = text.replace(f"{{{name}}}", replacement)
    if step in {"draft", "script_review", "revise_medical"}:
        for name in ("style_examples.vi.md", "ai_writing_signs.vi.md"):
            examples_path = PROMPTS_DIR / name
            if examples_path.is_file():
                examples = examples_path.read_text(encoding="utf-8").strip()
                text = f"{text.rstrip()}\n\n{examples}\n"
    company = company or load_company()
    skills_block = role_skill_block(company.role_for_step(step).id, company)
    if skills_block:
        text = f"{text.rstrip()}\n\n{skills_block.rstrip()}\n"
    rules_block = "\n".join(f"- {rule}" for rule in HARD_RULES)
    return f"{text.rstrip()}\n\n## Quy tắc cứng\n{rules_block}\n"


@dataclass(frozen=True)
class RunDeps:
    """Injected dependencies for running the topic queue."""

    create_project: Callable[[Path, QueueEntry], Path]
    read_state: Callable[[Path], WorkflowState]
    reject_note: Callable[[Path], str | None]
    python_steps: Mapping[str, Callable[[Path], None]]
    changed_code_paths: Callable[[Path], list[Path]]
    invoke: Callable[..., AgentResult] = invoke_with_failover
    posts_ready: Callable[[Path], bool] = lambda _: True
    storyboard_ready: Callable[[Path], bool] = lambda _: True
    voice_prep_ready: Callable[[Path], bool] = lambda _: True
    shorts_plan_ready: Callable[[Path], bool] = lambda _: True
    parallel_branches: bool = False
    code_snapshot: Callable[[Path], dict[str, str]] | None = None
    visual_review_pending: Callable[[Path], bool] = review_pending
    product_review_pending: Callable[[Path], bool] = product_review.pending
    # Spec 5.8: the writer starts only after the medical expert's brief exists. Production
    # wires ``expert.expert_brief_ready`` (factory_deps), like ``posts_ready``.
    expert_brief_ready: Callable[[Path], bool] = lambda _: True
    # Role table: which (cli, model) chain runs each agent step.
    company: Company = field(default_factory=load_company)


_REPORT_LOCK = threading.RLock()
_GPU_THREAD_LOCK = threading.Lock()
_TOPIC_LOCKS_GUARD = threading.Lock()
_TOPIC_LOCKS: dict[str, threading.RLock] = {}


def _topic_lock(slug: str) -> threading.RLock:
    with _TOPIC_LOCKS_GUARD:
        lock = _TOPIC_LOCKS.get(slug)
        if lock is None:
            lock = threading.RLock()
            _TOPIC_LOCKS[slug] = lock
        return lock


@contextmanager
def gpu_mutex(root: Path) -> Iterator[None]:
    """Serialize heavy RTX 3060 GPU/TTS/Remotion production across threads and processes."""
    lock_file = root / "cache" / "gpu-mutex.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    with _GPU_THREAD_LOCK, lock_file.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        if os.name == "nt":
            import msvcrt

            while True:
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _maker_slots_for_critic(
    root: Path,
    slug: str,
    critic_role: str,
    company: Company | None = None,
) -> tuple[ModelSlot, ...]:
    maker_order = CRITIC_OF.get(critic_role, ())
    maker_roles = set(maker_order)
    if not maker_roles:
        return ()
    act_path = root / ACTIVITY_FILE
    if not act_path.is_file():
        return ()
    latest_by_role: dict[str, ModelSlot] = {}
    try:
        for line in act_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            role = row.get("role")
            if (
                row.get("slug") == slug
                and role in maker_roles
                and row.get("ok") is True
                and row.get("cli")
                and row.get("model")
            ):
                latest_by_role[str(role)] = ModelSlot(cli=str(row["cli"]), model=str(row["model"]))
    except (OSError, ValueError):
        return ()
    if not latest_by_role:
        return ()
    excluded = tuple(dict.fromkeys(latest_by_role.values()))
    active_company = company or load_company()
    critic_chain = list(active_company.chain(critic_role))
    excluded_identities = {slot.model_identity for slot in excluded}
    if not [slot for slot in critic_chain if slot.model_identity not in excluded_identities]:
        primary_role = maker_order[0]
        primary_slot = latest_by_role.get(primary_role)
        if primary_slot is not None and any(slot.model_identity != primary_slot.model_identity
                                            for slot in critic_chain):
            return (primary_slot,)
    return excluded


def _invoke_supports_exclude(invoke_fn: object) -> bool:
    try:
        sig = inspect.signature(invoke_fn)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return "exclude_slots" in sig.parameters or any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()
    )


@dataclass
class RunReport:
    """Summary report produced by a queue run."""

    advanced: list[str] = field(default_factory=list)
    at_gate: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    code_changes: list[Path] = field(default_factory=list)
    # Topics paused until a model of their chain returns from quota rest.
    waiting_model: list[str] = field(default_factory=list)


WAITING_MODEL_FILE = "waiting-model.txt"


def waiting_until(root: Path, slug: str) -> datetime | None:
    """When a topic paused for quota may run again; None if unknown or not paused."""
    path = root / "topics" / "logs" / slug / WAITING_MODEL_FILE
    try:
        moment = datetime.fromisoformat(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return moment if moment.tzinfo else moment.astimezone()


def _mark_advanced(root: Path, slug: str, report: RunReport) -> None:
    """Record progress and drop a stale block note from an earlier run."""
    with _REPORT_LOCK:
        if slug not in report.advanced:
            report.advanced.append(slug)
        (root / "topics" / "logs" / slug / "blocked.txt").unlink(missing_ok=True)


def _mark_blocked(
    root: Path,
    slug: str,
    reason: str,
    report: RunReport,
    *,
    log_path: Path | None = None,
) -> None:
    with _REPORT_LOCK:
        if slug not in report.blocked:
            report.blocked.append(slug)
        blocked_file = root / "topics" / "logs" / slug / "blocked.txt"
        detail = (
            f"{reason}\nlog_path: {log_path}\n"
            if log_path is not None
            else f"{reason}\n"
        )
        write_text_atomic(blocked_file, detail)


def _unused_answers(project_dir: Path) -> str | None:
    """Why a writer rewrite is unfinished: expert answers still waiting in questions.yaml."""
    try:
        if expert.answered_questions(project_dir):
            return (
                "biên kịch chưa đưa câu trả lời của chuyên gia vào kịch bản "
                f"(còn câu đã trả lời trong {expert.QUESTIONS})"
            )
    except (OSError, TypeError, ValueError) as exc:
        return f"câu hỏi của biên kịch lỗi: {exc}"
    return None


def _expert_unfinished(project_dir: Path, deps: RunDeps, state: WorkflowState) -> str | None:
    """Why a research step is not done yet (spec 5.8), or None."""
    if state == WorkflowState.DRAFT_READY:
        try:
            if expert.open_questions(project_dir):
                return f"chuyên gia chưa trả lời hết câu hỏi trong {expert.QUESTIONS}"
        except (OSError, TypeError, ValueError) as exc:
            return f"câu hỏi của biên kịch lỗi: {exc}"
        return None
    if not deps.expert_brief_ready(project_dir):
        return f"chưa có {expert.EXPERT_BRIEF}: bước research chưa xong"
    return None


def _record_code_changes(
    root: Path,
    slug: str,
    deps: RunDeps,
    report: RunReport,
    before: dict[str, str] | None = None,
) -> None:
    if before is not None and deps.code_snapshot is not None:
        after = deps.code_snapshot(root)
        paths = [
            Path(path) for path in dict.fromkeys([*after, *before])
            if before.get(path) != after.get(path)
        ]
    else:
        paths = deps.changed_code_paths(root)
    new_paths: list[Path] = []
    with _REPORT_LOCK:
        for raw_path in paths:
            path = Path(raw_path)
            is_new = path not in report.code_changes
            if is_new:
                report.code_changes.append(path)
            if path not in new_paths and (before is not None or is_new):
                new_paths.append(path)
        if not new_paths:
            return

        review_file = root / "topics" / "code-review.yaml"
        existing_entries: list[dict[str, str]] = []
        if review_file.exists():
            data = read_yaml(review_file)
            raw_entries = data.get("entries", [])
            if isinstance(raw_entries, list):
                existing_entries = list(raw_entries)

        timestamp = datetime.now(UTC).isoformat()
        for path in new_paths:
            existing_entries.append(
                {
                    "path": path.as_posix(),
                    "slug": slug,
                    "at": timestamp,
                }
            )
        write_yaml_atomic(
            review_file,
            {
                "version": 1,
                "entries": existing_entries,
            },
        )


def _quarantine_review(project_dir: Path, step: str, log_dir: Path) -> None:
    """A prior invocation's unconsumed score is diagnostic, never a fresh review.

    Moving the file gives this invocation an empty output slot. Existing review
    validation then requires a newly written report for the captured input hash;
    timestamps and repeated report text cannot establish that relationship.
    """
    report = resolve_project_layout(project_dir).artifact_root / f"reviews/{step.replace('_', '-')}.yaml"
    if report.is_file():
        archive = log_dir / "review-artifacts" / f"{step}-{uuid4().hex}.yaml"
        archive.parent.mkdir(parents=True, exist_ok=True)
        report.rename(archive)


def _build_step_prompt(
    root: Path,
    deps: RunDeps,
    entry: QueueEntry,
    project_dir: Path,
    step: str,
    *,
    rewriting: bool = False,
    answering: bool = False,
) -> str:
    prompt_fields: dict[str, str] = {
        "project": str(project_dir),
        "slug": entry.slug,
        "title": entry.title,
        "question": entry.question,
        "doctor_note": entry.doctor_note or "",
    }
    if step.startswith("revise_") or step in {"draft", "script_review", "storyboard_design"}:
        prompt_fields["reject_note"] = deps.reject_note(project_dir) or ""
    if step == "revise_product":
        prompt_fields["reject_note"] = product_review.revision_notes(project_dir)
    if rewriting:
        notes = expert.answer_notes(project_dir) if answering else revision_notes(project_dir)
        prompt_fields["reject_note"] = f"{notes}\n{prompt_fields.get('reject_note', '')}".strip()
    if step in {"draft", "storyboard_design", "revise_product", "revise_production"}:
        blocked = root / 'topics/logs' / entry.slug / 'blocked.txt'
        if blocked.is_file():
            diagnostic = _sanitize_reason(RuntimeError(blocked.read_text(encoding='utf-8', errors='replace')))
            prompt_fields['reject_note'] = (prompt_fields.get('reject_note', '')
                                           + '\nLỗi kiểm tra cần sửa trong phạm vi bước này: '
                                           + diagnostic[-6000:])
    prompt = render_prompt(step, company=deps.company, **prompt_fields)
    standards_block = prompt_block(root, slug=entry.slug)
    if standards_block:
        body, heading, rules = prompt.rpartition("## Quy tắc cứng")
        prompt = f"{body.rstrip()}\n\n{standards_block.rstrip()}\n\n{heading}{rules}"
    return prompt


def _run_agent_invocation(
    root: Path,
    deps: RunDeps,
    entry: QueueEntry,
    project_dir: Path,
    report: RunReport,
    *,
    step: str,
    brief_context: str,
    log_dir: Path,
    rewriting: bool = False,
    answering: bool = False,
) -> tuple[str, Path | None, str | None, dict[str, str] | None]:
    """Run one agent step with fingerprint retry gating, failover & quarantine."""
    prompt = _build_step_prompt(
        root, deps, entry, project_dir, step, rewriting=rewriting, answering=answering
    )
    with _topic_lock(entry.slug):
        fingerprint = agent_fingerprint(root, project_dir, step, brief_context)
        status = agent_retry_status(root, project_dir, step, fingerprint)
        if not status["allowed"]:
            waiting = (
                f"đang chờ thử lại lúc {status['retry_after']}"
                if status["retry_after"]
                else "cần sửa đầu vào hoặc cấu hình"
            )
            _mark_blocked(
                root, entry.slug, f"bước {step}: {waiting}; {status['reason']}", report
            )
            return "blocked", None, None, None
    before = deps.code_snapshot(root) if deps.code_snapshot is not None else None
    reviewing = step in {"script_review", "product_review"}
    reviewed_hash = (
        script_hash(project_dir)
        if step == "script_review"
        else product_review.render_hash(project_dir)
        if reviewing
        else ""
    )
    if reviewing:
        _quarantine_review(project_dir, step, log_dir)
    role = deps.company.role_for_step(step)
    invoke_kwargs: dict[str, object] = {}
    if reviewing and _invoke_supports_exclude(deps.invoke):
        excluded = _maker_slots_for_critic(root, entry.slug, role.id, company=deps.company)
        if excluded:
            invoke_kwargs["exclude_slots"] = excluded
    try:
        result = deps.invoke(
            deps.company.chain(role.id),
            prompt,
            cwd=root,
            log_dir=log_dir,
            role=role.id,
            slug=entry.slug,
            step=step,
            **invoke_kwargs,
        )
    except AllAgentsExhausted as exc:
        with _topic_lock(entry.slug):
            record_model_resume(root, project_dir, step, brief_context)
        _record_code_changes(root, entry.slug, deps, report, before)
        back = exc.earliest_return
        write_text_atomic(
            root / "topics" / "logs" / entry.slug / WAITING_MODEL_FILE,
            back.isoformat() if back else "",
        )
        with _REPORT_LOCK:
            if entry.slug not in report.waiting_model:
                report.waiting_model.append(entry.slug)
        return "waiting_model", None, None, None
    except Exception as exc:  # noqa: BLE001 — a failed tool holds only this topic
        if is_project_paused(root, entry.slug):
            return "paused", None, None, None
        kind = (
            "transient"
            if isinstance(exc, (TimeoutError, ConnectionError, subprocess.TimeoutExpired))
            else "configuration"
            if isinstance(exc, (FileNotFoundError, PermissionError))
            else "agent_error"
        )
        with _topic_lock(entry.slug):
            record_agent_failure(
                root,
                project_dir,
                step,
                fingerprint,
                kind,
                exc,
                observed_fingerprint=agent_fingerprint(root, project_dir, step, brief_context),
            )
        _record_code_changes(root, entry.slug, deps, report, before)
        _mark_blocked(
            root, entry.slug, f"bước {step} lỗi: {_sanitize_reason(exc)}", report
        )
        return "blocked", None, None, None

    if not result.ok:
        if is_project_paused(root, entry.slug):
            return "paused", result.log_path, None, None
        with _topic_lock(entry.slug):
            record_agent_failure(
                root,
                project_dir,
                step,
                fingerprint,
                getattr(result, "failure_kind", None),
                RuntimeError(
                    f"agent {result.agent} thất bại ở bước {step}; log_path: {result.log_path}"
                ),
                observed_fingerprint=agent_fingerprint(root, project_dir, step, brief_context),
            )
        _record_code_changes(root, entry.slug, deps, report, before)
        _mark_blocked(
            root,
            entry.slug,
            f"agent {result.agent} thất bại ở bước {step}",
            report,
            log_path=result.log_path,
        )
        return "blocked", result.log_path, None, None

    with _topic_lock(entry.slug):
        record_agent_failure(
            root,
            project_dir,
            step,
            fingerprint,
            "validation",
            ValueError(f"bước {step}: đầu ra hoặc trạng thái chưa hợp lệ"),
            observed_fingerprint=agent_fingerprint(root, project_dir, step, brief_context),
        )
    _record_code_changes(root, entry.slug, deps, report, before)
    return "ok", result.log_path, reviewed_hash, {"fingerprint": fingerprint}


def _validate_nonstate_agent_step(
    deps: RunDeps, project_dir: Path, step: str
) -> str | None:
    if step == "posts" and not deps.posts_ready(project_dir):
        return "agent không làm đổi trạng thái: posts.yaml chưa hợp lệ"
    if step == "storyboard_design" and not deps.storyboard_ready(project_dir):
        return "agent không làm đổi trạng thái: storyboard.yaml chưa hợp lệ"
    if step == "voice_prep" and not deps.voice_prep_ready(project_dir):
        return "agent không làm đổi trạng thái: script/voice-prep.yaml chưa hợp lệ"
    if step == "shorts_plan" and not deps.shorts_plan_ready(project_dir):
        return "agent không làm đổi trạng thái: posts/shorts-plan.yaml chưa hợp lệ"
    return None


def _run_parallel_branches(
    root: Path,
    deps: RunDeps,
    entry: QueueEntry,
    project_dir: Path,
    report: RunReport,
    *,
    branches: tuple[str, ...],
    brief_context: str,
) -> tuple[str, int]:
    """Execute independent steps concurrently for the same topic with isolated log dirs."""
    outcomes: dict[str, tuple[str, Path | None, str | None]] = {}

    def run_branch(b_step: str) -> tuple[str, Path | None, str | None]:
        if b_step == "produce":
            try:
                with gpu_mutex(root), _production_running(root, entry.slug):
                    deps.python_steps["produce"](project_dir)
                clear_retry(root, entry.slug)
                return "ok", None, None
            except Exception as exc:  # noqa: BLE001
                record_failure(root, project_dir, deps.read_state(project_dir), exc)
                return "blocked", None, f"bước produce lỗi: {type(exc).__name__}: {exc}"
        b_log_dir = root / "topics" / "logs" / entry.slug / f"parallel-{b_step}"
        status, log_p, _, _ = _run_agent_invocation(
            root,
            deps,
            entry,
            project_dir,
            report,
            step=b_step,
            brief_context=brief_context,
            log_dir=b_log_dir,
        )
        if status != "ok":
            return status, log_p, None
        problem = _validate_nonstate_agent_step(deps, project_dir, b_step)
        if problem:
            return "blocked", log_p, problem
        with _topic_lock(entry.slug):
            clear_agent_retry(root, entry.slug, b_step)
            clear_model_resume(root, entry.slug)
        return "ok", log_p, None

    with ThreadPoolExecutor(max_workers=len(branches)) as pool:
        futures = {pool.submit(run_branch, b_step): b_step for b_step in branches}
        for future in as_completed(futures):
            b_step = futures[future]
            try:
                outcomes[b_step] = future.result()
            except Exception as exc:  # noqa: BLE001
                outcomes[b_step] = ("blocked", None, f"bước {b_step} lỗi: {_sanitize_reason(exc)}")

    if any(res[0] == "waiting_model" for res in outcomes.values()):
        return "waiting_model", len(branches)
    if any(res[0] == "paused" for res in outcomes.values()):
        return "paused", len(branches)
    for b_step in branches:
        st, log_p, err = outcomes[b_step]
        if st != "ok":
            if err:
                _mark_blocked(root, entry.slug, err, report, log_path=log_p)
            return "blocked", len(branches)
    _mark_advanced(root, entry.slug, report)
    return "ok", len(branches)


def _run_topic(
    root: Path,
    deps: RunDeps,
    topic: QueueEntry,
    report: RunReport,
    *,
    once: bool = False,
    max_steps_per_topic: int = 20,
) -> bool:
    """Advance queued topics automatically until a review gate or blocker."""
    entries = [topic]

    for entry in entries:
        if is_project_paused(root, entry.slug):
            continue
        waiting = root / "topics" / "logs" / entry.slug / WAITING_MODEL_FILE
        if waiting.exists():
            back = waiting_until(root, entry.slug)
            if back is not None and back > datetime.now(UTC):
                with _REPORT_LOCK:
                    report.waiting_model.append(entry.slug)
                continue
            waiting.unlink()
        project_dir = root / "projects" / entry.slug
        if not project_dir.exists():
            project_dir = deps.create_project(root, entry)

        steps_taken = 0
        # Dynamic rejection/answer instructions are already tracked as consumed
        # artifacts. Keep the queue brief stable when a failed agent mutates state.
        brief_context = json.dumps({"title": entry.title, "question": entry.question,
                                    "doctor_note": entry.doctor_note}, sort_keys=True)
        while True:
            with chat.step_boundary(root, entry.slug):
                if is_project_paused(root, entry.slug):
                    break
                state = deps.read_state(project_dir)
                pending_change = change_request.pending_note(project_dir)
                with _topic_lock(entry.slug):
                    quota_step = model_resume_step(root, project_dir, brief_context)
                    outstanding = outstanding_agent_retry(root, project_dir, brief_context)
                forced_step = outstanding[0] if outstanding else quota_step
                if outstanding and not outstanding[1]["allowed"]:
                    status = outstanding[1]
                    waiting = (f"đang chờ thử lại lúc {status['retry_after']}"
                               if status['retry_after'] else "cần sửa đầu vào hoặc cấu hình")
                    _mark_blocked(root, entry.slug,
                                  f"bước {forced_step}: {waiting}; {status['reason']}", report)
                    break
                step = forced_step or next_step(state)
                if step is None:
                    with _REPORT_LOCK:
                        if state == WorkflowState.BLOCKED:
                            if entry.slug not in report.blocked:
                                report.blocked.append(entry.slug)
                        elif state in (WorkflowState.PACKAGED, WorkflowState.PUBLISHED_MANUAL):
                            pass  # finished topics are not waiting at any gate
                        else:
                            if entry.slug not in report.at_gate:
                                report.at_gate.append(entry.slug)
                    break

                retrying_production = False
                if step == "produce":
                    try:
                        status = retry_status(root, project_dir, state)
                    except ValueError as exc:
                        _mark_blocked(root, entry.slug, str(exc), report)
                        break
                    if not status["allowed"]:
                        _mark_blocked(
                            root,
                            entry.slug,
                            f"bước produce lỗi: {status['reason']}",
                            report,
                        )
                        break
                    retrying_production = status["attempts"] > 0

                if step == "produce" and not retrying_production and deps.visual_review_pending(project_dir):
                    step = "visual_review"
                elif step == "produce" and not retrying_production and not forced_step:
                    need_posts = not deps.posts_ready(project_dir)
                    need_shorts = not deps.shorts_plan_ready(project_dir)
                    need_produce = not deps.product_review_pending(project_dir)
                    if deps.parallel_branches and (need_posts or need_shorts):
                        branches_to_run: list[str] = []
                        if need_posts:
                            branches_to_run.append("posts")
                        if need_shorts:
                            branches_to_run.append("shorts_plan")
                        if need_produce:
                            branches_to_run.append("produce")
                        if len(branches_to_run) > 1:
                            if steps_taken + len(branches_to_run) > max_steps_per_topic:
                                _mark_blocked(root, entry.slug, "vượt số bước", report)
                                break
                            outcome, delta = _run_parallel_branches(
                                root,
                                deps,
                                entry,
                                project_dir,
                                report,
                                branches=tuple(branches_to_run),
                                brief_context=brief_context,
                            )
                            steps_taken += delta
                            if outcome != "ok":
                                break
                            if once:
                                return True
                            continue
                        step = branches_to_run[0]
                    elif need_posts:
                        step = "posts"
                    elif need_shorts:
                        step = "shorts_plan"
                    elif deps.product_review_pending(project_dir):
                        try:
                            step = product_review.next_product_action(project_dir)
                        except (OSError, ValueError) as exc:
                            _mark_blocked(root, entry.slug, f"duyệt sản phẩm lỗi: {exc}", report)
                            break

                answering = False
                if step == "script_review":
                    # Spec 5.8: open writer questions go to the medical expert; answered ones go
                    # back to the writer before the critic reads the script.
                    try:
                        if expert.open_questions(project_dir):
                            step = "research"
                        elif expert.answered_questions(project_dir):
                            step, answering = "draft", True
                    except (OSError, TypeError, ValueError) as exc:
                        _mark_blocked(root, entry.slug, f"câu hỏi của biên kịch lỗi: {exc}", report)
                        break
                if step == "script_review":
                    try:
                        step = ('draft' if pending_change else next_script_action(project_dir))
                    except (OSError, ValueError) as exc:
                        _mark_blocked(root, entry.slug, f"chấm kịch bản lỗi: {exc}", report)
                        break
                if (step in {"script_review", "submit_medical"}
                        and state == WorkflowState.DRAFT_READY
                        and not pending_change and not forced_step):
                    need_sb = not deps.storyboard_ready(project_dir)
                    need_vp = not deps.voice_prep_ready(project_dir)
                    if deps.parallel_branches and need_sb and need_vp:
                        if steps_taken + 2 > max_steps_per_topic:
                            _mark_blocked(root, entry.slug, "vượt số bước", report)
                            break
                        outcome, delta = _run_parallel_branches(
                            root,
                            deps,
                            entry,
                            project_dir,
                            report,
                            branches=("storyboard_design", "voice_prep"),
                            brief_context=brief_context,
                        )
                        steps_taken += delta
                        if outcome != "ok":
                            break
                        if once:
                            return True
                        continue
                    if need_sb:
                        step = "storyboard_design"
                    elif need_vp:
                        step = "voice_prep"
                if (step == "draft" and state == WorkflowState.EVIDENCE_READY
                        and not deps.expert_brief_ready(project_dir)):
                    step = "research"  # no expert brief yet: the research step is not finished
                if forced_step:
                    step = forced_step
                rewriting = step == "draft" and state == WorkflowState.DRAFT_READY

                if steps_taken >= max_steps_per_topic:
                    _mark_blocked(root, entry.slug, "vượt số bước", report)
                    break

                log_dir = root / "topics" / "logs" / entry.slug
                result_log_path: Path | None = None

                if step in AGENT_STEPS:
                    reviewing = step in {"script_review", "product_review"}
                    reviewed_hash = (
                        script_hash(project_dir)
                        if step == "script_review"
                        else product_review.render_hash(project_dir)
                        if reviewing
                        else ""
                    )
                    outcome, result_log_path, _, _ = _run_agent_invocation(
                        root,
                        deps,
                        entry,
                        project_dir,
                        report,
                        step=step,
                        brief_context=brief_context,
                        log_dir=log_dir,
                        rewriting=rewriting,
                        answering=answering,
                    )
                    if outcome != "ok":
                        break
                    if is_project_paused(root, entry.slug):
                        break
                    if reviewing:
                        record = (record_review if step == "script_review"
                                  else product_review.record_review)
                        try:
                            record(project_dir, reviewed_hash)
                        except (OSError, ValueError) as exc:
                            _mark_blocked(
                                root,
                                entry.slug,
                                f"{'chấm kịch bản' if step == 'script_review' else 'duyệt sản phẩm'} lỗi: {exc}",
                                report,
                                log_path=result_log_path,
                            )
                            break
                    if step == "revise_product":
                        # Python re-renders the fix at once; an unchanged render goes to the doctor.
                        try:
                            product_review.mark_fix_attempted(project_dir)
                            with _topic_lock(entry.slug):
                                clear_agent_retry(root, entry.slug, step)
                                clear_model_resume(root, entry.slug)
                            with gpu_mutex(root), _production_running(root, entry.slug):
                                deps.python_steps["produce"](project_dir)
                        except Exception as exc:  # noqa: BLE001
                            record_failure(root, project_dir, deps.read_state(project_dir), exc)
                            _mark_blocked(root, entry.slug, f"dựng lại sau sửa lỗi: {exc}", report)
                            break
                        clear_retry(root, entry.slug)
                    if step == "visual_review":
                        # Python validates the report, bounds regeneration and renders the
                        # chosen candidate/fallback before it can enter the physician gate.
                        try:
                            status = retry_status(
                                root, project_dir, deps.read_state(project_dir)
                            )
                        except ValueError as exc:
                            _mark_blocked(root, entry.slug, str(exc), report)
                            break
                        if not status["allowed"]:
                            _mark_blocked(
                                root,
                                entry.slug,
                                f"visual_review lỗi: {status['reason']}",
                                report,
                            )
                            break
                        try:
                            with gpu_mutex(root), _production_running(root, entry.slug):
                                deps.python_steps["produce"](project_dir)
                        except Exception as exc:  # noqa: BLE001
                            if not isinstance(exc, ValueError):
                                with _topic_lock(entry.slug):
                                    clear_agent_retry(root, entry.slug, step)
                                    clear_model_resume(root, entry.slug)
                            record_failure(
                                root, project_dir, deps.read_state(project_dir), exc
                            )
                            _mark_blocked(root, entry.slug, f"visual_review lỗi: {exc}", report)
                            break
                        clear_retry(root, entry.slug)
                elif step in deps.python_steps:
                    try:
                        if step == "produce":
                            with gpu_mutex(root), _production_running(root, entry.slug):
                                deps.python_steps[step](project_dir)
                        else:
                            deps.python_steps[step](project_dir)
                    except Exception as exc:  # noqa: BLE001 — one failing topic is blocked, the queue keeps going
                        if step == "produce":
                            record_failure(
                                root, project_dir, deps.read_state(project_dir), exc
                            )
                        _mark_blocked(
                            root,
                            entry.slug,
                            f"bước {step} lỗi: {type(exc).__name__}: {exc}",
                            report,
                        )
                        break
                    if step == "produce":
                        clear_retry(root, entry.slug)
                else:
                    _mark_blocked(
                        root,
                        entry.slug,
                        f"không tìm thấy bước xử lý cho {step}",
                        report,
                    )
                    break

                steps_taken += 1
                new_state = deps.read_state(project_dir)
                nonstate_problem = _validate_nonstate_agent_step(deps, project_dir, step)
                if step in {"visual_review", "script_review", "product_review", "revise_product"}:
                    _mark_advanced(root, entry.slug, report)
                elif rewriting:
                    unused = _unused_answers(project_dir)
                    if unused:
                        _mark_blocked(root, entry.slug, unused, report, log_path=result_log_path)
                        break
                    if next_script_action(project_dir) == "draft":
                        _mark_blocked(
                            root,
                            entry.slug,
                            "agent không sửa kịch bản theo nhận xét biên tập",
                            report,
                            log_path=result_log_path,
                        )
                        break
                    _mark_advanced(root, entry.slug, report)
                elif step in {"posts", "storyboard_design", "voice_prep", "shorts_plan"}:
                    if nonstate_problem:
                        _mark_blocked(
                            root,
                            entry.slug,
                            nonstate_problem,
                            report,
                            log_path=result_log_path,
                        )
                        break
                    _mark_advanced(root, entry.slug, report)
                elif step == "research" and (
                    state == WorkflowState.DRAFT_READY or new_state == WorkflowState.EVIDENCE_READY
                ):
                    problem = _expert_unfinished(project_dir, deps, state)
                    if problem:
                        _mark_blocked(root, entry.slug, problem, report, log_path=result_log_path)
                        break
                    _mark_advanced(root, entry.slug, report)
                else:
                    if step in AGENT_STEPS and new_state == state:
                        _mark_blocked(
                            root,
                            entry.slug,
                            "agent không làm đổi trạng thái",
                            report,
                            log_path=result_log_path,
                        )
                        break
                    if new_state != state:
                        _mark_advanced(root, entry.slug, report)

                if (pending_change and step in {'draft', 'revise_medical', 'revise_production'}
                        and new_state != WorkflowState.RESEARCH_IN_PROGRESS
                        and (new_state != state or rewriting)):
                    chat.completed(root, entry.slug, project_dir)

                if step in AGENT_STEPS:
                    with _topic_lock(entry.slug):
                        clear_agent_retry(root, entry.slug, step)
                        clear_model_resume(root, entry.slug)

                if once:
                    return True

    return False


@contextmanager
def _production_running(root: Path, slug: str) -> Iterator[None]:
    """Expose actual production work, including work nested after an agent step."""
    path = root / "topics" / "logs" / slug / ".production-running"
    write_text_atomic(path, json.dumps({"pid": os.getpid(),
                                       "process_token": process_token(os.getpid()),
                                       "started_at": datetime.now(UTC).isoformat()}))
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def run_queue(
    root: Path,
    deps: RunDeps,
    *,
    once: bool = False,
    max_steps_per_topic: int = 20,
    max_parallel_topics: int = 1,
) -> RunReport:
    """Isolate project, artifact and tool errors without swallowing interrupts."""
    report = RunReport()
    entries = load_queue(root)

    def _run_entry(entry: QueueEntry) -> bool:
        try:
            return _run_topic(
                root, deps, entry, report, once=once, max_steps_per_topic=max_steps_per_topic
            )
        except Exception as exc:  # noqa: BLE001 — a corrupt topic cannot stop the next one
            log = root / "topics" / "logs" / entry.slug / "runner-error.log"
            reason = _sanitize_reason(exc)
            write_text_atomic(log, f"{datetime.now(UTC).isoformat()} {reason}\n")
            _mark_blocked(root, entry.slug, f"lỗi xử lý chủ đề: {reason}", report, log_path=log)
            return False

    if max_parallel_topics > 1 and not once:
        def dispatch_signature(entry: QueueEntry) -> tuple:
            logs = root / 'topics/logs' / entry.slug
            paths = [root / 'projects' / entry.slug / 'project.yaml']
            paths.extend(logs / name for name in (
                'blocked.txt', 'production-retry.yaml', 'agent-retry.yaml',
                WAITING_MODEL_FILE, 'waiting-model-step.yaml', PAUSED_FILE,
            ))
            contents = []
            for path in paths:
                try:
                    contents.append(path.read_bytes())
                except FileNotFoundError:
                    contents.append(None)
            quota_until = waiting_until(root, entry.slug)
            quota_waiting = quota_until is not None and quota_until > datetime.now(UTC)
            return (entry.model_dump_json(), *contents,
                    tuple(retry_deadlines(root, entry.slug)), quota_waiting)

        def run_and_snapshot(entry: QueueEntry) -> tuple:
            _run_entry(entry)
            return dispatch_signature(entry)

        with ThreadPoolExecutor(max_workers=max_parallel_topics) as pool:
            pending = {}
            completed = {}
            while True:
                active = set(pending.values())
                for entry in entries:
                    if entry.slug in active:
                        continue
                    if completed.get(entry.slug) == dispatch_signature(entry):
                        continue
                    # A fresh retry replaces the previous blocked/gate summary.
                    with _REPORT_LOCK:
                        for items in (report.blocked, report.at_gate, report.waiting_model):
                            if entry.slug in items:
                                items.remove(entry.slug)
                    pending[pool.submit(run_and_snapshot, entry)] = entry.slug
                    active.add(entry.slug)
                if not pending:
                    break
                finished, _ = wait(pending, timeout=1, return_when=FIRST_COMPLETED)
                for future in finished:
                    completed[pending.pop(future)] = future.result()
                entries = load_queue(root)
        return report

    for entry in entries:
        if _run_entry(entry) and once:
            break
    return report
