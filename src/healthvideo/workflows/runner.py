"""Select the next factory workflow step for a project state and run the queue."""

import inspect
import json
import os
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import yaml

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
from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.gate_review import GateApprovalRecord
from healthvideo.domain.hook_outro import CHANNEL_OUTRO_TEXT, OUTRO_TEXT
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.domain.script import Script
from healthvideo.domain.script_style import lint_script_style
from healthvideo.failures import classify_failure, is_file_contention
from healthvideo.process import process_token
from healthvideo.qa.script import review_script
from healthvideo.storage.explainer import read_explainer
from healthvideo.storage.files import (
    AGENT_UTF8_RULE,
    canonical_json_hash,
    read_agent_text,
    read_agent_yaml,
    read_yaml,
    write_text_atomic,
    write_yaml_atomic,
)
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.storage.queue import load_queue
from healthvideo.workflows import (
    change_request,
    chat,
    doctor_questions,
    expert,
    product_review,
    rework,
)
from healthvideo.workflows.factory_standards import style_a_active
from healthvideo.workflows.gate_review import (
    MEDICAL_APPROVAL_ARTIFACT,
    POSTS_ARTIFACT,
    check_revision_posts,
    hash_reviewed_artifacts,
    medical_reviewed_paths,
)
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
    in_rewrite_loop,
    next_script_action,
    previous_review_notes,
    record_review,
    reset_for_doctor_guidance,
    revision_notes,
    script_hash,
)
from healthvideo.workflows.shorts_plan import SHORTS_PLAN_ARTIFACT, ShortsPlan
from healthvideo.workflows.standards import prompt_block
from healthvideo.workflows.storyboard_design import storyboard_validation_error
from healthvideo.workflows.visual_review import prepare_stale_review, review_pending
from healthvideo.workflows.voice_prep import (
    VOICE_PREP_ARTIFACT,
    VoicePrepSheet,
    try_auto_voice_prep,
)
from healthvideo.workflows.voice_prep import (
    voice_prep_ready as default_voice_prep_ready,
)

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

_GUIDANCE_STEPS_BY_STATE: dict[WorkflowState, frozenset[str]] = {
    WorkflowState.TOPIC_SELECTED: frozenset({"research"}),
    WorkflowState.RESEARCH_IN_PROGRESS: frozenset({"research"}),
    WorkflowState.EVIDENCE_READY: frozenset({"draft", "research"}),
    WorkflowState.DRAFT_READY: frozenset({"draft", "storyboard_design", "voice_prep", "research"}),
    WorkflowState.NEEDS_MEDICAL_REVISION: frozenset({"revise_medical", "research"}),
    WorkflowState.MEDICALLY_APPROVED: frozenset({"shorts_plan", "posts", "visual_review"}),
    WorkflowState.PRODUCTION_IN_PROGRESS: frozenset({"shorts_plan", "posts", "visual_review"}),
    WorkflowState.NEEDS_PRODUCTION_REVISION: frozenset({"revise_production", "shorts_plan"}),
}


def _leader_guidance_path(root: Path, slug: str) -> Path:
    return root / "topics" / "logs" / slug / "leader-guidance.yaml"


def _active_leader_guidance(root: Path, project_dir: Path) -> dict[str, Any] | None:
    path = _leader_guidance_path(root, project_dir.name)
    if not path.is_file():
        return None
    try:
        data = read_yaml(path)
        if not isinstance(data, dict):
            return None
        active_revision = resolve_project_layout(project_dir).manifest.active_revision
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        return None
    if data.get("revision") != active_revision:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    return data


def _change_touches_script(project_dir: Path, note: str) -> bool:
    """Return False only when the change request targets non-script IDs exclusively."""
    plan_file: Path | None = None
    prior_bytes: bytes | None = None
    try:
        if (project_dir / "project.yaml").is_file():
            plan_file = resolve_project_layout(project_dir).artifact_root / rework.PLAN
            if plan_file.is_file():
                prior_bytes = plan_file.read_bytes()
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        plan_file = None
    try:
        plan = rework.prepare(project_dir, note)
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return True
    finally:
        if plan_file is not None:
            try:
                if prior_bytes is None:
                    plan_file.unlink(missing_ok=True)
                elif not plan_file.is_file() or plan_file.read_bytes() != prior_bytes:
                    plan_file.write_bytes(prior_bytes)
            except OSError:
                pass
    scope = plan.get("scope") if isinstance(plan, Mapping) else None
    if not isinstance(scope, Mapping):
        return True
    return not (any(scope.values()) and not scope.get("script/script.yaml"))


