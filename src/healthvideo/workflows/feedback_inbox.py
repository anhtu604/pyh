"""Doctor's opinions: an independent agent turns each one into work items for Claude.

The analyst never edits anything but its report. Finished items stay in
``topics/feedback.yaml`` with status ``ready`` until Claude handles them and sets ``done``.
"""

import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field

from healthvideo.agents import (
    AgentResult,
    AllAgentsExhausted,
    invoke_with_failover,
)
from healthvideo.company import Company, load_company, role_skill_block
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.factory_deps import changed_code_paths, code_snapshot
from healthvideo.workflows.runner import PROMPTS_DIR

FEEDBACK_FILE = Path('topics/feedback.yaml')
REPORT_DIR = Path('topics/logs/feedback')
GENERAL = 'chung'
MAX_TEXT = 4000
ORPHAN_REASON = 'App đã tắt khi đang phân tích; bấm Phân tích lại.'

_LOCK = threading.RLock()
_RUN_LOCK = threading.Lock()  # one analyst at a time; local models and quotas are shared
_ACTIVE: set[str] = set()


class FeedbackTask(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: Literal['san_pham', 'xuong', 'chuan_kenh']
    target: str = Field(min_length=1)
    request: str = Field(min_length=1)
    done_when: str = Field(min_length=1)


class FeedbackAnalysis(BaseModel):
    model_config = ConfigDict(extra='forbid')

    summary: str = Field(min_length=1)
    tasks: list[FeedbackTask] = Field(min_length=1)


def load(root: Path) -> list[dict]:
    path = root / FEEDBACK_FILE
    return list(read_yaml(path).get('entries', [])) if path.is_file() else []


def _save(root: Path, entries: list[dict]) -> None:
    write_yaml_atomic(root / FEEDBACK_FILE, {'version': 1, 'entries': entries})


def _update(root: Path, entry_id: str, **fields: object) -> dict:
    with _LOCK:
        entries = load(root)
        for entry in entries:
            if entry['id'] == entry_id:
                entry.update(fields)
                _save(root, entries)
                return entry
    raise LookupError('Không tìm thấy ý kiến này.')


def add(root: Path, project: str, text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError('Nhập ý kiến trước khi gửi.')
    if len(text) > MAX_TEXT:
        raise ValueError(f'Ý kiến tối đa {MAX_TEXT} ký tự.')
    entry = {
        'id': uuid4().hex,
        'at': datetime.now().astimezone().isoformat(timespec='seconds'),
        'project': project,
        'text': text,
        'status': 'analyzing',
        'analysis': None,
        'error': None,
    }
    with _LOCK:
        _ACTIVE.add(entry['id'])
        _save(root, [*load(root), entry])
    return entry


def retry(root: Path, entry_id: str) -> dict:
    with _LOCK:
        entry = next((item for item in view(root) if item['id'] == entry_id), None)
        if entry is None:
            raise LookupError('Không tìm thấy ý kiến này.')
        if entry['status'] != 'failed':
            raise ValueError('Chỉ phân tích lại ý kiến đã lỗi.')
        _ACTIVE.add(entry_id)
        return _update(root, entry_id, status='analyzing', error=None)


def view(root: Path) -> list[dict]:
    """Newest first; an analysis no thread is running can never finish, so show it as failed."""
    with _LOCK:
        entries = load(root)
        for entry in entries:
            if entry['status'] == 'analyzing' and entry['id'] not in _ACTIVE:
                entry.update(status='failed', error=ORPHAN_REASON)
    return entries[::-1]


def _prompt(root: Path, entry: dict, report: Path, company: Company | None = None) -> str:
    text = (PROMPTS_DIR / 'feedback_triage.md').read_text(encoding='utf-8')
    fields = {'project': entry['project'], 'report': str(report), 'root': str(root),
              'text': entry['text']}
    for name, value in fields.items():
        text = text.replace(f'{{{name}}}', value)
    skills_block = role_skill_block('feedback_analyst', company)
    return f'{text.rstrip()}\n\n{skills_block}' if skills_block else text


def analyze(
    root: Path,
    entry_id: str,
    *,
    invoke: Callable[..., AgentResult] = invoke_with_failover,
    company: Company | None = None,
) -> None:
    """Run the analyst and store its validated work items; failures stay retryable."""
    log_dir = root / REPORT_DIR
    report = log_dir / f'{entry_id}.yaml'
    try:
        with _RUN_LOCK:
            entry = next(item for item in load(root) if item['id'] == entry_id)
            log_dir.mkdir(parents=True, exist_ok=True)
            report.unlink(missing_ok=True)
            guarded = (root / '.git').exists()
            before = code_snapshot(root) if guarded else {}
            company = company or load_company()
            result = invoke(company.chain('feedback_analyst'),
                            _prompt(root, entry, report, company), cwd=root, log_dir=log_dir,
                            role='feedback_analyst', slug=entry['project'],
                            step='feedback_inbox')
            if not result.ok:
                raise RuntimeError(f'Agent {result.agent} không phân tích được.')
            leaked = [path for path in (changed_code_paths(root, before) if guarded else [])
                      if path.parts[:1] != ('topics',)]
            if leaked:
                raise RuntimeError('Agent phân tích đã sửa file, cần xem lại: '
                                   + ', '.join(path.as_posix() for path in leaked))
            if not report.is_file():
                raise RuntimeError('Agent chưa ghi báo cáo phân tích.')
            analysis = FeedbackAnalysis.model_validate(read_yaml(report))
    except (AllAgentsExhausted, OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        _update(root, entry_id, status='failed', error=str(exc))
    else:
        report.unlink()
        _update(root, entry_id, status='ready', analysis=analysis.model_dump(mode='json'),
                error=None)
    finally:
        with _LOCK:
            _ACTIVE.discard(entry_id)


def start(root: Path, entry_id: str) -> None:
    threading.Thread(target=analyze, args=(root, entry_id), daemon=True).start()
