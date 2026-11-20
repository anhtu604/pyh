"""Serialized coordinator conversations; Python alone executes confirmed actions."""

import json
import os
import re
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.agents import (
    RUNNING_MARKER,
    _quota_lock,
    cancel_running_job,
    invoke_with_failover,
)
from healthvideo.company import COMPANY_PATH, load_company
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.process import is_same_process, process_token
from healthvideo.storage.files import read_yaml, write_text_atomic, write_yaml_atomic
from healthvideo.storage.queue import add_to_queue, load_queue
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


AssignmentAction = Literal[
    'sync_sheet_topics',
    'discover_topics',
    'analyze_channel',
    'sync_channel',
    'publish_video',
    'promote_inbox_topic',
    'queue_topic',
    'cancel_job',
    'retry_project',
    'edit_production',
    'edit_script',
    'factory_feedback',
    'status',
]

CoordinatorAction = Literal[
    'none',
    'ask',
    'edit_production',
    'edit_script',
    'queue_topic',
    'factory_feedback',
    'status',
    'dispatch',
    'sync_sheet_topics',
    'discover_topics',
    'analyze_channel',
    'sync_channel',
    'publish_video',
    'cancel_job',
    'retry_project',
    'promote_inbox_topic',
]

_LEGACY_CONFIRM_ACTIONS = frozenset({
    'edit_production',
    'edit_script',
    'queue_topic',
    'factory_feedback',
})

_APPROVED_GATE_STATES = frozenset({
    WorkflowState.MEDICALLY_APPROVED,
    WorkflowState.PRODUCTION_IN_PROGRESS,
    WorkflowState.AWAITING_VIDEO_REVIEW,
    WorkflowState.VIDEO_APPROVED,
    WorkflowState.PACKAGED,
    WorkflowState.PUBLISHED_MANUAL,
})


_STEP_TO_ACTION = frozenset({
    'sync_sheet_topics',
    'discover_topics',
    'analyze_channel',
    'sync_channel',
    'publish_video',
    'promote_inbox_topic',
    'queue_topic',
    'cancel_job',
    'retry_project',
    'edit_production',
    'edit_script',
    'factory_feedback',
})


class TaskAssignment(BaseModel):
    model_config = ConfigDict(extra='forbid')

    role: str = Field(min_length=1)
    step: str = Field(min_length=1)
    task: str = Field(min_length=1)
    slug: str | None = None
    action: AssignmentAction = 'status'
    brief: str = ''
    topic: dict | None = None
    job_id: str | None = None
    sheet_url: str | None = None
    query: str | None = None
    inbox_slug: str | None = None
    platform: Literal['youtube', 'tiktok'] | None = None
    clip_id: str | None = None
    privacy: str | None = None
    title_index: int | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def valid_assignment(self):
        if self.action == 'status' and self.step in _STEP_TO_ACTION:
            self.action = self.step  # type: ignore[assignment]
        if self.action == 'queue_topic' and self.topic is not None:
            QueueEntry.model_validate({**(self.topic or {}), 'added': datetime.now().astimezone().date()})
        return self


class CoordinatorReply(BaseModel):
    model_config = ConfigDict(extra='forbid')

    reply: str = Field(min_length=1)
    action: CoordinatorAction
    brief: str = ''
    options: list[dict] = Field(default_factory=list)
    topic: dict | None = None
    escalate: bool = False
    assignments: list[TaskAssignment] = Field(default_factory=list)
    job_id: str | None = None
    sheet_url: str | None = None
    query: str | None = None
    inbox_slug: str | None = None
    platform: Literal['youtube', 'tiktok'] | None = None
    clip_id: str | None = None
    privacy: str | None = None
    title_index: int | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def valid_action(self):
        if self.action in _LEGACY_CONFIRM_ACTIONS and not self.brief.strip():
            raise ValueError('Hành động này cần brief.')
        if self.action == 'dispatch' and not self.assignments and not self.brief.strip():
            raise ValueError('Phân việc cần danh sách assignments hoặc brief.')
        if self.action == 'cancel_job' and not (self.job_id or '').strip() and not self.brief.strip():
            raise ValueError('Hủy tác vụ cần job_id hoặc brief mô tả.')
        if self.action == 'promote_inbox_topic' and not (self.inbox_slug or '').strip() and not self.brief.strip():
            raise ValueError('Chuyển chủ đề cần inbox_slug hoặc brief.')
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
    updates: dict = {}
    if reply.action == 'edit_production' and _NUMBER_CHANGE.search(reply.brief):
        updates['action'] = 'edit_script'
    if reply.assignments:
        guarded = []
        changed = False
        for item in reply.assignments:
            if item.action == 'edit_production' and _NUMBER_CHANGE.search(item.brief or item.task):
                guarded.append(item.model_copy(update={'action': 'edit_script'}))
                changed = True
            else:
                guarded.append(item)
        if changed:
            updates['assignments'] = guarded
    return reply.model_copy(update=updates) if updates else reply


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


