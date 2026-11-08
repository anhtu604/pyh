"""Hand-off between the medical expert and the viral writer (spec 2026-11-08 §5.8).

The expert must leave ``evidence/expert-brief.md`` before the writer starts. The writer never
searches sources; a missing point goes into ``script/questions.yaml`` and the expert answers it.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from healthvideo.storage.files import read_yaml
from healthvideo.storage.project_layout import resolve_project_layout

EXPERT_BRIEF = 'evidence/expert-brief.md'
QUESTIONS = 'script/questions.yaml'


class WriterQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str = Field(min_length=1)
    ask: str = Field(min_length=1)
    line: str | None = None
    answer: str | None = None
    claim_ids: list[str] = Field(default_factory=list)

    @property
    def answered(self) -> bool:
        return bool((self.answer or '').strip())


class WriterQuestions(BaseModel):
    model_config = ConfigDict(extra='forbid')

    questions: list[WriterQuestion] = Field(default_factory=list)


def expert_brief_ready(project: Path) -> bool:
    """True when the active revision has a non-empty expert brief."""
    try:
        path = resolve_project_layout(project).artifact_root / EXPERT_BRIEF
        return path.is_file() and bool(path.read_text(encoding='utf-8').strip())
    except (OSError, ValueError):
        return False


def _questions(project: Path) -> list[WriterQuestion]:
    path = resolve_project_layout(project).artifact_root / QUESTIONS
    if not path.is_file():
        return []
    try:
        return WriterQuestions.model_validate(read_yaml(path)).questions
    except (TypeError, yaml.YAMLError, ValidationError) as exc:
        raise ValueError(f'{QUESTIONS} không hợp lệ: {exc}') from exc


def open_questions(project: Path) -> list[dict]:
    """Writer questions the expert has not answered yet."""
    return [item.model_dump() for item in _questions(project) if not item.answered]


def answered_questions(project: Path) -> list[dict]:
    """Answered questions the writer has not folded into the script (and removed) yet."""
    return [item.model_dump() for item in _questions(project) if item.answered]


def answer_notes(project: Path) -> str:
    """Render the expert's answers as rewrite instructions for the writer."""
    rows = []
    for item in answered_questions(project):
        where = f" (dòng {item['line']})" if item['line'] else ''
        claims = f" [claim: {', '.join(item['claim_ids'])}]" if item['claim_ids'] else ''
        rows.append(f"- {item['id']}{where}: {item['ask']} → {item['answer'].strip()}{claims}")
    if not rows:
        return ''
    return '\n'.join([
        f'Chuyên gia y học đã trả lời câu hỏi trong {QUESTIONS}; đưa vào kịch bản rồi xoá câu đã dùng:',
        *rows,
    ])