def _has_open_questions(project_dir: Path) -> bool:
    if not (project_dir / "project.yaml").is_file():
        return False
    try:
        return bool(expert.open_questions(project_dir))
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return False


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
    AGENT_UTF8_RULE,
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
_GPU_LOCK_STATE = threading.local()
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
    lock_file = (root / "cache" / "gpu-mutex.lock").resolve()
    depths: dict[str, int] | None = getattr(_GPU_LOCK_STATE, "depths", None)
    if depths is None:
        depths = {}
        _GPU_LOCK_STATE.depths = depths
    lock_key = str(lock_file)
    depth = depths.get(lock_key, 0)
    if depth > 0:
        depths[lock_key] = depth + 1
        try:
            yield
        finally:
            depths[lock_key] = depth
        return
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
            depths[lock_key] = 1
            try:
                yield
            finally:
                depths.pop(lock_key, None)
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            depths[lock_key] = 1
            try:
                yield
            finally:
                depths.pop(lock_key, None)
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
    try:
        lines = act_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ()
    overall_latest: dict[str, ModelSlot] = {}
    since_last_critic: dict[str, ModelSlot] = {}
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("slug") != slug or row.get("ok") is not True:
            continue
        role = row.get("role")
        if role == critic_role:
            since_last_critic.clear()
            continue
        if role in maker_roles and row.get("cli") and row.get("model"):
            try:
                slot = ModelSlot(cli=str(row["cli"]), model=str(row["model"]))
            except ValueError:
                continue
            overall_latest[str(role)] = slot
            since_last_critic[str(role)] = slot
    latest_by_role = since_last_critic or overall_latest
    if not latest_by_role:
        return ()
    excluded = tuple(dict.fromkeys(latest_by_role.values()))
    active_company = company or load_company()
    critic_chain = list(active_company.chain(critic_role))
    excluded_identities = {slot.model_identity for slot in excluded}
    if not [slot for slot in critic_chain if slot.model_identity not in excluded_identities]:
        primary_role = maker_order[0]
        primary_slot = latest_by_role.get(primary_role)
        if primary_slot is not None and any(
            slot.model_identity != primary_slot.model_identity for slot in critic_chain
        ):
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
    # Topics paused waiting for a doctor question outside formal approval gates.
    waiting_doctor: list[str] = field(default_factory=list)


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
    if state in {WorkflowState.EVIDENCE_READY, WorkflowState.NEEDS_MEDICAL_REVISION} and (
        project_dir / "project.yaml"
    ).is_file():
        try:
            if expert.open_questions(project_dir):
                return f"chuyên gia chưa trả lời hết câu hỏi trong {expert.QUESTIONS}"
        except (OSError, TypeError, ValueError) as exc:
            return f"câu hỏi của biên kịch lỗi: {exc}"
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
    if step == 'revise_medical' and (project_dir / 'project.yaml').is_file():
        from healthvideo.workflows import rework

        prompt_fields['reject_note'] = rework.context(project_dir, prompt_fields['reject_note'])
    if step == 'storyboard_design' and (project_dir / 'project.yaml').is_file():
        from healthvideo.workflows import rework

        prompt_fields['reject_note'] += '\n' + rework.storyboard_context(project_dir)
    if rewriting:
        if not answering:
            from healthvideo.workflows.script_review import ensure_repair_baseline

            ensure_repair_baseline(project_dir)
        notes = expert.answer_notes(project_dir) if answering else revision_notes(project_dir)
        prompt_fields["reject_note"] = f"{notes}\n{prompt_fields.get('reject_note', '')}".strip()
    if step == 'script_review':
        prompt_fields['reject_note'] += '\n' + previous_review_notes(project_dir)
    if step in {"draft", "storyboard_design", "revise_product", "revise_production"}:
        blocked = root / 'topics/logs' / entry.slug / 'blocked.txt'
        if blocked.is_file():
            diagnostic = _sanitize_reason(RuntimeError(blocked.read_text(encoding='utf-8', errors='replace')))
            prompt_fields['reject_note'] = (prompt_fields.get('reject_note', '')
                                           + '\nLỗi kiểm tra cần sửa trong phạm vi bước này: '
                                           + diagnostic[-6000:])
    prompt = render_prompt(step, company=deps.company, **prompt_fields)
    from healthvideo.workflows import script_review

    protocol = script_review if step in {'script_review', 'draft'} else product_review
    incremental = (protocol.incremental_context(project_dir, writer=step in {'draft', 'revise_product'})
                   if (project_dir / 'project.yaml').is_file()
                   and (step in {'script_review', 'product_review', 'revise_product'}
                        or (step == 'draft' and rewriting and not answering)) else '')
    if incremental:
        reviewing = step in {'script_review', 'product_review'}
        schema = (script_review.ScriptReviewReport if step == 'script_review'
                  else product_review.ProductReviewReport)
        if reviewing:
            output = (
                f'Chỉ ghi {_artifact_report_path(project_dir, step)} bằng Python với encoding="utf-8". '
                f'Schema báo cáo:\n'
                + json.dumps(schema.model_json_schema(), ensure_ascii=False)
            )
            prompt = (f'Project: {project_dir}\nBước: (`{step}`)\n'
                      f'Ghi chú bác sĩ: {entry.doctor_note or ""}\n'
                      f'Yêu cầu bác sĩ: {deps.reject_note(project_dir) or ""}\n'
                      'Đây là vòng sửa/duyệt từng phần. Gói bên dưới là đầu vào chính; '
                      'không đọc lại toàn bộ bài để chấm lại từ đầu. Ngữ cảnh diff chỉ để đọc. '
                      'Chỉ kiểm issue mở và ảnh hưởng ngữ cảnh quanh chỗ sửa; xem tổng thể ngắn. '
                      'Không nêu lỗi mới ở phần không đổi trừ an toàn y khoa nghiêm trọng '
                      '(blocking_safety: true, ghi lý do cụ thể). Giữ issue_id và vị trí. '
                      'Trả issue_statuses bắt buộc là từ điển issue_id -> status '
                      '(resolved/still_open), không phải danh sách. Ví dụ YAML: '
                      'issue_statuses: {PR3-01: still_open, PR3-02: resolved}. overall ngắn. '
                      'Giữ điểm tiêu chí không có issue và các decisions chưa có chỉ dẫn xử lý. '
                      'Bắt buộc ghi YAML bằng Python encoding="utf-8" (không làm mất dấu tiếng Việt thành "?").\n'
                      + incremental + '\n' + output
                      + '\n## Quy tắc cứng\n' + '\n'.join(f'- {rule}' for rule in HARD_RULES))
        elif step == 'revise_product':
            output = (
                'Chỉ sửa phẫu thuật đúng phạm vi issue mở (fixable: true). '
                'Khóa cứng tuyệt đối `script/script.yaml`, `evidence/*`, `explainer/*`, '
                '`assets/license-ledger.yaml`, `script/outline.yaml` và các trường y khoa '
                '(`id`, `script_line_id`, `narration`, `claim_id`, `chapter_id`, `source_marker`, '
                '`source_card`, `evidence_highlight`) trong storyboard; không sửa cảnh ngoài danh sách. '
                'Ghi mọi file YAML bằng Python với encoding="utf-8". '
                'Không tự dựng video hay đổi trạng thái project; Python dựng lại ngay sau bước này.'
            )
            prompt = (f'Project: {project_dir}\nBước: (`{step}`)\n'
                      f'Ghi chú bác sĩ: {entry.doctor_note or ""}\n'
                      f'Yêu cầu bác sĩ: {deps.reject_note(project_dir) or ""}\n'
                      'Đây là vòng sửa phẫu thuật tại Trạm 12. Kỷ luật thợ dựng (`mục 5` Spec Style A): '
                      'không tự thêm hiệu ứng ngoài bộ động tác nhận diện để "cho sinh động".\n'
                      + incremental + '\n' + output
                      + '\n## Quy tắc cứng\n' + '\n'.join(f'- {rule}' for rule in HARD_RULES))
        else:
            output = (
                'Chỉ sửa các dòng/phạm vi issue mở. Giữ nguyên từng byte ngoài phạm vi; '
                'không tự sửa dòng kề. Giữ id, thứ tự và metadata. '
                'Ghi file YAML bằng Python với encoding="utf-8". '
                'Dùng lệnh nộp của bước hiện hành sau khi sửa; không tự duyệt cổng.'
            )
            prompt = (f'Project: {project_dir}\nBước: (`{step}`)\n'
                      f'Ghi chú bác sĩ: {entry.doctor_note or ""}\n'
                      f'Yêu cầu bác sĩ: {deps.reject_note(project_dir) or ""}\n'
                      'Đây là vòng sửa/duyệt từng phần. Gói bên dưới là đầu vào chính; '
                      'không đọc lại toàn bộ bài để chấm lại từ đầu. Ngữ cảnh diff chỉ để đọc.\n'
                      + incremental + '\n' + output
                      + '\n## Quy tắc cứng\n' + '\n'.join(f'- {rule}' for rule in HARD_RULES))
        if step == 'product_review':
            prompt += (f'\nLấy bằng chứng hình hiện hành: healthvideo step review-frames {project_dir} --every 4. '
                       'Chờ lệnh xong, mở contact sheet của các cảnh có issue và cảnh kề; '
                       'xem tổng thể ngắn. Không nhận đã nghe âm thanh. '
                       'Đối chiếu QA/phát âm hiện hành khi issue liên quan âm thanh.')
    style_note = ""
    if step in {"product_review", "revise_product"} and (project_dir / "project.yaml").is_file():
        revision_dir = resolve_project_layout(project_dir).artifact_root
        if style_a_active(revision_dir):
            style_note = (
                "## Chuẩn phong cách áp dụng (Trạm 12)\n"
                "- Revision này đã ghim Chuẩn phong cách PYH — Hướng A trong `workflow/standards.yaml`: "
                "bắt buộc chấm đủ 7 tiêu chí (gồm `dung_phong_cach_pyh >= 7`) để qua Trạm 12."
            )
        else:
            style_note = (
                "## Chuẩn phong cách áp dụng (Trạm 12)\n"
                "- Revision này được tạo TRƯỚC Chuẩn phong cách A (`workflow/standards.yaml` chưa ghim Chuẩn A): "
                "`dung_phong_cach_pyh` chỉ mang tính tham khảo/tùy chọn và KHÔNG chặn cổng Trạm 12 "
                "nếu 6 tiêu chí gốc (`hinh_khop_loi`, `hinh_ro`, `nhip_dung`, `am_thanh_phu_de`, `mo_ket`, `bai_dang`) "
                "đều đạt >= 7. Không yêu cầu dựng lại video cũ theo mascot Style A hay zoom kính lúp."
            )
    standards_block = prompt_block(root, slug=entry.slug)
    stale_visual_note = (
        prepare_stale_review(resolve_project_layout(project_dir).artifact_root)
        if step == 'visual_review' and (project_dir / 'project.yaml').is_file() else ''
    )
    shorts_plan_note = ''
    if step == 'shorts_plan':
        problem = _shorts_plan_validation_problem(project_dir)
        if problem:
            shorts_plan_note = f'Lỗi kế hoạch short cần sửa trong phạm vi bước này: {problem}'
    guidance = _active_leader_guidance(root, project_dir)
    guidance_note = (
        "## Hướng dẫn xử lý lỗi từ Điều phối viên trưởng\n" + str(guidance["brief"]).strip()
        if guidance and str(guidance.get("brief") or "").strip()
        else ""
    )
    extra_blocks = "\n\n".join(
        part
        for part in (style_note, standards_block.rstrip(), stale_visual_note, shorts_plan_note, guidance_note)
        if part
    )
    if extra_blocks:
        body, heading, rules = prompt.rpartition("## Quy tắc cứng")
        if heading:
            prompt = f"{body.rstrip()}\n\n{extra_blocks}\n\n{heading}{rules}"
        else:
            prompt = f"{prompt.rstrip()}\n\n{extra_blocks}\n"
    return prompt