def post(root: Path, slug: str | None, text: str, context: dict,
         *, source: str = 'web', start_worker: bool = True) -> dict:
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise ValueError('Tin chat cần nội dung từ 1 đến 4000 ký tự.')
    if not isinstance(context, dict) or set(context) - {'slug', 'revision', 'view', 'scene', 'time_s'}:
        raise ValueError('Ngữ cảnh chat không hợp lệ.')
    if context.get('slug') not in (None, slug):
        raise ValueError('Ngữ cảnh không thuộc project này.')
    with locked(root):
        row = _append(root, slug, _message('doctor', text.strip(), context, status='pending', source=source))
    if start_worker:
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


def _running_jobs(root: Path) -> list[dict]:
    logs_root = root / 'topics/logs'
    if not logs_root.is_dir():
        return []
    jobs: list[dict] = []
    for path in sorted(logs_root.rglob('.job-*.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        pid = data.get('child_pid')
        token = data.get('child_process_token')
        if not isinstance(pid, int) or not is_same_process(pid, token):
            continue
        jobs.append({
            'job_id': data.get('job_id'),
            'role': data.get('role'),
            'slug': data.get('slug'),
            'step': data.get('step'),
            'cli': data.get('cli'),
            'model': data.get('model'),
            'started_at': data.get('started_at'),
            'child_pid': pid,
        })
    return jobs


def _company_summary(root: Path) -> dict:
    from healthvideo.workflows import channel_analytics, factory, researcher

    cfg = root / 'profiles/company.yaml'
    roster: list[dict] = []
    try:
        comp = load_company(cfg if cfg.is_file() else COMPANY_PATH)
        roster = [
            {'id': r.id, 'name': r.name, 'steps': list(r.steps)}
            for r in comp.roles.values()
        ]
    except (OSError, ValueError, TypeError):
        pass

    projects_list: list[dict] = []
    try:
        for path, project in factory.projects(root):
            blocked_file = root / 'topics/logs' / path.name / 'blocked.txt'
            projects_list.append({
                'slug': path.name,
                'title': factory.project_title(path, project),
                'state': project.state.value,
                'blocked_reason': (
                    blocked_file.read_text(encoding='utf-8', errors='replace').strip()[:240]
                    if blocked_file.is_file() else ''
                ),
            })
    except (OSError, ValueError, TypeError):
        pass

    queue_list: list[dict] = []
    try:
        queue_list = [{'slug': e.slug, 'title': e.title} for e in load_queue(root)]
    except (OSError, ValueError, TypeError):
        pass

    inbox_data: dict = {'summary': {}, 'top': []}
    try:
        inbox_items = researcher.load_inbox(root)
        inbox_data = {
            'summary': researcher.inbox_summary(root),
            'top': [
                {
                    'slug': it.get('slug'),
                    'title': it.get('title'),
                    'score': it.get('score'),
                    'tier': it.get('tier'),
                    'status': it.get('status'),
                }
                for it in inbox_items[:5]
            ],
        }
    except (OSError, ValueError, TypeError):
        pass

    channel_data: dict = {'connected': False}
    try:
        ch = channel_analytics.channel_overview_payload(root)
        channel_data = {
            key: ch.get(key) for key in ('connected', 'connections', 'data_available', 'analysis_ready', 'analysis_reason', 'sources', 'accounts', 'excluded_account_records', 'videos_count', 'total_views')
        }
    except (OSError, ValueError, TypeError):
        pass

    return {
        'roster': roster,
        'running_jobs': _running_jobs(root),
        'projects': projects_list,
        'queue': queue_list,
        'inbox': inbox_data,
        'channel': channel_data,
    }


def _input(root: Path, slug: str | None, message: dict) -> dict:
    from healthvideo.workflows.dashboard_operations import inside, project_layout

    data = {
        'message': message,
        'recent': load(root, slug)[-20:],
        'state': None,
        'excerpts': {},
        'company_summary': _company_summary(root),
    }
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


def _project_passed_gate(root: Path, target_slug: str | None) -> bool:
    from healthvideo.workflows.dashboard_operations import project_layout
    from healthvideo.workflows.review import latest_approval

    if not target_slug:
        return False
    try:
        layout = project_layout(root, target_slug)
    except (LookupError, OSError, ValueError):
        return False
    if layout.manifest.state in _APPROVED_GATE_STATES:
        return True
    return (
        latest_approval(layout.project_dir, GateKind.MEDICAL) is not None
        or latest_approval(layout.project_dir, GateKind.VIDEO) is not None
    )


def _retry_project_state(root: Path, target_slug: str) -> dict:
    from healthvideo.workflows.dashboard_operations import project_layout
    from healthvideo.workflows.production_retry import clear_retry

    layout = project_layout(root, target_slug)
    log_dir = root / 'topics/logs' / target_slug
    for fname in ('blocked.txt', 'waiting-model.txt', 'waiting-model-step.yaml', 'agent-retry.yaml'):
        (log_dir / fname).unlink(missing_ok=True)
    clear_retry(root, target_slug)
    manifest = layout.manifest
    if manifest.state is WorkflowState.BLOCKED and manifest.side_state is not None:
        target_state = manifest.side_state.resume_state
        if target_state is not None:
            manifest = transition_v2(
                manifest,
                target_state,
                TransitionContext(active_revision=manifest.active_revision),
            )
            write_yaml_atomic(layout.project_dir / 'project.yaml', manifest.model_dump(mode='json'))
    return {'slug': target_slug, 'state': manifest.state.value}


def _needs_doctor_confirmation(root: Path, default_slug: str | None, reply: CoordinatorReply) -> bool:
    if reply.action in _LEGACY_CONFIRM_ACTIONS and not reply.assignments:
        return True
    if reply.action == 'dispatch':
        for item in reply.assignments:
            if item.action in {'edit_script', 'edit_production'}:
                target = item.slug or default_slug
                if _project_passed_gate(root, target):
                    return True
    return False


def _execute_leader_operation(root: Path, default_slug: str | None, op: dict, context: dict) -> dict:
    from healthvideo.workflows import channel_analytics, feedback_inbox, researcher
    from healthvideo.workflows.dashboard_operations import project_layout

    action = op.get('action')
    target_slug = op.get('slug') or default_slug
    brief = str(op.get('brief') or op.get('task') or '').strip()

    if action == 'sync_sheet_topics':
        sheet_id, _ = channel_analytics.parse_sheet_reference(op.get('sheet_url'))
        res = researcher.sync_reference_sheet(root, spreadsheet_id=sheet_id)
        return {'action': action, 'ok': True, 'result': res}
    if action == 'discover_topics':
        res = researcher.discover_topics_with_agent(
            root, query=op.get('query') or brief or 'phòng bệnh thường gặp tại Việt Nam'
        )
        return {'action': action, 'ok': True, 'result': res}
    if action == 'sync_channel':
        from healthvideo.workflows.channel_connections import sync_connected_channel

        if op.get('platform') not in {'youtube', 'tiktok'}:
            raise ValueError('Cần chọn nền tảng để đồng bộ.')
        res = channel_analytics.save_synced_metrics(root, sync_connected_channel(root, op['platform']))
        return {'action': action, 'ok': True, 'result': res}
    if action == 'publish_video':
        from healthvideo.workflows.channel_publishing import publication_preview

        if not target_slug or op.get('platform') not in {'youtube', 'tiktok'} or not op.get('privacy'):
            raise ValueError('Đăng video cần slug, platform và privacy rõ ràng từ bác sĩ.')
        res = publication_preview(root, target_slug, platform=op['platform'], clip_id=op.get('clip_id'),
                                  title_index=op.get('title_index') or 0)
        return {'action': action, 'ok': True, 'preview': res,
                'requested_privacy': op['privacy'], 'needs_publication_confirmation': True,
                'message': 'Đã chuẩn bị bản xem trước. Bác sĩ mở màn hình đăng trong app, kiểm tra tài khoản, gói video và quyền hiển thị rồi xác nhận từng bài đăng.'}
    if action == 'analyze_channel':
        res = channel_analytics.analyze_channel_performance(root, focus=str(op.get('query') or brief or ''))
        return {'action': action, 'ok': True, 'result': res}
    if action == 'promote_inbox_topic':
        inbox_slug = str(op.get('inbox_slug') or op.get('slug') or brief).strip()
        res = researcher.promote_inbox_topic(root, inbox_slug, doctor_note=brief or None)
        return {'action': action, 'ok': True, 'result': res}
    if action == 'cancel_job':
        res = cancel_running_job(
            root,
            job_id=op.get('job_id') or None,
            slug=op.get('slug') or default_slug,
            role=op.get('role') or None,
        )
        return {'action': action, 'ok': True, 'cancelled': res}
    if action == 'retry_project':
        if not target_slug:
            raise ValueError('Cần chọn project để thử lại.')
        res = _retry_project_state(root, target_slug)
        return {'action': action, 'ok': True, 'result': res}
    if action == 'queue_topic':
        entry = QueueEntry(**op['topic'], added=datetime.now().astimezone().date())
        add_to_queue(root, entry)
        return {'action': action, 'ok': True, 'slug': entry.slug}
    if action == 'factory_feedback':
        feedback_inbox.add_ready(root, target_slug or 'chung', brief)
        return {'action': action, 'ok': True}
    if action in {'edit_script', 'edit_production'}:
        if not target_slug:
            raise ValueError('Chọn project trước khi yêu cầu sửa.')
        change_request.request_change(
            project_layout(root, target_slug).project_dir,
            action,
            brief,
            context,
            now=datetime.now().astimezone(),
        )
        return {'action': action, 'ok': True, 'slug': target_slug}
    return {'action': str(action or 'status'), 'ok': True}


def _execute_dispatch_reply(root: Path, slug: str | None, message: dict) -> dict:
    assignments_raw = message.get('assignments') or []
    context = message.get('context') or {}
    results: list[dict] = []
    updated_assignments: list[dict] = []
    if assignments_raw:
        for item in assignments_raw:
            op = dict(item)
            res = _execute_leader_operation(root, slug, op, context)
            results.append(res)
            updated_assignments.append({**op, 'status': 'done'})
    else:
        res = _execute_leader_operation(root, slug, message, context)
        results.append(res)
    return _append(root, slug, {
        **message,
        'assignments': updated_assignments or assignments_raw,
        'execution_results': results,
        'status': 'done',
    })


def _guard_channel_readiness(root: Path, reply: CoordinatorReply) -> CoordinatorReply:
    """Explain missing observations before assigning an impossible analysis task."""
    if reply.action != 'analyze_channel' and not any(item.action == 'analyze_channel' for item in reply.assignments):
        return reply
    from healthvideo.workflows.channel_analytics import channel_overview_payload

    overview = channel_overview_payload(root)
    if overview['analysis_ready']:
        return reply
    remaining = [item for item in reply.assignments if item.action != 'analyze_channel']
    return reply.model_copy(update={
        'action': 'dispatch' if remaining else 'status',
        'assignments': remaining,
        'reply': str(overview['analysis_reason']),
    })


def run_coordinator(root: Path, message_id: str, *, invoke=invoke_with_failover) -> dict:
    from healthvideo.company import role_skill_block
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
                skills = role_skill_block(role_id, company)
                role_prompt = f'{prompt}\n{skills}' if skills else prompt
                result = invoke(company.chain(role_id), role_prompt, cwd=root, log_dir=log_dir,
                                role=role_id, slug=slug or 'chung', step=role_id)
                if not result.ok:
                    raise ValueError('Điều phối viên chưa trả lời được; hãy gửi lại.')
                reply = _guard_channel_readiness(root, guard(CoordinatorReply.model_validate(read_yaml(report))))
                if not reply.escalate or role_id == 'coordinator_senior':
                    break
                with locked(root):
                    _append(root, slug, _message('coordinator', reply.reply, message['context'],
                                                 action='none', in_reply_to=message_id, status='done'))
                report.unlink(missing_ok=True)
                prompt += '\n## Vòng chuyên sâu\nĐiều tra kỹ rồi trả lời; escalate không còn tác dụng.\n'
            # Also guard against medical changes mentioned by the doctor but omitted in brief.
            if _NUMBER_CHANGE.search(message['text']):
                if reply.action == 'edit_production':
                    reply = reply.model_copy(update={'action': 'edit_script'})
                if reply.assignments:
                    updated_items = [
                        item.model_copy(update={'action': 'edit_script'})
                        if item.action == 'edit_production' else item
                        for item in reply.assignments
                    ]
                    reply = reply.model_copy(update={'assignments': updated_items})
        except (OSError, RuntimeError, TypeError, ValueError, yaml.YAMLError) as exc:
            with locked(root):
                return _append(root, slug, {**message, 'status': 'failed', 'error': f'Lỗi Điều phối viên: {exc}'})
        with locked(root):
            _append(root, slug, {**message, 'status': 'done'})
            needs_confirm = _needs_doctor_confirmation(root, slug, reply)
            outbound = _message(
                'coordinator',
                reply.reply,
                message['context'],
                action=reply.action,
                brief=reply.brief,
                options=reply.options,
                topic=reply.topic,
                assignments=[item.model_dump(mode='json') for item in reply.assignments],
                job_id=reply.job_id,
                sheet_url=reply.sheet_url,
                query=reply.query,
                inbox_slug=reply.inbox_slug,
                platform=reply.platform,
                clip_id=reply.clip_id,
                privacy=reply.privacy,
                title_index=reply.title_index,
                in_reply_to=message_id,
                status='pending' if needs_confirm else 'done',
            )
            saved = _append(root, slug, outbound)
            auto_ops = {
                'dispatch',
                'sync_sheet_topics',
                'discover_topics',
                'analyze_channel',
                'sync_channel',
                'publish_video',
                'cancel_job',
                'retry_project',
                'promote_inbox_topic',
            }
            if not needs_confirm and reply.action in auto_ops:
                try:
                    return _execute_dispatch_reply(root, slug, saved)
                except (OSError, RuntimeError, TypeError, ValueError, LookupError) as exc:
                    return _append(root, slug, {**saved, 'status': 'failed', 'error': f'Lỗi thực thi lệnh: {exc}'})
            return saved


def _execute(root: Path, slug: str | None, message: dict) -> dict:
    from healthvideo.workflows import feedback_inbox
    from healthvideo.workflows.dashboard_operations import project_layout

    action = message.get('action')
    if action in {'dispatch', 'sync_sheet_topics', 'discover_topics', 'analyze_channel', 'sync_channel', 'publish_video', 'cancel_job', 'retry_project', 'promote_inbox_topic'}:
        return _execute_dispatch_reply(root, slug, message)
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


def dismiss(root: Path, slug: str | None, message_id: str) -> dict:
    """Dismiss a pending coordinator proposal without executing it."""
    with locked(root):
        message = _find(root, slug, message_id)
        if message['who'] != 'coordinator':
            raise ValueError('Chỉ bỏ qua được đề xuất của Điều phối viên.')
        if message['status'] == 'dismissed':
            return message
        if message['status'] not in {'pending', 'proposed'}:
            raise ValueError('Tin này không thể bỏ qua.')
        return _append(root, slug, {**message, 'status': 'dismissed'})


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
        write_text_atomic(
            marker,
            json.dumps({
                'pid': os.getpid(),
                'process_token': process_token(os.getpid()),
                'started_at': datetime.now(UTC).isoformat(),
            }),
        )
    try:
        yield
    finally:
        with locked(root):
            marker.unlink(missing_ok=True)


def completed(root: Path, slug: str, project: Path) -> None:
    label: str | None = None
    with locked(root):
        requests = change_request.pending(project)
        if not requests:
            return
        context = requests[-1][1]['context']
        change_request.mark_applied(project)
        label = change_request.context_label(context)
        _append(root, slug, _message('coordinator', f'Đã sửa {label}, xem lại', context,
                                    action='none', link=f'/#project/{slug}'))
    if label:
        try:
            from healthvideo.workflows import telegram
            if telegram.configured():
                telegram.send_text(f'[{slug}] Đã sửa {label}, xem lại ở Dashboard /#project/{slug}')
        except (OSError, ValueError, RuntimeError):
            pass
