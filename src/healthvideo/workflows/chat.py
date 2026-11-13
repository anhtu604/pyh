"""Serialized coordinator conversations; Python alone executes confirmed actions."""

import json
import re
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.agents import RUNNING_MARKER, _quota_lock, invoke_with_failover
from healthvideo.company import load_company
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import read_yaml
from healthvideo.storage.queue import add_to_queue
from healthvideo.workflows import change_request

_LOCK = threading.RLock()
_RUN_LOCK = threading.Lock()
STEP_MARKER = '.chat-step-running'
_NUMBER_CHANGE = re.compile(
    # Claim words count only after a change verb: "giữ nguyên ... claim" is a visual edit.
    r'\bN\d+\b|\d\s*(?:mg|mmol|%|ml|mmhg|g/dl)'
    r'|(?:đổi|sửa|thay|tăng|giảm|thêm|bỏ|xoá|xóa|change|replace|edit)\s+(?:\S+\s+){0,3}?'
    r'(?:claim|số liệu|lời đọc|lời thoại)'
    r'|(?:đổi|sửa|thay|tăng|giảm|change|replace)\s+(?:số\s+)?\d', re.IGNORECASE)


class CoordinatorReply(BaseModel):
    model_config = ConfigDict(extra='forbid')

    reply: str = Field(min_length=1)
    action: Literal['none', 'ask', 'edit_production', 'edit_script', 'queue_topic', 'factory_feedback', 'status']
    brief: str = ''
    options: list[dict] = Field(default_factory=list)
    topic: dict | None = None
    escalate: bool = False

    @model_validator(mode='after')
    def valid_action(self):
        if self.action not in {'none', 'ask', 'status'} and not self.brief.strip():
            raise ValueError('Hành động này cần brief.')
        if self.action == 'ask' and (not 2 <= len(self.options) <= 3 or any(
            not isinstance(option.get(key), str) or not option[key].strip()
            for option in self.options for key in ('label', 'effect')
        )):
            raise ValueError('Câu hỏi cần 2–3 phương án có label và effect.')
        if self.action != 'ask' and self.options:
            raise ValueError('Chỉ action ask được có options.')
        if self.action == 'queue_topic':
            QueueEntry.model_validate({**(self.topic or {}), 'added': datetime.now().astimezone().date()})
        return self


def guard(reply: CoordinatorReply) -> CoordinatorReply:
    if reply.action == 'edit_production' and _NUMBER_CHANGE.search(reply.brief):
        return reply.model_copy(update={'action': 'edit_script'})
    return reply


@contextmanager
def locked(root: Path):
    # The factory runs in a separate process from the HTTP server.
    with _LOCK, _quota_lock(root / 'cache/chat-storage'):
        yield


def _path(root: Path, slug: str | None) -> Path:
    from healthvideo.workflows.dashboard_operations import inside, project_layout

    if slug:
        project = project_layout(root, slug).project_dir
        return inside(project, project / 'chat.jsonl')
    return inside(root, root / 'topics/chat.jsonl')


def load(root: Path, slug: str | None = None) -> list[dict]:
    """Fold append-only message updates into conversation order."""
    with locked(root):
        return _load(root, slug)


def _load(root: Path, slug: str | None) -> list[dict]:
    path = _path(root, slug)
    messages: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            messages[row['id']] = {**messages.get(row['id'], {}), **row}
    return list(messages.values())