def _artifact_report_path(project_dir: Path, step: str) -> Path:
    return resolve_project_layout(project_dir).artifact_root / f"reviews/{step.replace('_', '-')}.yaml"


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
    defer_validation_record: bool = False,
    mark_blocked_on_failure: bool = True,
) -> tuple[str, Path | None, str | None, dict[str, str] | None]:
    """Run one agent step with fingerprint retry gating, failover & quarantine."""
    prompt = _build_step_prompt(
        root, deps, entry, project_dir, step, rewriting=rewriting, answering=answering
    )
    fingerprint = agent_fingerprint(root, project_dir, step, brief_context)
    with _topic_lock(entry.slug):
        status = agent_retry_status(root, project_dir, step, fingerprint)
        if not status["allowed"]:
            waiting = (
                f"đang chờ thử lại lúc {status['retry_after']}"
                if status["retry_after"]
                else "cần sửa đầu vào hoặc cấu hình"
            )
            blocked_reason = f"bước {step}: {waiting}; {status['reason']}"
            if mark_blocked_on_failure:
                _mark_blocked(root, entry.slug, blocked_reason, report)
            return "blocked", None, None, {"error": blocked_reason}
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
    checkpoint: dict[Path, bytes] = {}
    restore_repair: Callable[[], None] | None = None
    try:
        from healthvideo.workflows import script_review

        scoped_storyboard = (step == 'storyboard_design' and (project_dir / 'project.yaml').is_file()
                             and (resolve_project_layout(project_dir).artifact_root
                                  / 'reviews/storyboard-rework.yaml').is_file())
        scoped_script = step == 'draft' and rewriting and not answering
        scoped_product = step == 'revise_product' and (project_dir / 'project.yaml').is_file()
        scoped_medical = step == 'revise_medical' and (project_dir / 'project.yaml').is_file()
        repair_root = (resolve_project_layout(project_dir).artifact_root
                       if scoped_script or scoped_product or scoped_medical or scoped_storyboard else project_dir)
        # Keep a full textual checkpoint so an invalid agent save/state transition is reversible.
        checkpoint = ({p: p.read_bytes() for p in repair_root.rglob('*.yaml')}
                      | {project_dir / 'project.yaml': (project_dir / 'project.yaml').read_bytes()}
                      if scoped_script or scoped_product or scoped_medical or scoped_storyboard else {})
        storyboard_before = (read_yaml(repair_root / 'reviews/storyboard-rework.yaml')
                             if scoped_storyboard else None)
        product_before = product_review.repair_files(project_dir) if scoped_product else {}
        protected_dirs = (('script', 'storyboard', 'assets', 'evidence', 'explainer', 'posts', 'reviews')
                          if scoped_script or scoped_product or scoped_medical or scoped_storyboard else ())
        protected_before = {p for name in protected_dirs for p in (repair_root / name).rglob('*.yaml')}
        # Voice preparation owns this sibling artifact and may save it concurrently.
        sibling_files = {repair_root / 'script/voice-prep.yaml'} if scoped_storyboard else set()
        protected_before -= sibling_files
        for sibling in sibling_files:
            checkpoint.pop(sibling, None)

        def restore_repair() -> None:
            current_paths = {p for name in protected_dirs for p in (repair_root / name).rglob('*.yaml')}
            for path in current_paths - protected_before - sibling_files:
                path.unlink(missing_ok=True)
            for path, raw in checkpoint.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            if scoped_product:
                repo = project_dir.parent.parent
                for relative in product_review.repair_files(project_dir).keys() - product_before.keys():
                    (repo / relative).unlink(missing_ok=True)
                for relative, raw in product_before.items():
                    (repo / relative).parent.mkdir(parents=True, exist_ok=True)
                    (repo / relative).write_bytes(raw)
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
        for correction in range(2):
            if not (scoped_script or scoped_product or scoped_medical or scoped_storyboard):
                if result.ok:
                    _validate_agent_step_files(project_dir, step)
                break
            try:
                if result.ok:
                    _validate_agent_step_files(project_dir, step)
                protected_after = {p for name in protected_dirs
                                   for p in (repair_root / name).rglob('*.yaml')} - sibling_files
                extra_allowed = ({repair_root / 'script/questions.yaml'} if scoped_medical
                                 and deps.read_state(project_dir) == WorkflowState.RESEARCH_IN_PROGRESS
                                 else set())
                if scoped_storyboard:
                    extra_allowed.add(repair_root / 'reviews/storyboard-rework.yaml')
                if (protected_after - extra_allowed) != (protected_before - extra_allowed):
                    raise ValueError('Repair scope violation: file creation/deletion')
                for original, raw in checkpoint.items():
                    if (original.is_relative_to(repair_root / 'reviews') and original not in extra_allowed
                            and original.read_bytes() != raw):
                        raise ValueError(f'Repair scope violation: review record is read-only: {original}')
                if scoped_script:
                    path = script_review.script_path(project_dir)
                    script_review.check_rewrite(project_dir, checkpoint[path], path.read_bytes())
                    for original, raw in checkpoint.items():
                        if original != path and original.is_relative_to(repair_root) and (
                            original.parts[len(repair_root.parts)] in
                            {'script', 'storyboard', 'assets', 'evidence', 'explainer'}
                        ) and original.read_bytes() != raw:
                            raise ValueError(f'Repair scope violation: {original}')
                elif scoped_product:
                    product_review.check_repair(project_dir, product_before)
                    product_review.finalize_product_repair(project_dir, product_before)
                elif scoped_storyboard:
                    from healthvideo.workflows import rework

                    rework.check_storyboard(project_dir,
                                           {name: repair_root / name for name in storyboard_before['snapshot']},
                                           plan=storyboard_before)
                    for original, raw in checkpoint.items():
                        if original.is_relative_to(repair_root) and (
                            original.parts[len(repair_root.parts)] in {'script', 'evidence', 'explainer'}
                        ) and (original.relative_to(repair_root).as_posix() not in storyboard_before['snapshot']
                               and original.read_bytes() != raw):
                            raise ValueError(f'Repair scope violation: {original}')
                else:
                    from healthvideo.workflows import rework

                    rework.check(project_dir)
                    for original, raw in checkpoint.items():
                        if original.is_relative_to(repair_root) and (
                            original.parts[len(repair_root.parts)] in {'evidence', 'explainer'}
                        ) and original.read_bytes() != raw:
                            raise ValueError(f'Repair scope violation: {original}')
                break
            except (ValueError, OSError) as scope_error:
                restore_repair()
                write_text_atomic(log_dir / 'repair-scope-rejection.txt', str(scope_error))
                if correction or not result.ok:
                    raise
                result = deps.invoke(
                    deps.company.chain(role.id),
                    prompt + '\nĐầu ra bị trả lại: ' + str(scope_error)
                    + '\nĐã khôi phục checkpoint. Sửa lại đúng phạm vi một lần duy nhất.',
                    cwd=root, log_dir=log_dir, role=role.id, slug=entry.slug, step=step,
                    **invoke_kwargs,
                )
    except AllAgentsExhausted as exc:
        if checkpoint and restore_repair is not None:
            restore_repair()
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
        if checkpoint and restore_repair is not None:
            restore_repair()
        if is_project_paused(root, entry.slug):
            return "paused", None, None, None
        kind = classify_failure(exc)
        observed_fp = agent_fingerprint(root, project_dir, step, brief_context)
        with _topic_lock(entry.slug):
            record_agent_failure(
                root,
                project_dir,
                step,
                fingerprint,
                kind,
                exc,
                observed_fingerprint=observed_fp,
            )
        _record_code_changes(root, entry.slug, deps, report, before)
        blocked_reason = f"bước {step} lỗi: {_sanitize_reason(exc)}"
        if mark_blocked_on_failure:
            _mark_blocked(root, entry.slug, blocked_reason, report)
        return "blocked", None, None, {"error": blocked_reason}

    if not result.ok:
        if is_project_paused(root, entry.slug):
            return "paused", result.log_path, None, None
        failure = RuntimeError(
            f"agent {result.agent} thất bại ở bước {step}; log_path: {result.log_path}"
        )
        try:
            detail = result.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            detail = ""
        if is_file_contention(detail):
            # Log filenames change on every invocation. Persist the actual lock
            # diagnostic so identical consecutive failures share the same count.
            failure = RuntimeError(f"agent {result.agent} thất bại ở bước {step}: {detail}")
        observed_fp = agent_fingerprint(root, project_dir, step, brief_context)
        with _topic_lock(entry.slug):
            record_agent_failure(
                root,
                project_dir,
                step,
                fingerprint,
                getattr(result, "failure_kind", None),
                failure,
                observed_fingerprint=observed_fp,
            )
        _record_code_changes(root, entry.slug, deps, report, before)
        blocked_reason = f"agent {result.agent} thất bại ở bước {step}"
        if mark_blocked_on_failure:
            _mark_blocked(
                root,
                entry.slug,
                blocked_reason,
                report,
                log_path=result.log_path,
            )
        return "blocked", result.log_path, None, {"error": blocked_reason}

    if not defer_validation_record:
        observed_fp = agent_fingerprint(root, project_dir, step, brief_context)
        with _topic_lock(entry.slug):
            record_agent_failure(
                root,
                project_dir,
                step,
                fingerprint,
                "validation",
                ValueError(f"bước {step}: đầu ra hoặc trạng thái chưa hợp lệ"),
                observed_fingerprint=observed_fp,
            )
    _record_code_changes(root, entry.slug, deps, report, before)
    return "ok", result.log_path, reviewed_hash, {"fingerprint": fingerprint}


