"""Select the next factory workflow step for a project state and run the queue."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from healthvideo.agents import (
    DEFAULT_AGENTS,
    AgentCli,
    AgentResult,
    AllAgentsExhausted,
    invoke_with_failover,
)
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import (
    read_yaml,
    write_text_atomic,
    write_yaml_atomic,
)
from healthvideo.storage.queue import load_queue

StepKind = Literal[
    "create",
    "research",
    "draft",
    "produce",
    "revise_medical",
    "revise_production",
]
AGENT_STEPS: frozenset[str] = frozenset(
    {"research", "draft", "revise_medical", "revise_production"}
)

_STEP_BY_STATE: dict[WorkflowState, StepKind] = {
    WorkflowState.TOPIC_SELECTED: "research",
    WorkflowState.RESEARCH_IN_PROGRESS: "research",
    WorkflowState.EVIDENCE_READY: "draft",
    WorkflowState.DRAFT_READY: "draft",
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


from pathlib import Path

PROMPTS_DIR: Path = Path(__file__).resolve().parent.parent / "prompts"

HARD_RULES: tuple[str, ...] = (
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


def render_prompt(step: str, **fields: str) -> str:
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


@dataclass
class RunReport:
    """Summary report produced by a queue run."""

    advanced: list[str] = field(default_factory=list)
    at_gate: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    code_changes: list[Path] = field(default_factory=list)
    exhausted: bool = False


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


def _record_code_changes(
    root: Path,
    slug: str,
    deps: RunDeps,
    report: RunReport,
) -> None:
    paths = deps.changed_code_paths(root)
    new_paths: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path not in report.code_changes:
            report.code_changes.append(path)
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
    agents: Sequence[AgentCli] = DEFAULT_AGENTS,
    once: bool = False,
    max_steps_per_topic: int = 20,
) -> RunReport:
    """Advance queued topics automatically until a review gate or blocker."""
    report = RunReport()
    entries = load_queue(root)

    for entry in entries:
        project_dir = root / "projects" / entry.slug
        if not project_dir.exists():
            project_dir = deps.create_project(root, entry)

        steps_taken = 0
        while True:
            state = deps.read_state(project_dir)
            step = next_step(state)
            if step is None:
                if state == WorkflowState.BLOCKED:
                    if entry.slug not in report.blocked:
                        report.blocked.append(entry.slug)
                else:
                    if entry.slug not in report.at_gate:
                        report.at_gate.append(entry.slug)
                break

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
                if step.startswith("revise_"):
                    prompt_fields["reject_note"] = (
                        deps.reject_note(project_dir) or ""
                    )
                prompt = render_prompt(step, **prompt_fields)
                try:
                    result = deps.invoke(
                        agents,
                        prompt,
                        cwd=root,
                        log_dir=log_dir,
                    )
                except AllAgentsExhausted:
                    report.exhausted = True
                    return report

                result_log_path = result.log_path
                _record_code_changes(root, entry.slug, deps, report)
                if not result.ok:
                    _mark_blocked(
                        root,
                        entry.slug,
                        f"agent {result.agent} thất bại ở bước {step}",
                        report,
                        log_path=result.log_path,
                    )
                    break
            elif step in deps.python_steps:
                try:
                    deps.python_steps[step](project_dir)
                except Exception as exc:  # noqa: BLE001 — one failing topic is blocked, the queue keeps going
                    _mark_blocked(
                        root,
                        entry.slug,
                        f"bước {step} lỗi: {type(exc).__name__}: {exc}",
                        report,
                    )
                    break
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
            if step in AGENT_STEPS and new_state == state:
                _mark_blocked(
                    root,
                    entry.slug,
                    "agent không làm đổi trạng thái",
                    report,
                    log_path=result_log_path,
                )
                break
            if new_state != state and entry.slug not in report.advanced:
                report.advanced.append(entry.slug)

            if once:
                return report

    return report
