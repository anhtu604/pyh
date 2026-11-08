"""Select the next factory workflow step for a project state and run the queue."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from healthvideo.agents import (
    AgentResult,
    AllAgentsExhausted,
    invoke_with_failover,
)
from healthvideo.company import Company, load_company, role_skill_block
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import (
    read_yaml,
    write_text_atomic,
    write_yaml_atomic,
)
from healthvideo.storage.queue import load_queue
from healthvideo.workflows import change_request, chat, expert, product_review
from healthvideo.workflows.production_retry import (
    clear_retry,
    record_failure,
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
    "script_review",
    "submit_medical",
    "posts",
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
        "script_review",
        "posts",
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
    code_snapshot: Callable[[Path], dict[str, str]] | None = None
    visual_review_pending: Callable[[Path], bool] = review_pending
    product_review_pending: Callable[[Path], bool] = product_review.pending
    # Spec 5.8: the writer starts only after the medical expert's brief exists. Production
    # wires ``expert.expert_brief_ready`` (factory_deps), like ``posts_ready``.
    expert_brief_ready: Callable[[Path], bool] = lambda _: True
    # Role table: which (cli, model) chain runs each agent step.
    company: Company = field(default_factory=load_company)


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


def run_queue(
    root: Path,
    deps: RunDeps,
    *,
    once: bool = False,
    max_steps_per_topic: int = 20,
) -> RunReport:
    """Advance queued topics automatically until a review gate or blocker."""
    report = RunReport()
    entries = load_queue(root)

    for entry in entries:
        waiting = root / "topics" / "logs" / entry.slug / WAITING_MODEL_FILE
        if waiting.exists():
            back = waiting_until(root, entry.slug)
            if back is not None and back > datetime.now(UTC):
                report.waiting_model.append(entry.slug)
                continue
            waiting.unlink()
        project_dir = root / "projects" / entry.slug
        if not project_dir.exists():
            project_dir = deps.create_project(root, entry)

        steps_taken = 0
        while True:
            with chat.step_boundary(root, entry.slug):
                state = deps.read_state(project_dir)
                pending_change = change_request.pending_note(project_dir)
                step = next_step(state)
                if step is None:
                    if state == WorkflowState.BLOCKED:
                        if entry.slug not in report.blocked:
                            report.blocked.append(entry.slug)
                    elif state in (WorkflowState.PACKAGED, WorkflowState.PUBLISHED_MANUAL):
                        pass  # finished topics are not waiting at any gate
                    else:
                        if entry.slug not in report.at_gate:
                            report.at_gate.append(entry.slug)
                    break

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

                if step == "produce" and deps.visual_review_pending(project_dir):
                    step = "visual_review"
                elif step == "produce" and not deps.posts_ready(project_dir):
                    step = "posts"
                elif step == "produce" and deps.product_review_pending(project_dir):
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
                if (step == "draft" and state == WorkflowState.EVIDENCE_READY
                        and not deps.expert_brief_ready(project_dir)):
                    step = "research"  # no expert brief yet: the research step is not finished
                rewriting = step == "draft" and state == WorkflowState.DRAFT_READY

                if steps_taken >= max_steps_per_topic:
                    _mark_blocked(root, entry.slug, "vượt số bước", report)
                    break

                log_dir = root / "topics" / "logs" / entry.slug
                result_log_path: Path | None = None

                if step in AGENT_STEPS:
                    prompt_fields: dict[str, str] = {
                        "project": str(project_dir),
                        "slug": entry.slug,
                        "title": entry.title,
                        "question": entry.question,
                        "doctor_note": entry.doctor_note or "",
                    }
                    if step.startswith("revise_") or step in {"draft", "script_review"}:
                        prompt_fields["reject_note"] = (
                            deps.reject_note(project_dir) or ""
                        )
                    if step == "revise_product":
                        prompt_fields["reject_note"] = product_review.revision_notes(project_dir)
                    if rewriting:
                        notes = (expert.answer_notes(project_dir) if answering
                                 else revision_notes(project_dir))
                        prompt_fields["reject_note"] = (
                            f"{notes}\n{prompt_fields['reject_note']}"
                        ).strip()
                    prompt = render_prompt(step, company=deps.company, **prompt_fields)
                    standards_block = prompt_block(root, slug=entry.slug)
                    if standards_block:
                        body, heading, rules = prompt.rpartition('## Quy tắc cứng')
                        prompt = f"{body.rstrip()}\n\n{standards_block.rstrip()}\n\n{heading}{rules}"
                    before = deps.code_snapshot(root) if deps.code_snapshot is not None else None
                    reviewing = step in {"script_review", "product_review"}
                    reviewed_hash = (
                        script_hash(project_dir) if step == "script_review"
                        else product_review.render_hash(project_dir) if reviewing else ""
                    )
                    role = deps.company.role_for_step(step)
                    try:
                        result = deps.invoke(
                            deps.company.chain(role.id),
                            prompt,
                            cwd=root,
                            log_dir=log_dir,
                            role=role.id,
                            slug=entry.slug,
                            step=step,
                        )
                    except AllAgentsExhausted as exc:
                        # Only this topic waits for a model; the rest of the queue keeps going.
                        _record_code_changes(root, entry.slug, deps, report, before)
                        back = exc.earliest_return
                        write_text_atomic(
                            log_dir / WAITING_MODEL_FILE, back.isoformat() if back else ""
                        )
                        report.waiting_model.append(entry.slug)
                        break

                    result_log_path = result.log_path
                    _record_code_changes(root, entry.slug, deps, report, before)
                    if not result.ok:
                        _mark_blocked(
                            root,
                            entry.slug,
                            f"agent {result.agent} thất bại ở bước {step}",
                            report,
                            log_path=result.log_path,
                        )
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
                                log_path=result.log_path,
                            )
                            break
                    if step == "revise_product":
                        # Python re-renders the fix at once; an unchanged render goes to the doctor.
                        try:
                            product_review.mark_fix_attempted(project_dir)
                            deps.python_steps["produce"](project_dir)
                        except Exception as exc:  # noqa: BLE001
                            record_failure(root, project_dir, deps.read_state(project_dir), exc)
                            _mark_blocked(root, entry.slug, f"dựng lại sau sửa lỗi: {exc}", report)
                            break
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
                            deps.python_steps["produce"](project_dir)
                        except Exception as exc:  # noqa: BLE001
                            record_failure(
                                root, project_dir, deps.read_state(project_dir), exc
                            )
                            _mark_blocked(root, entry.slug, f"visual_review lỗi: {exc}", report)
                            break
                        clear_retry(root, entry.slug)
                elif step in deps.python_steps:
                    try:
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
                elif step == "posts":
                    if not deps.posts_ready(project_dir):
                        _mark_blocked(
                            root,
                            entry.slug,
                            "agent không làm đổi trạng thái: posts.yaml chưa hợp lệ",
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

                if once:
                    return report

    return report