def _record_agent_validation_failure(
    root: Path,
    slug: str,
    project_dir: Path,
    step: str,
    brief_context: str,
    pre_fingerprint: str | None,
    reason: str,
) -> None:
    """Record a concrete post-step validation error in agent-retry.yaml once."""
    observed = agent_fingerprint(root, project_dir, step, brief_context)
    fingerprint = pre_fingerprint or observed
    with _topic_lock(slug):
        record_agent_failure(
            root,
            project_dir,
            step,
            fingerprint,
            "validation",
            ValueError(reason),
            observed_fingerprint=observed,
        )


def _revision_root_or_error(project_dir: Path) -> tuple[Path | None, str | None]:
    project_yaml = project_dir / "project.yaml"
    if not project_yaml.is_file():
        return None, "thiếu project.yaml"
    try:
        return resolve_project_layout(project_dir).artifact_root, None
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        return None, f"project.yaml chưa hợp lệ: {_sanitize_reason(exc)}"


def _posts_validation_problem(project_dir: Path) -> str | None:
    revision_root, root_err = _revision_root_or_error(project_dir)
    if revision_root is None:
        return f"{POSTS_ARTIFACT} chưa hợp lệ ({root_err})"
    if not (revision_root / POSTS_ARTIFACT).is_file():
        return f"thiếu {POSTS_ARTIFACT}"
    try:
        issues = check_revision_posts(revision_root)
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        return f"{POSTS_ARTIFACT} chưa hợp lệ: {_sanitize_reason(exc)}"
    if issues:
        return f"{POSTS_ARTIFACT} chưa hợp lệ: {'; '.join(issues[:4])}"
    return None


def _diagnose_posts_error(project_dir: Path) -> str:
    return _posts_validation_problem(project_dir) or f"{POSTS_ARTIFACT} chưa hợp lệ"