def _append(root: Path, slug: str | None, row: dict) -> dict:
    path = _path(root, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    return row


def _message(who: str, text: str, context: dict, **fields) -> dict:
    return {'id': uuid4().hex, 'at': datetime.now().astimezone().isoformat(),
            'who': who, 'text': text, 'context': context, 'status': 'done', **fields}


def _find(root: Path, slug: str | None, message_id: str) -> dict:
    for row in _load(root, slug):
        if row['id'] == message_id:
            return row
    raise LookupError('Không tìm thấy tin chat này.')


def post(root: Path, slug: str | None, text: str, context: dict) -> dict:
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise ValueError('Tin chat cần nội dung từ 1 đến 4000 ký tự.')
    if not isinstance(context, dict) or set(context) - {'slug', 'revision', 'view', 'scene', 'time_s'}:
        raise ValueError('Ngữ cảnh chat không hợp lệ.')
    if context.get('slug') not in (None, slug):
        raise ValueError('Ngữ cảnh không thuộc project này.')
    with locked(root):
        row = _append(root, slug, _message('doctor', text.strip(), context, status='pending'))
    start(root, row['id'])
    return row


def start(root: Path, message_id: str) -> None:
    threading.Thread(target=run_coordinator, args=(root, message_id), daemon=True).start()


def _locate(root: Path, message_id: str) -> tuple[str | None, dict]:
    candidates = [None, *(p.parent.name for p in (root / 'projects').glob('*/chat.jsonl'))]
    for slug in candidates:
        for row in _load(root, slug):
            if row['id'] == message_id:
                return slug, row
    raise LookupError('Không tìm thấy tin chat này.')


def _input(root: Path, slug: str | None, message: dict) -> dict:
    from healthvideo.workflows.dashboard_operations import inside, project_layout

    data = {'message': message, 'recent': load(root, slug)[-20:], 'state': None, 'excerpts': {}}
    if slug:
        layout = project_layout(root, slug)
        data['state'] = layout.manifest.model_dump(mode='json')
        for relative, key, selected in (
            ('script/script.yaml', 'lines', message['context'].get('scene')),
            ('storyboard/storyboard.yaml', 'scenes', message['context'].get('scene')),
        ):
            path = inside(layout.artifact_root, layout.artifact_root / relative)
            if path.is_file():
                rows = read_yaml(path).get(key, [])
                data['excerpts'][key] = [row for row in rows if row.get('id') == selected
                                         or row.get('scene_id') == selected][:3]
        render = inside(layout.artifact_root, layout.artifact_root / 'renders/render-input.json')
        if render.is_file():
            scenes = json.loads(render.read_text(encoding='utf-8')).get('scenes', [])
            data['excerpts']['render_scenes'] = [row for row in scenes
                if row.get('id') == message['context'].get('scene')][:1]
    return data


def run_coordinator(root: Path, message_id: str, *, invoke=invoke_with_failover) -> dict:
    from healthvideo.workflows.runner import HARD_RULES

    # Threads wait here in posting order; the file lock also serializes multiple app processes.
    with _RUN_LOCK, _quota_lock(root / 'cache/coordinator-run'):
        with locked(root):
            slug, message = _locate(root, message_id)
            if message['status'] != 'pending':
                return message
        log_dir = root / 'topics/logs/chat'
        report = log_dir / f'{message_id}.yaml'
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            report.unlink(missing_ok=True)
            text = (Path(__file__).resolve().parent.parent / 'prompts/coordinator.md').read_text(encoding='utf-8')
            prompt = text.replace('{report}', str(report)).replace(
                '{input}', json.dumps(_input(root, slug, message), ensure_ascii=False))
            prompt += '\n\n## Quy tắc cứng\n' + '\n'.join(f'- {rule}' for rule in HARD_RULES) + '\n'
            company = load_company()
            # A fast model answers first; it may hand a hard question to a stronger chain once.
            for role_id in ('coordinator', 'coordinator_senior'):
                result = invoke(company.chain(role_id), prompt, cwd=root, log_dir=log_dir,
                                role=role_id, slug=slug or 'chung', step='coordinator')
                if not result.ok:
                    raise ValueError('Điều phối viên chưa trả lời được; hãy gửi lại.')
                reply = guard(CoordinatorReply.model_validate(read_yaml(report)))
                if not reply.escalate or role_id == 'coordinator_senior':
                    break
                with locked(root):
                    _append(root, slug, _message('coordinator', reply.reply, message['context'],
                                                 action='none', in_reply_to=message_id, status='done'))
                report.unlink(missing_ok=True)
                prompt += '\n## Vòng chuyên sâu\nĐiều tra kỹ rồi trả lời; escalate không còn tác dụng.\n'
            # Also guard against medical changes mentioned by the doctor but omitted in brief.
            if reply.action == 'edit_production' and _NUMBER_CHANGE.search(message['text']):
                reply = reply.model_copy(update={'action': 'edit_script'})
        except (OSError, RuntimeError, TypeError, ValueError, yaml.YAMLError) as exc:
            with locked(root):
                return _append(root, slug, {**message, 'status': 'failed', 'error': f'Lỗi Điều phối viên: {exc}'})
        with locked(root):
            _append(root, slug, {**message, 'status': 'done'})
            return _append(root, slug, _message('coordinator', reply.reply, message['context'],
                action=reply.action, brief=reply.brief, options=reply.options, topic=reply.topic,
                in_reply_to=message_id, status='pending' if reply.action in {
                    'edit_script', 'edit_production', 'queue_topic', 'factory_feedback'} else 'done'))


def _execute(root: Path, slug: str | None, message: dict) -> dict:
    from healthvideo.workflows import feedback_inbox
    from healthvideo.workflows.dashboard_operations import project_layout

    action = message.get('action')
    if action in {'edit_script', 'edit_production'}:
        if not slug:
            raise ValueError('Chọn project trước khi yêu cầu sửa.')
        change_request.request_change(project_layout(root, slug).project_dir, action,
                                      message['brief'], message['context'], now=datetime.now().astimezone())
    elif action == 'queue_topic':
        add_to_queue(root, QueueEntry(**message['topic'], added=datetime.now().astimezone().date()))
    elif action == 'factory_feedback':
        feedback_inbox.add_ready(root, slug or 'chung', message['brief'])
    else:
        raise ValueError('Tin này không có hành động cần xác nhận.')
    return _append(root, slug, {**message, 'status': 'done'})


def confirm(root: Path, slug: str | None, message_id: str) -> dict:
    with locked(root):
        message = _find(root, slug, message_id)
        if message['who'] != 'coordinator':
            raise ValueError('Chỉ xác nhận đề xuất của Điều phối viên.')
        if message['status'] in {'done', 'queued'}:
            return message
        if message['status'] != 'pending':
            raise ValueError('Tin này không thể xác nhận.')
        if message.get('action') in {'edit_script', 'edit_production'} and slug:
            log = root / 'topics/logs' / slug
            if any((log / marker).exists() for marker in (RUNNING_MARKER, STEP_MARKER)):
                return _append(root, slug, {**message, 'status': 'queued'})
        return _execute(root, slug, message)


@contextmanager
def step_boundary(root: Path, slug: str):
    """Apply confirmations before selecting a step, and protect its entire execution."""
    marker = root / 'topics/logs' / slug / STEP_MARKER
    with locked(root):
        rows = _load(root, slug) if (root / 'projects' / slug / 'chat.jsonl').is_file() else []
        queued = [row for row in rows if row['status'] == 'queued']
        for row in queued[:1]:
            try:
                _execute(root, slug, row)
            except ValueError as exc:
                _append(root, slug, {**row, 'status': 'failed', 'error': str(exc)})
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    try:
        yield
    finally:
        with locked(root):
            marker.unlink(missing_ok=True)


def completed(root: Path, slug: str, project: Path) -> None:
    with locked(root):
        requests = change_request.pending(project)
        if not requests:
            return
        context = requests[-1][1]['context']
        change_request.mark_applied(project)
        label = change_request.context_label(context)
        _append(root, slug, _message('coordinator', f'Đã sửa {label}, xem lại', context,
                                    action='none', link=f'/#project/{slug}'))
