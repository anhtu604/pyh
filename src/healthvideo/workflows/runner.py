"""Select the next factory workflow step for a project state."""

from typing import Literal

from healthvideo.domain.project_v2 import WorkflowState

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
    for field in PROMPT_FIELDS:
        value = fields.get(field)
        replacement = value if value is not None else "(không có)"
        text = text.replace(f"{{{field}}}", replacement)
    rules_block = "\n".join(f"- {rule}" for rule in HARD_RULES)
    return f"{text.rstrip()}\n\n## Quy tắc cứng\n{rules_block}\n"