def _voice_prep_validation_problem(project_dir: Path) -> str | None:
    revision_root, root_err = _revision_root_or_error(project_dir)
    if revision_root is None:
        return f"{VOICE_PREP_ARTIFACT} chưa hợp lệ ({root_err})"
    vp_path = revision_root / VOICE_PREP_ARTIFACT
    if not vp_path.is_file():
        return f"thiếu {VOICE_PREP_ARTIFACT}"
    script_path = revision_root / "script" / "script.yaml"
    if not script_path.is_file():
        return f"thiếu script/script.yaml để đối chiếu {VOICE_PREP_ARTIFACT}"
    try:
        sheet = VoicePrepSheet.model_validate(read_agent_yaml(vp_path))
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        return f"{VOICE_PREP_ARTIFACT} chưa hợp lệ: {_sanitize_reason(exc)}"
    try:
        script_data = read_yaml(script_path)
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        return f"script/script.yaml chưa hợp lệ: {_sanitize_reason(exc)}"
    expected_hash = canonical_json_hash(script_data)
    if sheet.script_hash != expected_hash:
        return (
            f"voice-prep.yaml script_hash lệch "
            f"(trong {VOICE_PREP_ARTIFACT}: {sheet.script_hash[:12]}, script hiện tại: {expected_hash[:12]})"
        )
    return None


def _diagnose_voice_prep_error(project_dir: Path) -> str:
    return _voice_prep_validation_problem(project_dir) or f"{VOICE_PREP_ARTIFACT} chưa hợp lệ"


def _shorts_plan_validation_problem(project_dir: Path) -> str | None:
    revision_root, root_err = _revision_root_or_error(project_dir)
    if revision_root is None:
        return f"{SHORTS_PLAN_ARTIFACT} chưa hợp lệ ({root_err})"
    plan_path = revision_root / SHORTS_PLAN_ARTIFACT
    if not plan_path.is_file():
        return f"thiếu {SHORTS_PLAN_ARTIFACT}"
    try:
        plan = ShortsPlan.model_validate(read_agent_yaml(plan_path))
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        return f"{SHORTS_PLAN_ARTIFACT} chưa hợp lệ: {_sanitize_reason(exc)}"
    script_path = revision_root / "script" / "script.yaml"
    board_path = revision_root / "storyboard" / "storyboard.yaml"
    if not script_path.is_file():
        return f"thiếu script/script.yaml để đối chiếu {SHORTS_PLAN_ARTIFACT}"
    if not board_path.is_file():
        return f"thiếu storyboard/storyboard.yaml để đối chiếu {SHORTS_PLAN_ARTIFACT}"
    try:
        expected_hash = canonical_json_hash(
            {"script": read_yaml(script_path), "storyboard": read_yaml(board_path)}
        )
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        return f"không đọc được script/storyboard để đối chiếu {SHORTS_PLAN_ARTIFACT}: {_sanitize_reason(exc)}"
    if plan.revision_hash != expected_hash:
        return (
            f"{SHORTS_PLAN_ARTIFACT} revision_hash lệch "
            f"(trong file: {plan.revision_hash[:12]}, hiện tại: {expected_hash[:12]})"
        )
    try:
        from healthvideo.workflows.shorts_plan import sync_shorts_plan_to_clip_plan

        sync_shorts_plan_to_clip_plan(revision_root)
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        return f"{SHORTS_PLAN_ARTIFACT} chưa hợp lệ: {_sanitize_reason(exc)}"
    return None


def _diagnose_shorts_plan_error(project_dir: Path) -> str:
    return _shorts_plan_validation_problem(project_dir) or f"{SHORTS_PLAN_ARTIFACT} chưa hợp lệ"


def _existing_invalid_shorts_plan(deps: RunDeps, project_dir: Path) -> bool:
    """Missing plans keep the original visual-first order for new projects."""
    revision_root, _ = _revision_root_or_error(project_dir)
    return (revision_root is not None
            and (revision_root / SHORTS_PLAN_ARTIFACT).is_file()
            and not deps.shorts_plan_ready(project_dir))


def _diagnose_script_error(revision_root: Path) -> str | None:
    script_path = revision_root / "script" / "script.yaml"
    if not script_path.is_file():
        return "thiếu script/script.yaml"
    try:
        script = Script.model_validate(read_agent_yaml(script_path))
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        return f"script/script.yaml chưa hợp lệ: {_sanitize_reason(exc)}"
    if not script.lines:
        return "script/script.yaml chưa có dòng lời thoại nào"
    if script.format_profile == "hook_outro_v1":
        outro = script.lines[-1]
        if outro.purpose != "outro" or outro.text not in {CHANNEL_OUTRO_TEXT, OUTRO_TEXT}:
            return "M6.4 final outro must match pinned text (outro cuối trong script/script.yaml chưa khớp mẫu pin)"
    claims: list[EvidenceClaim] = []
    ledger_path = revision_root / "evidence" / "ledger.yaml"
    if ledger_path.is_file():
        try:
            ledger_raw = read_yaml(ledger_path)
            claims = [
                EvidenceClaim.model_validate(item)
                for item in (ledger_raw.get("claims") or [])
            ]
        except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
            return f"evidence/ledger.yaml chưa hợp lệ: {_sanitize_reason(exc)}"
    explainer = None
    explainer_path = revision_root / "explainer" / "explainer.yaml"
    if explainer_path.is_file():
        try:
            explainer = read_explainer(revision_root)
        except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
            return f"explainer/explainer.yaml chưa hợp lệ: {_sanitize_reason(exc)}"
    elif script.format_profile == "explain_first_v1":
        return "thiếu explainer/explainer.yaml (bắt buộc cho explain_first_v1)"
    if claims or explainer is not None or script.format_profile == "explain_first_v1":
        qa_issues = [
            f"{iss.line_id or 'script'}:{iss.code}({iss.message})"
            for iss in review_script(script, claims, [], explainer=explainer)
            if iss.severity == "error"
        ]
        if qa_issues:
            return f"script/script.yaml lỗi QA: {'; '.join(qa_issues[:4])}"
    style_blocks = [
        f"{iss.line_id}:{iss.rule}({iss.excerpt})"
        for iss in lint_script_style(script)
        if iss.severity == "block"
    ]
    if style_blocks:
        return f"script/script.yaml vi phạm văn phong: {'; '.join(style_blocks[:4])}"
    return None


def _diagnose_unchanged_state(
    deps: RunDeps, project_dir: Path, step: str, state: WorkflowState
) -> str:
    prefix = f"agent không làm đổi trạng thái ({step}, trạng thái {state.value})"
    revision_root, root_err = _revision_root_or_error(project_dir)
    if revision_root is None:
        return f"{prefix}: {root_err}"

    if step == "research":
        expert_err = _expert_unfinished(project_dir, deps, state)
        if expert_err:
            return f"{prefix}: {expert_err}"
        if state == WorkflowState.TOPIC_SELECTED and not (revision_root / "evidence" / "question.yaml").is_file():
            return f"{prefix}: thiếu evidence/question.yaml (agent chưa tạo câu hỏi nghiên cứu PICO)"
        ledger_path = revision_root / "evidence" / "ledger.yaml"
        if not ledger_path.is_file():
            return f"{prefix}: thiếu evidence/ledger.yaml (agent chưa hoàn tất tổng hợp chứng cứ)"
        try:
            ledger_raw = read_yaml(ledger_path)
            if not isinstance(ledger_raw, Mapping):
                return f"{prefix}: evidence/ledger.yaml phải là mapping YAML"
            for rec in ledger_raw.get("records") or []:
                SourceRecord.model_validate(rec)
            for cl in ledger_raw.get("claims") or []:
                EvidenceClaim.model_validate(cl)
        except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
            return f"{prefix}: evidence/ledger.yaml chưa hợp lệ: {_sanitize_reason(exc)}"
        explainer_path = revision_root / "explainer" / "explainer.yaml"
        if not explainer_path.is_file():
            return f"{prefix}: thiếu explainer/explainer.yaml"
        try:
            read_explainer(revision_root)
        except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
            return f"{prefix}: explainer/explainer.yaml chưa hợp lệ: {_sanitize_reason(exc)}"
        return f"{prefix}: tệp chứng cứ đã có nhưng agent chưa gọi lệnh chuyển sang evidence_ready"

    if step in {"draft", "revise_medical"}:
        script_err = _diagnose_script_error(revision_root)
        if script_err:
            return f"{prefix}: {script_err}"
        if (revision_root / "storyboard" / "storyboard.yaml").is_file():
            sb_err = storyboard_validation_error(project_dir)
            if sb_err:
                return f"{prefix}: {sb_err}"
        if step == "revise_medical" and (revision_root / VOICE_PREP_ARTIFACT).is_file():
            vp_err = _voice_prep_validation_problem(project_dir)
            if vp_err:
                return f"{prefix}: {vp_err}"
        return f"{prefix}: agent chưa gọi lệnh nộp để chuyển trạng thái từ {state.value}"

    if step == "revise_production":
        approval_path = revision_root / MEDICAL_APPROVAL_ARTIFACT
        if approval_path.is_file():
            try:
                record = GateApprovalRecord.model_validate(read_yaml(approval_path))
                reviewed_paths = medical_reviewed_paths(revision_root)
                current_hashes = hash_reviewed_artifacts(reviewed_paths)
                drifted = [
                    rel
                    for rel in reviewed_paths
                    if record.artifact_hashes.get(rel) != current_hashes.get(rel)
                ]
                if drifted:
                    return (
                        f"{prefix}: tệp khóa cổng y khoa đã lệch hash so với {MEDICAL_APPROVAL_ARTIFACT}: "
                        + ", ".join(drifted[:5])
                    )
            except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
                return f"{prefix}: {MEDICAL_APPROVAL_ARTIFACT} chưa hợp lệ: {_sanitize_reason(exc)}"
        if (revision_root / "storyboard" / "storyboard.yaml").is_file() and not deps.storyboard_ready(project_dir):
            sb_err = storyboard_validation_error(project_dir) or "storyboard.yaml chưa hợp lệ"
            return f"{prefix}: {sb_err}"
        if (revision_root / POSTS_ARTIFACT).is_file() and not deps.posts_ready(project_dir):
            return f"{prefix}: {_diagnose_posts_error(project_dir)}"
        if (revision_root / VOICE_PREP_ARTIFACT).is_file() and not deps.voice_prep_ready(project_dir):
            return f"{prefix}: {_diagnose_voice_prep_error(project_dir)}"
        if (revision_root / SHORTS_PLAN_ARTIFACT).is_file() and not deps.shorts_plan_ready(project_dir):
            return f"{prefix}: {_diagnose_shorts_plan_error(project_dir)}"
        return (
            f"{prefix}: agent không thay đổi trạng thái {state.value} "
            "(chưa gọi lệnh nộp sau sửa dựng hoặc yêu cầu chạm tệp khóa cổng y khoa)"
        )

    return f"{prefix}: agent hoàn tất nhưng chưa chuyển trạng thái"


def _validate_nonstate_agent_step(
    deps: RunDeps, project_dir: Path, step: str
) -> str | None:
    if step == "posts" and not deps.posts_ready(project_dir):
        return f"agent không làm đổi trạng thái (posts): {_diagnose_posts_error(project_dir)}"
    if step == "storyboard_design" and not deps.storyboard_ready(project_dir):
        detail = storyboard_validation_error(project_dir) or "storyboard.yaml chưa hợp lệ"
        return f"agent không làm đổi trạng thái (storyboard_design): {detail}"
    if step == "voice_prep" and not deps.voice_prep_ready(project_dir):
        return f"agent không làm đổi trạng thái (voice_prep): {_diagnose_voice_prep_error(project_dir)}"
    if step == "shorts_plan" and not deps.shorts_plan_ready(project_dir):
        return f"agent không làm đổi trạng thái (shorts_plan): {_diagnose_shorts_plan_error(project_dir)}"
    return None


def _validate_agent_step_files(project_dir: Path, step: str) -> None:
    """Catch direct writes too; never inspect historical review archives/snapshots."""
    revision, _ = _revision_root_or_error(project_dir)
    if revision is None:
        return  # Existing schema/state validation reports missing or invalid projects.
    script = ('script/script.yaml', 'script/outline.yaml', 'script/questions.yaml')
    visuals = ('storyboard/storyboard.yaml', 'assets/asset-manifest.yaml', 'script/clip-plan.yaml')
    outputs = {
        'research': ('evidence/question.yaml', 'evidence/claims.yaml', 'evidence/records.yaml',
                     'evidence/ledger.yaml', expert.EXPERT_BRIEF, 'explainer/explainer.yaml',
                     expert.QUESTIONS),
        'draft': script,
        'revise_medical': script + visuals,
        'storyboard_design': visuals,
        'voice_prep': (VOICE_PREP_ARTIFACT,),
        'shorts_plan': (SHORTS_PLAN_ARTIFACT,),
        'posts': (POSTS_ARTIFACT,),
        'script_review': ('reviews/script-review.yaml',),
        'product_review': (product_review.REPORT,),
        'visual_review': ('reviews/visual-review.yaml',),
        'revise_product': visuals + (POSTS_ARTIFACT, SHORTS_PLAN_ARTIFACT, VOICE_PREP_ARTIFACT),
        'revise_production': visuals + (POSTS_ARTIFACT,),
    }
    for relative in outputs.get(step, ()):
        path = revision / relative
        if path.is_file():
            read_agent_text(path)


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
                try:
                    failed_state = deps.read_state(project_dir)
                except Exception:  # noqa: BLE001
                    failed_state = WorkflowState.MEDICALLY_APPROVED
                record_failure(root, project_dir, failed_state, exc)
                return "blocked", None, f"bước produce lỗi: {_sanitize_reason(exc)}"
        b_log_dir = root / "topics" / "logs" / entry.slug / f"parallel-{b_step}"
        status, log_p, _, meta = _run_agent_invocation(
            root,
            deps,
            entry,
            project_dir,
            report,
            step=b_step,
            brief_context=brief_context,
            log_dir=b_log_dir,
            defer_validation_record=True,
            mark_blocked_on_failure=False,
        )
        if status != "ok":
            return status, log_p, (meta or {}).get("error")
        problem = _validate_nonstate_agent_step(deps, project_dir, b_step)
        if problem:
            _record_agent_validation_failure(
                root,
                entry.slug,
                project_dir,
                b_step,
                brief_context,
                (meta or {}).get("fingerprint"),
                problem,
            )
            return "blocked", log_p, problem
        with _topic_lock(entry.slug):
            clear_agent_retry(root, entry.slug, b_step)
        return "ok", log_p, None

    with ThreadPoolExecutor(max_workers=len(branches)) as pool:
        futures = {pool.submit(run_branch, b_step): b_step for b_step in branches}
        for future in as_completed(futures):
            b_step = futures[future]
            try:
                outcomes[b_step] = future.result()
            except Exception as exc:  # noqa: BLE001
                outcomes[b_step] = ("blocked", None, f"bước {b_step} lỗi: {_sanitize_reason(exc)}")

    if any(outcomes[b_step][0] == "paused" for b_step in branches):
        return "paused", len(branches)
    blocked_items = [
        (b_step, outcomes[b_step][1], outcomes[b_step][2])
        for b_step in branches
        if outcomes[b_step][0] == "blocked"
    ]
    if blocked_items:
        (root / "topics" / "logs" / entry.slug / WAITING_MODEL_FILE).unlink(missing_ok=True)
        with _REPORT_LOCK:
            if entry.slug in report.waiting_model:
                report.waiting_model.remove(entry.slug)
        parts = [
            f"{b_step}: {err}" if len(blocked_items) > 1 else err
            for b_step, _, err in blocked_items
            if err
        ]
        combined_err = "; ".join(parts) or (
            f"nhánh song song lỗi ({', '.join(b for b, _, _ in blocked_items)})"
        )
        first_log = next((lp for _, lp, _ in blocked_items if lp is not None), None)
        _mark_blocked(root, entry.slug, combined_err, report, log_path=first_log)
        return "blocked", len(branches)
    if any(outcomes[b_step][0] == "waiting_model" for b_step in branches):
        return "waiting_model", len(branches)
    with _topic_lock(entry.slug):
        clear_model_resume(root, entry.slug)
    _mark_advanced(root, entry.slug, report)
    return "ok", len(branches)


def _waiting_for_repair_idle(root: Path, slug: str, state: WorkflowState) -> bool:
    from healthvideo.workflows.repair_service import waiting_idle_for_topic

    return waiting_idle_for_topic(root, slug, state)


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
        candidate_dir = root / "projects" / entry.slug
        if (candidate_dir / "project.yaml").is_file():
            product_review.reconcile_doctor_question(root, candidate_dir)
            if _waiting_for_repair_idle(root, entry.slug, deps.read_state(candidate_dir)):
                with _REPORT_LOCK:
                    if entry.slug not in report.blocked:
                        report.blocked.append(entry.slug)
                continue
        if doctor_questions.open_question(root, entry.slug) is not None:
            with _REPORT_LOCK:
                if entry.slug not in report.waiting_doctor:
                    report.waiting_doctor.append(entry.slug)
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
                if (project_dir / "project.yaml").is_file():
                    product_review.reconcile_doctor_question(root, project_dir)
                if doctor_questions.open_question(root, entry.slug) is not None:
                    with _REPORT_LOCK:
                        if entry.slug not in report.waiting_doctor:
                            report.waiting_doctor.append(entry.slug)
                    break
                state = deps.read_state(project_dir)
                if _waiting_for_repair_idle(root, entry.slug, state):
                    with _REPORT_LOCK:
                        if entry.slug not in report.blocked:
                            report.blocked.append(entry.slug)
                    break
                pending_change = change_request.pending_note(project_dir)
                touches_script: bool | None = None
                if pending_change and state in {
                    WorkflowState.DRAFT_READY, WorkflowState.NEEDS_MEDICAL_REVISION,
                }:
                    requests = change_request.pending(project_dir)
                    if requests and requests[-1][1].get('kind') == 'edit_script':
                        touches_script = _change_touches_script(project_dir, pending_change)
                        reset_for_doctor_guidance(
                            project_dir,
                            str(requests[-1][0]),
                            require_script_rewrite=touches_script,
                        )
                with _topic_lock(entry.slug):
                    quota_step = model_resume_step(root, project_dir, brief_context)
                    outstanding = outstanding_agent_retry(root, project_dir, brief_context)
                forced_step = outstanding[0] if outstanding else quota_step
                if forced_step is None:
                    guidance = _active_leader_guidance(root, project_dir)
                    if guidance is not None:
                        guidance_step = guidance.get("step")
                        if (
                            isinstance(guidance_step, str)
                            and guidance_step in _GUIDANCE_STEPS_BY_STATE.get(state, ())
                        ):
                            forced_step = guidance_step
                repair_shorts = (
                    outstanding is not None
                    and outstanding[0] in {"visual_review", "produce"}
                    and outstanding[1]["kind"] == "validation"
                    and next_step(state) == "produce"
                    and _existing_invalid_shorts_plan(deps, project_dir)
                )
                if repair_shorts:
                    # Preserve the downstream hold; only its prerequisite may run.
                    # Keep this forced through final selection, and let shorts_plan's
                    # own persisted budget block a second failed repair.
                    forced_step = "shorts_plan"
                elif outstanding and not outstanding[1]["allowed"]:
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
                        if (status['kind'] == 'validation' and not forced_step
                                and _existing_invalid_shorts_plan(deps, project_dir)):
                            # Only the repair station may run, never production. Its existing
                            # agent-retry validation hold caps repair at ONE attempt per input
                            # fingerprint, including subsequent queue scans (output edits do
                            # not reset that budget). Failed repairs retain their diagnosis.
                            step = "shorts_plan"
                        else:
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
                    # An existing invalid plan blocks clip rendering inside visual_review.
                    # Missing plans keep the original visual-first order for new projects.
                    if not forced_step and _existing_invalid_shorts_plan(deps, project_dir):
                        step = "shorts_plan"
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
                        if step == "wait_doctor":
                            with _REPORT_LOCK:
                                if entry.slug not in report.waiting_doctor:
                                    report.waiting_doctor.append(entry.slug)
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
                        if pending_change:
                            if touches_script is None:
                                touches_script = _change_touches_script(project_dir, pending_change)
                            if touches_script:
                                step = "draft"
                            elif state == WorkflowState.DRAFT_READY:
                                step = "storyboard_design"
                            else:
                                step = next_script_action(project_dir)
                        else:
                            step = next_script_action(project_dir)
                    except (OSError, ValueError) as exc:
                        _mark_blocked(root, entry.slug, f"chấm kịch bản lỗi: {exc}", report)
                        break
                    if step == "wait_doctor":
                        with _REPORT_LOCK:
                            if entry.slug not in report.waiting_doctor:
                                report.waiting_doctor.append(entry.slug)
                        break
                if (step in {"script_review", "submit_medical"}
                        and state == WorkflowState.DRAFT_READY
                        and (step == 'submit_medical' or not in_rewrite_loop(project_dir))
                        and not pending_change and not forced_step):
                    need_sb = not deps.storyboard_ready(project_dir)
                    need_vp = not deps.voice_prep_ready(project_dir)
                    if need_vp and deps.voice_prep_ready is default_voice_prep_ready:
                        try:
                            if try_auto_voice_prep(project_dir, root=root) is not None:
                                need_vp = not deps.voice_prep_ready(project_dir)
                        except (OSError, TypeError, ValueError, yaml.YAMLError):
                            pass
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
                if (
                    step == "draft"
                    and state == WorkflowState.EVIDENCE_READY
                    and (not deps.expert_brief_ready(project_dir) or _has_open_questions(project_dir))
                ):
                    step = "research"  # no expert brief yet or open questions: research is not finished
                if forced_step:
                    step = forced_step
                rewriting = step == "draft" and state == WorkflowState.DRAFT_READY

                if steps_taken >= max_steps_per_topic:
                    _mark_blocked(root, entry.slug, "vượt số bước", report)
                    break

                log_dir = root / "topics" / "logs" / entry.slug
                result_log_path: Path | None = None
                pre_fingerprint: str | None = None

                if step in AGENT_STEPS:
                    reviewing = step in {"script_review", "product_review"}
                    reviewed_hash = (
                        script_hash(project_dir)
                        if step == "script_review"
                        else product_review.render_hash(project_dir)
                        if reviewing
                        else ""
                    )
                    outcome, result_log_path, _, invoke_meta = _run_agent_invocation(
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
                        defer_validation_record=True,
                    )
                    if outcome != "ok":
                        break
                    if is_project_paused(root, entry.slug):
                        break
                    pre_fingerprint = (invoke_meta or {}).get("fingerprint")
                    if reviewing:
                        record = (record_review if step == "script_review"
                                  else product_review.record_review)
                        try:
                            record(project_dir, reviewed_hash)
                        except (OSError, ValueError) as exc:
                            reason = (
                                f"{'chấm kịch bản' if step == 'script_review' else 'duyệt sản phẩm'} lỗi: {exc}"
                            )
                            _record_agent_validation_failure(
                                root,
                                entry.slug,
                                project_dir,
                                step,
                                brief_context,
                                pre_fingerprint,
                                reason,
                            )
                            _mark_blocked(
                                root,
                                entry.slug,
                                reason,
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
                            reason = f"visual_review lỗi: {exc}"
                            if isinstance(exc, ValueError):
                                _record_agent_validation_failure(
                                    root,
                                    entry.slug,
                                    project_dir,
                                    step,
                                    brief_context,
                                    pre_fingerprint,
                                    reason,
                                )
                            else:
                                with _topic_lock(entry.slug):
                                    clear_agent_retry(root, entry.slug, step)
                                    clear_model_resume(root, entry.slug)
                            record_failure(
                                root, project_dir, deps.read_state(project_dir), exc
                            )
                            _mark_blocked(root, entry.slug, reason, report)
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
                if step in {"visual_review", "script_review", "product_review", "revise_product"}:
                    _mark_advanced(root, entry.slug, report)
                elif rewriting:
                    unused = _unused_answers(project_dir)
                    if unused:
                        _record_agent_validation_failure(
                            root, entry.slug, project_dir, step, brief_context, pre_fingerprint, unused
                        )
                        _mark_blocked(root, entry.slug, unused, report, log_path=result_log_path)
                        break
                    try:
                        rewrite_action = next_script_action(project_dir)
                    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
                        reason = f"agent không sửa kịch bản theo nhận xét biên tập: {_sanitize_reason(exc)}"
                        _record_agent_validation_failure(
                            root, entry.slug, project_dir, step, brief_context, pre_fingerprint, reason
                        )
                        _mark_blocked(root, entry.slug, reason, report, log_path=result_log_path)
                        break
                    if rewrite_action == "wait_doctor":
                        with _REPORT_LOCK:
                            if entry.slug not in report.waiting_doctor:
                                report.waiting_doctor.append(entry.slug)
                        break
                    if rewrite_action == "draft":
                        rev_root, _ = _revision_root_or_error(project_dir)
                        detail = _diagnose_script_error(rev_root) if rev_root is not None else None
                        reason = (
                            f"agent không sửa kịch bản theo nhận xét biên tập: {detail}"
                            if detail
                            else "agent không sửa kịch bản theo nhận xét biên tập (script/script.yaml chưa thay đổi sau phê bình)"
                        )
                        _record_agent_validation_failure(
                            root, entry.slug, project_dir, step, brief_context, pre_fingerprint, reason
                        )
                        _mark_blocked(
                            root,
                            entry.slug,
                            reason,
                            report,
                            log_path=result_log_path,
                        )
                        break
                    _mark_advanced(root, entry.slug, report)
                elif step in {"posts", "storyboard_design", "voice_prep", "shorts_plan"}:
                    nonstate_problem = _validate_nonstate_agent_step(deps, project_dir, step)
                    if nonstate_problem:
                        _record_agent_validation_failure(
                            root,
                            entry.slug,
                            project_dir,
                            step,
                            brief_context,
                            pre_fingerprint,
                            nonstate_problem,
                        )
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
                    state in {
                        WorkflowState.DRAFT_READY,
                        WorkflowState.EVIDENCE_READY,
                        WorkflowState.NEEDS_MEDICAL_REVISION,
                    }
                    or new_state == WorkflowState.EVIDENCE_READY
                ):
                    problem = _expert_unfinished(project_dir, deps, state)
                    if problem:
                        _record_agent_validation_failure(
                            root, entry.slug, project_dir, step, brief_context, pre_fingerprint, problem
                        )
                        _mark_blocked(root, entry.slug, problem, report, log_path=result_log_path)
                        break
                    _mark_advanced(root, entry.slug, report)
                else:
                    if step in AGENT_STEPS and new_state == state:
                        reason = _diagnose_unchanged_state(deps, project_dir, step, state)
                        _record_agent_validation_failure(
                            root, entry.slug, project_dir, step, brief_context, pre_fingerprint, reason
                        )
                        _mark_blocked(
                            root,
                            entry.slug,
                            reason,
                            report,
                            log_path=result_log_path,
                        )
                        break
                    if new_state != state:
                        _mark_advanced(root, entry.slug, report)

                if (
                    pending_change
                    and step in {'draft', 'storyboard_design', 'revise_medical', 'revise_production'}
                    and new_state != WorkflowState.RESEARCH_IN_PROGRESS
                    and (new_state != state or rewriting or step == 'storyboard_design')
                ):
                    chat.completed(root, entry.slug, project_dir)

                if step in AGENT_STEPS:
                    guidance_path = _leader_guidance_path(root, entry.slug)
                    if guidance_path.is_file():
                        active_guidance = _active_leader_guidance(root, project_dir)
                        if active_guidance is None or active_guidance.get("step") == step or new_state != state:
                            guidance_path.unlink(missing_ok=True)
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
                doctor_questions.QUESTION_FILE,
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
                        for items in (report.blocked, report.at_gate, report.waiting_model, report.waiting_doctor):
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
