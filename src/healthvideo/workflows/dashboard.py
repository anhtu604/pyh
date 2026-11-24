"""Localhost dashboard for the factory: watch, control, and decide gates.

Gate decisions still need the approver PIN, typed by the doctor in the app and
verified here; the PIN is never stored, logged, or passed to agents.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import urlopen

import yaml

from healthvideo.agents import ACTIVITY_FILE, QUOTA_FILE, RUNNING_MARKER, QuotaBook
from healthvideo.approver_pin import pin_path, verify_pin
from healthvideo.company import COMPANY_PATH, REPO_ROOT, load_company
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.env import child_env, hide_child_consoles
from healthvideo.process import is_same_process, process_token, resolve_pnpm_argv
from healthvideo.project_codes import project_codes
from healthvideo.storage.files import read_yaml, write_text_atomic, write_yaml_atomic
from healthvideo.storage.queue import load_queue
from healthvideo.workflows import (
    app_update,
    asset_library,
    change_request,
    channel_analytics,
    chat,
    dashboard_operations,
    decision_card,
    doctor_questions,
    factory,
    feedback_inbox,
    medanim_library,
    product_review,
    production_retry,
    repair_service,
    researcher,
    standards,
)
from healthvideo.workflows.gate_review import approve_gate, reject_gate, resume_gate
from healthvideo.workflows.script_review import (
    CRITERIA,
    CYCLE_LIMIT_REASON,
    PASS_SCORE,
    review_view,
)

APP_ID = 'healthvideo-dashboard'
DEFAULT_PORT = 8765
FALLBACK_PORT_END = 8775
SERVER_STATE_FILE = 'cache/dashboard-server.json'
TOKEN_FILE = 'cache/dashboard-token.txt'
STUDIO_URL = 'http://localhost:3000'
HTML_PATH = Path(__file__).with_name('dashboard.html')
LOG_TAIL = 40
MAX_BODY = 16_000
MAX_PIN_FAILURES = 5
LOCKOUT_SECONDS = 600
RESUME_TARGETS: dict[GateKind, tuple[tuple[WorkflowState, str], ...]] = {
    GateKind.MEDICAL: (
        (WorkflowState.DRAFT_READY, 'Sửa kịch bản/storyboard'),
        (WorkflowState.RESEARCH_IN_PROGRESS, 'Tìm thêm bằng chứng'),
    ),
    GateKind.VIDEO: (
        (WorkflowState.PRODUCTION_IN_PROGRESS, 'Chỉ dựng/render lại'),
        (WorkflowState.DRAFT_READY, 'Sai nội dung, quay lại kịch bản'),
    ),
}

STAGES: tuple[str, ...] = (
    'Chủ đề', 'Nghiên cứu', 'Kịch bản', 'Duyệt y khoa', 'Sản xuất', 'Duyệt video', 'Đóng gói',
)
_STAGE_OF: dict[WorkflowState, int] = {
    WorkflowState.IDEA: 0,
    WorkflowState.TOPIC_SELECTED: 0,
    WorkflowState.TOPIC_REJECTED: 0,
    WorkflowState.RESEARCH_IN_PROGRESS: 1,
    WorkflowState.EVIDENCE_READY: 2,
    WorkflowState.DRAFT_READY: 2,
    WorkflowState.NEEDS_MEDICAL_REVISION: 2,
    WorkflowState.AWAITING_MEDICAL_REVIEW: 3,
    WorkflowState.MEDICALLY_APPROVED: 4,
    WorkflowState.PRODUCTION_IN_PROGRESS: 4,
    WorkflowState.NEEDS_PRODUCTION_REVISION: 4,
    WorkflowState.AWAITING_VIDEO_REVIEW: 5,
    WorkflowState.VIDEO_APPROVED: 6,
    WorkflowState.PACKAGED: 6,
    WorkflowState.PUBLISHED_MANUAL: 6,
}
STATE_LABELS: dict[WorkflowState, str] = {
    WorkflowState.IDEA: 'Ý tưởng',
    WorkflowState.TOPIC_SELECTED: 'Đã chọn chủ đề',
    WorkflowState.TOPIC_REJECTED: 'Chủ đề bị loại',
    WorkflowState.RESEARCH_IN_PROGRESS: 'Đang nghiên cứu',
    WorkflowState.EVIDENCE_READY: 'Đủ bằng chứng',
    WorkflowState.DRAFT_READY: 'Đang viết kịch bản',
    WorkflowState.AWAITING_MEDICAL_REVIEW: 'Chờ bác sĩ duyệt y khoa',
    WorkflowState.MEDICALLY_APPROVED: 'Đã duyệt y khoa',
    WorkflowState.PRODUCTION_IN_PROGRESS: 'Đang sản xuất video',
    WorkflowState.AWAITING_VIDEO_REVIEW: 'Chờ bác sĩ duyệt video',
    WorkflowState.VIDEO_APPROVED: 'Đã duyệt video',
    WorkflowState.PACKAGED: 'Đã đóng gói',
    WorkflowState.PUBLISHED_MANUAL: 'Đã đăng',
    WorkflowState.NEEDS_MEDICAL_REVISION: 'Đang sửa theo góp ý y khoa',
    WorkflowState.NEEDS_PRODUCTION_REVISION: 'Đang sửa video theo góp ý',
    WorkflowState.BLOCKED: 'Bị chặn',
}


def stage_index(project: ProjectManifestV2) -> int:
    """Map main and side states onto the 7-step progress bar."""
    state = project.state
    if state is WorkflowState.BLOCKED and project.side_state is not None:
        state = project.side_state.resume_state or state
    return _STAGE_OF.get(state, 0)


def _tail(path: Path, lines: int) -> list[str]:
    if not path.is_file():
        return []
    with path.open('rb') as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - 64_000))
        text = stream.read().decode('utf-8', errors='replace')
    return [line for line in text.splitlines() if line.strip()][-lines:]


PRODUCTION_RUNNING_MARKER = '.production-running'
_APP_LIVE_ROLES: frozenset[str] = frozenset({
    'coordinator',
    'coordinator_senior',
    'feedback_analyst',
    'researcher',
})
_APP_LIVE_STEPS: frozenset[str] = frozenset({
    'chat',
    'chat_deep',
    'coordinator',
    'feedback_inbox',
    'topic_research',
    'channel_analytics',
})
_APP_LIVE_SCOPES: frozenset[str] = frozenset({'chat', 'feedback', 'researcher', 'channel'})
_BLOCKED_STEP_RE = re.compile(r'(?:ở bước|bước)\s+([a-z_]+)|^([a-z_]+)\s+lỗi:', re.IGNORECASE)


def _valid_pid(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _marker_scope(marker: Path) -> str:
    return marker.parent.parent.name if marker.parent.name.startswith('parallel-') else marker.parent.name


def _read_agent_marker(marker: Path) -> dict:
    """Verify per-topic/chat/feedback .agent-running line-3 process identity."""
    scope = _marker_scope(marker)
    if not marker.is_file():
        return {'state': 'missing', 'scope': scope}
    try:
        lines = marker.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return {'state': 'unverified', 'scope': scope}
    agent_name = lines[0].strip() if lines and lines[0].strip() else 'agent'
    started_at = lines[1].strip() if len(lines) > 1 else ''
    if len(lines) < 3 or not lines[2].strip():
        return {'state': 'unverified', 'agent': agent_name, 'scope': scope}
    try:
        meta = json.loads(lines[2])
    except ValueError:
        return {'state': 'unverified', 'agent': agent_name, 'scope': scope}
    if not isinstance(meta, dict):
        return {'state': 'unverified', 'agent': agent_name, 'scope': scope}
    pid = meta.get('pid')
    token = meta.get('process_token')
    raw_job_id = meta.get('job_id')
    job_id = raw_job_id.strip() if isinstance(raw_job_id, str) else ''
    if not _valid_pid(pid) or not isinstance(token, str) or not token.strip() or not job_id:
        return {'state': 'unverified', 'agent': agent_name, 'scope': scope}
    if is_same_process(pid, token):
        return {
            'state': 'running',
            'agent': agent_name,
            'pid': pid,
            'process_token': token,
            'job_id': job_id,
            'started_at': str(meta.get('started_at') or started_at),
            'scope': scope,
        }
    return {'state': 'stale', 'agent': agent_name, 'scope': scope}


def running_agents(root: Path) -> list[str]:
    """Verified live agent CLIs; live chat/feedback still report when the factory daemon is off."""
    factory_on = factory.running_pid(root) is not None
    names: list[str] = []
    logs_dir = root / 'topics' / 'logs'
    markers = sorted([*logs_dir.glob(f'*/{RUNNING_MARKER}'), *logs_dir.glob(f'*/parallel-*/{RUNNING_MARKER}')])
    for marker in markers:
        info = _read_agent_marker(marker)
        if info.get('state') != 'running':
            continue
        if not factory_on and info.get('scope') not in _APP_LIVE_SCOPES:
            continue
        names.append(str(info.get('agent') or 'agent'))
    return names


def _active_running_jobs(root: Path) -> list[dict]:
    """Read live .job-*.json sidecars verified by child OS PID + creation token."""
    logs_dir = root / 'topics' / 'logs'
    if not logs_dir.is_dir():
        return []
    jobs: list[dict] = []
    for path in sorted(logs_dir.rglob('.job-*.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        pid = data.get('child_pid')
        token = data.get('child_process_token')
        if not _valid_pid(pid) or not isinstance(token, str) or not is_same_process(pid, token):
            continue
        step = str(data.get('step') or '')
        jobs.append({
            'job_id': str(data.get('job_id') or ''),
            'role': str(data.get('role') or ''),
            'slug': str(data.get('slug') or ''),
            'step': step,
            'step_label': STEP_LABELS.get(step, step),
            'cli': str(data.get('cli') or ''),
            'model': str(data.get('model') or ''),
            'started_at': str(data.get('started_at') or ''),
            'child_pid': pid,
        })
    return jobs


def _inspect_production_markers(
    root: Path,
    *,
    now_dt: datetime,
) -> tuple[list[dict], list[dict]]:
    """Read topics/logs/<slug>/.production-running and verify PID + creation token."""
    factory_on = factory.running_pid(root) is not None
    titles = {path.name: factory.project_title(path, proj) for path, proj in factory.projects(root)}
    running: list[dict] = []
    unverified: list[dict] = []
    for marker in sorted((root / 'topics' / 'logs').glob(f'*/{PRODUCTION_RUNNING_MARKER}')):
        slug = marker.parent.name
        if slug not in titles:
            continue
        try:
            data = json.loads(marker.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            unverified.append({'slug': slug, 'reason': 'Marker máy dựng không đọc được'})
            continue
        if not isinstance(data, dict):
            unverified.append({'slug': slug, 'reason': 'Marker máy dựng sai định dạng'})
            continue
        pid = data.get('pid')
        token = data.get('process_token')
        started_raw = str(data.get('started_at') or '')
        if not _valid_pid(pid) or not isinstance(token, str) or not token.strip():
            unverified.append({'slug': slug, 'reason': 'Marker máy dựng thiếu định danh'})
            continue
        if factory_on and is_same_process(pid, token):
            started_dt = _parse_iso(started_raw)
            duration_s = (
                round(max(0.0, (now_dt - started_dt).total_seconds()), 1)
                if started_dt is not None else 0.0
            )
            running.append({
                'slug': slug,
                'title': titles.get(slug, slug),
                'pid': pid,
                'started_at': started_raw,
                'duration_s': duration_s,
            })
    return running, unverified


def production_running(
    root: Path,
    *,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> list[dict]:
    """Active production runs verified by OS process creation token."""
    return _inspect_production_markers(root, now_dt=now())[0]


def _active_work_blocker(root: Path) -> str | None:
    """Return a Vietnamese refusal message if any agent or production step is currently running."""
    prod = production_running(root)
    if prod:
        labels = ', '.join(str(item.get('title') or item.get('slug') or 'dự án') for item in prod[:3])
        return f'Không thể cập nhật: đang có bước dựng video chạy dở ({labels}). Hãy chờ dựng xong rồi thử lại.'
    jobs = _active_running_jobs(root)
    if jobs:
        labels = ', '.join(
            str(item.get('step_label') or item.get('role') or item.get('slug') or 'agent')
            for item in jobs[:3]
        )
        return f'Không thể cập nhật: đang có agent chạy dở ({labels}). Hãy chờ agent hoàn tất rồi thử lại.'
    agents = running_agents(root)
    if agents:
        labels = ', '.join(agents[:3])
        return f'Không thể cập nhật: đang có agent chạy dở ({labels}). Hãy chờ agent hoàn tất rồi thử lại.'
    return None


STEP_LABELS: dict[str, str] = {
    'create': 'Đang tạo dự án',
    'scout': 'Đang trinh sát chủ đề',
    'research': 'Đang nghiên cứu y văn',
    'draft': 'Đang viết kịch bản',
    'storyboard_design': 'Đang thiết kế storyboard',
    'voice_prep': 'Đang chuẩn hóa phiên âm',
    'script_review': 'Đang chấm kịch bản',
    'posts': 'Đang soạn bài đăng',
    'shorts_plan': 'Đang lên kế hoạch Shorts',
    'produce': 'Đang dựng video',
    'visual_review': 'Đang chọn hình minh họa',
    'product_review': 'Đang kiểm định video',
    'revise_medical': 'Đang sửa theo góp ý y khoa',
    'revise_production': 'Đang sửa hình/nhịp video',
    'revise_product': 'Đang sửa lỗi sản phẩm',
    'topic_research': 'Đang tìm & chấm chủ đề',
    'channel_analytics': 'Đang phân tích kênh',
    'chat': 'Đang trả lời chat',
    'chat_deep': 'Đang phân tích chuyên sâu',
    'coordinator': 'Đang điều phối chat',
    'feedback_inbox': 'Đang phân tích ý kiến',
    'repair': 'Tự sửa lỗi kỹ thuật',
}


_TERMINAL_STATES: frozenset[WorkflowState] = frozenset({
    WorkflowState.VIDEO_APPROVED,
    WorkflowState.PACKAGED,
    WorkflowState.PUBLISHED_MANUAL,
    WorkflowState.TOPIC_REJECTED,
})


def _safe_astimezone(dt: datetime) -> datetime:
    """Convert to local timezone without failing on Windows boundary dates."""
    try:
        return dt.astimezone()
    except (OSError, OverflowError, ValueError):
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _format_hhmm(dt: datetime) -> str:
    """Format local HH:MM safely even when Windows rejects tz conversion."""
    local_dt = _safe_astimezone(dt)
    try:
        return local_dt.strftime('%H:%M')
    except (OSError, OverflowError, ValueError):
        try:
            return dt.strftime('%H:%M')
        except (OSError, OverflowError, ValueError):
            return dt.isoformat()


def _safe_mtime_optional(path: Path) -> datetime | None:
    try:
        return _safe_astimezone(datetime.fromtimestamp(path.stat().st_mtime, tz=UTC))
    except (OSError, OverflowError, ValueError):
        return None


def _safe_mtime(path: Path, fallback: datetime) -> datetime:
    return _safe_mtime_optional(path) or fallback


def _safe_quota_snapshot(root: Path, now_dt: datetime) -> tuple[list[dict], bool]:
    try:
        entries = QuotaBook(root / QUOTA_FILE).snapshot(now_dt)
        if not isinstance(entries, list):
            return [], True
        return [entry for entry in entries if isinstance(entry, dict)], False
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, yaml.YAMLError):
        return [], True


def _parse_iso(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo else _safe_astimezone(parsed)
    except (ValueError, OSError, OverflowError):
        return None


def _role_names() -> dict[str, str]:
    try:
        return {role_id: role.name for role_id, role in load_company().roles.items()}
    except ValueError:
        return {}


PROGRESS_FILE = Path('docs/progress.yaml')
PROGRESS_STATUSES = ('todo', 'doing', 'done', 'blocked')


def progress(root: Path) -> dict:
    """Development plan progress for the home page, read from ``docs/progress.yaml``."""
    path = root / PROGRESS_FILE
    if not path.is_file():
        return {'updated': None, 'done': 0, 'total': 0, 'doing': [], 'phases': []}
    data = read_yaml(path)
    phases, doing, done, total = [], [], 0, 0
    for phase in data.get('phases') or []:
        tasks = []
        for task in phase.get('tasks') or []:
            status = task.get('status') if task.get('status') in PROGRESS_STATUSES else 'todo'
            item = {
                'id': str(task.get('id', '')),
                'title': str(task.get('title', '')),
                'status': status,
                'owner': str(task.get('owner') or ''),
                'note': str(task.get('note') or ''),
            }
            tasks.append(item)
            total += 1
            done += status == 'done'
            if status == 'doing':
                doing.append(item)
        phases.append({
            'id': str(phase.get('id', '')),
            'title': str(phase.get('title', '')),
            'done': sum(t['status'] == 'done' for t in tasks),
            'total': len(tasks),
            'tasks': tasks,
        })
    return {'updated': str(data.get('updated') or '') or None, 'done': done, 'total': total,
            'doing': doing, 'phases': phases}


def activity(
    root: Path,
    *,
    limit: int = 10,
    slug: str | None = None,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> dict:
    """Recent completed agent events plus verified currently running jobs."""
    path = root / ACTIVITY_FILE
    roles = _role_names()
    current_now = _safe_astimezone(now())
    factory_on = factory.running_pid(root) is not None
    open_starts: dict[tuple[str, ...], tuple[dict, datetime | None]] = {}
    history: list[dict] = []
    if path.is_file():
        for raw in path.read_text(encoding='utf-8', errors='replace').splitlines():
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            if slug and str(row.get('slug') or '') != slug:
                continue
            raw_job_id = row.get('job_id')
            job_id = raw_job_id.strip() if isinstance(raw_job_id, str) else ''
            key: tuple[str, ...] = (
                ('job', job_id)
                if job_id
                else (
                    'legacy',
                    str(row.get('slug') or ''),
                    str(row.get('step') or ''),
                    str(row.get('role') or ''),
                    str(row.get('cli') or ''),
                    str(row.get('model') or ''),
                )
            )
            role_id = str(row.get('role') or '')
            enriched = {
                **row,
                'role_name': roles.get(role_id, role_id),
                'step_label': STEP_LABELS.get(str(row.get('step') or ''), str(row.get('step') or '')),
            }
            event = row.get('event')
            at_dt = _parse_iso(row.get('at'))
            if event == 'start':
                open_starts[key] = (enriched, at_dt)
            elif event == 'end':
                prior = open_starts.pop(key, None)
                duration_s = 0.0
                started_at = row.get('at')
                if prior is not None:
                    started_at = prior[0].get('at')
                    if prior[1] is not None and at_dt is not None:
                        duration_s = round(max(0.0, (at_dt - prior[1]).total_seconds()), 1)
                history.append({
                    **enriched,
                    'started_at': started_at,
                    'duration_s': duration_s,
                    'running': False,
                })
            elif event == 'quota':
                history.append({
                    **enriched,
                    'started_at': row.get('at'),
                    'duration_s': 0.0,
                    'running': False,
                })

    running: list[dict] = []
    for start_row, start_dt in open_starts.values():
        pid = start_row.get('pid')
        token = start_row.get('process_token')
        raw_job_id = start_row.get('job_id')
        job_id = raw_job_id.strip() if isinstance(raw_job_id, str) else ''
        has_identity = (
            bool(job_id)
            and _valid_pid(pid)
            and isinstance(token, str)
            and bool(token.strip())
        )
        role_id = str(start_row.get('role') or '')
        step_id = str(start_row.get('step') or '')
        app_live = role_id in _APP_LIVE_ROLES or step_id in _APP_LIVE_STEPS
        if not has_identity:
            history.append({
                **start_row,
                'started_at': start_row.get('at'),
                'duration_s': 0.0,
                'running': False,
                'ok': None,
                'interrupted': True,
                'unverified': True,
            })
            continue
        if not is_same_process(pid, token) or (not factory_on and not app_live):
            history.append({
                **start_row,
                'started_at': start_row.get('at'),
                'duration_s': 0.0,
                'running': False,
                'ok': None,
                'interrupted': True,
                'unverified': False,
            })
            continue
        duration_s = 0.0
        if start_dt is not None:
            duration_s = round(max(0.0, (current_now - start_dt).total_seconds()), 1)
        running.append({
            **start_row,
            'started_at': start_row.get('at'),
            'duration_s': duration_s,
            'running': True,
        })
    recent = history[::-1][: max(1, int(limit))]
    return {
        'running': running,
        'recent': recent,
        'items': [*running, *recent],
    }


def _blocked_note(root: Path, path: Path, project: ProjectManifestV2) -> str:
    blocked = root / 'topics' / 'logs' / path.name / 'blocked.txt'
    reason = path / 'blocked-reason.md'
    if project.state is WorkflowState.BLOCKED or blocked.exists():
        source = reason if reason.exists() else blocked
        return source.read_text(encoding='utf-8', errors='replace').strip() if source.exists() else ''
    return ''


_STUCK_RE = re.compile(r'tiêu chí kẹt:\s*(.+?)\.\s*Bác sĩ gửi hướng dẫn', re.DOTALL)
_ROUNDS_RE = re.compile(r'\((\d+)\s+vòng\)')


def _script_guidance(path: Path, note: str) -> dict | None:
    """Detect a script that hit the Station 07 cycle cap and now waits for the doctor."""
    if (CYCLE_LIMIT_REASON not in (note or '')
            and 'Trạm 07 cần hướng dẫn:' not in (note or '')):
        return None
    flat = ' '.join(note.split())
    match = _STUCK_RE.search(flat)
    stuck = match.group(1).strip() if match else ''
    count = _ROUNDS_RE.search(flat)
    rounds = int(count.group(1)) if count else 0
    if not stuck or not rounds:
        logs = sorted(path.glob('revisions/*/reviews/script-review-log.yaml'))
        log = _safe_yaml(logs[-1]) if logs else {}
        raw = log.get('rounds') if isinstance(log, dict) else None
        rows = [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []
        rounds = rounds or len(rows)
        scores = rows[-1].get('scores') if rows else None
        if not stuck and isinstance(scores, dict):
            stuck = ', '.join(f'{CRITERIA.get(k, k)} {v}' for k, v in scores.items()
                              if isinstance(v, (int, float)) and v < PASS_SCORE)
    return {'stuck': stuck or 'chưa rõ tiêu chí', 'rounds': rounds}


_HANDLER_ACTIVE_REPAIR_PHASES = frozenset({
    'diagnosing', 'repairing', 'waiting_idle', 'retry_requested', 'cooldown', 'repair_failed',
})


def _first_line(text: object, limit: int = 220) -> str:
    for line in str(text or '').splitlines():
        line = line.strip()
        if line and not line.startswith('log_path:'):
            return line[:limit]
    return ''


def project_handler(
    root: Path,
    slug: str,
    *,
    gate: str | None,
    paused: bool,
    blocked_note: str,
    running_jobs: list[dict],
    producing: bool = False,
    roles: dict[str, str] | None = None,
    doctor_question: dict | None = None,
) -> dict:
    """Who is handling a project right now: ``{label, kind, reason}``.

    kind is one of agent, repair, doctor, paused, blocked, idle. Reads only the
    verified job list plus the project's own log directory.
    """
    roles = roles if roles is not None else _role_names()
    logs_dir = root / 'topics' / 'logs' / slug

    def role_name(role_id: str) -> str:
        return roles.get(role_id) or role_id or 'Agent'

    job = next((j for j in running_jobs if j.get('slug') == slug), None)
    if job is not None:
        step_label = str(job.get('step_label') or '')
        action = step_label[5:].lower() if step_label.startswith('Đang ') else step_label.lower()
        who = role_name(str(job.get('role') or ''))
        return {'label': f'{who} đang {action}' if action else f'{who} đang xử lý',
                'kind': 'agent', 'reason': ''}
    if gate:
        return {'label': 'Chờ bác sĩ', 'kind': 'doctor', 'reason': ''}
    if doctor_question:
        return {
            'label': 'Chờ ý kiến bác sĩ',
            'kind': 'doctor',
            'reason': _first_line(doctor_question.get('question')),
        }
    if paused:
        reason = _first_line(_safe_yaml(logs_dir / 'paused.yaml').get('reason'))
        return {'label': 'Tạm dừng', 'kind': 'paused', 'reason': reason}
    guidance = _script_guidance(root / 'projects' / slug, blocked_note)
    if guidance:
        return {'label': 'Chờ bác sĩ hướng dẫn Biên kịch', 'kind': 'doctor',
                'reason': guidance['stuck']}
    if 'Trạm 12 cần hướng dẫn:' in (blocked_note or ''):
        return {'label': 'Chờ bác sĩ hướng dẫn Thợ dựng', 'kind': 'doctor',
                'reason': _first_line(blocked_note)}
    if ('Storyboard cần hướng dẫn:' in (blocked_note or '')
            or 'Góp ý y khoa chưa có vị trí:' in (blocked_note or '')):
        return {'label': 'Chờ bác sĩ xác định phạm vi sửa', 'kind': 'doctor',
                'reason': _first_line(blocked_note)}
    record = _safe_yaml(logs_dir / 'leader-repair.yaml')
    phase = str(record.get('phase') or '')
    incident = record.get('incident')
    repair_reason = _first_line(incident.get('reason') if isinstance(incident, dict) else '')
    repair_active = phase in {'diagnosing', 'repairing', 'retry_requested'} or (
        bool(blocked_note) and phase in (_HANDLER_ACTIVE_REPAIR_PHASES | {'needs_attention'})
    )
    if repair_active:
        reason = repair_reason or _first_line(blocked_note)
        if phase == 'needs_attention':
            attention = _first_line(record.get('attention_reason'))
            delegation = record.get('delegation')
            if isinstance(delegation, dict) and delegation.get('requires_doctor_reopen'):
                attention = 'Cần bác sĩ mở lại cổng để sửa nội dung.'
            return {'label': 'Leader đã chẩn đoán, chờ xử lý', 'kind': 'repair',
                    'reason': reason or attention}
        if phase == 'repairing':
            return {'label': f'{role_name("repair_engineer")} đang sửa lỗi', 'kind': 'repair',
                    'reason': reason}
        delegation = record.get('delegation')
        if phase == 'retry_requested' and isinstance(delegation, dict) and delegation.get('role'):
            return {'label': f'{role_name(str(delegation["role"]))} đang sửa theo Leader',
                    'kind': 'repair', 'reason': reason}
        return {'label': 'Leader đang điều phối sửa lỗi', 'kind': 'repair', 'reason': reason}
    if blocked_note:
        return {'label': 'Bị chặn', 'kind': 'blocked', 'reason': _first_line(blocked_note)}
    if producing:
        return {'label': f'{role_name("render_machine")} đang dựng', 'kind': 'agent', 'reason': ''}
    waiting = logs_dir / 'waiting-model.txt'
    if waiting.is_file():
        return {'label': 'Chờ model trở lại', 'kind': 'idle', 'reason': ''}
    return {'label': 'Chờ xưởng nhận việc', 'kind': 'idle', 'reason': ''}


def _blocked_step(note: str) -> str | None:
    match = _BLOCKED_STEP_RE.search(note or '')
    if not match:
        return None
    return (match.group(1) or match.group(2) or '').lower() or None


def _project_pending_step(root: Path, path: Path, project: ProjectManifestV2, blocked_note: str) -> str | None:
    """Infer which step a project currently sits at without making external calls."""
    if blocked_note:
        step = _blocked_step(blocked_note)
        if step:
            return step
    state = project.state
    if state is WorkflowState.BLOCKED and project.side_state and project.side_state.resume_state:
        state = project.side_state.resume_state
    if state in {WorkflowState.TOPIC_SELECTED, WorkflowState.RESEARCH_IN_PROGRESS}:
        return 'research'
    if state is WorkflowState.EVIDENCE_READY:
        return 'draft'
    if state is WorkflowState.DRAFT_READY:
        rev = path / 'revisions' / project.active_revision
        if (rev / 'script/script.yaml').is_file() and not (rev / 'storyboard/storyboard.yaml').is_file():
            return 'storyboard_design'
        return 'script_review'
    if state is WorkflowState.NEEDS_MEDICAL_REVISION:
        return 'revise_medical'
    if state is WorkflowState.NEEDS_PRODUCTION_REVISION:
        return 'revise_production'
    if state in {WorkflowState.MEDICALLY_APPROVED, WorkflowState.PRODUCTION_IN_PROGRESS}:
        rev = path / 'revisions' / project.active_revision
        if (rev / 'reviews/visual/candidates.yaml').is_file() and not (rev / 'reviews/visual-review.yaml').is_file():
            return 'visual_review'
        if not (rev / 'posts/posts.yaml').is_file():
            waiting_model = (root / 'topics/logs' / path.name / 'waiting-model.txt').is_file()
            if waiting_model or (rev / 'renders/video.mp4').is_file():
                return 'posts'
        if (rev / 'renders/video.mp4').is_file() and product_review.pending(path):
            try:
                action = product_review.next_product_action(path, root=root, create_question=False)
                return None if action == 'wait_doctor' else action
            except (OSError, ValueError):
                return 'product_review'
        return 'produce'
    return None


def _read_agent_retry_sidecar(path: Path) -> tuple[dict[str, dict], bool]:
    """Read topics/logs/<slug>/agent-retry.yaml defensively; never trust malformed files."""
    if not path.exists():
        return {}, False
    valid_kinds = {'transient', 'validation', 'configuration', 'agent_error'}
    try:
        data = read_yaml(path)
        if not isinstance(data, dict) or data.get('version') != 1:
            return {}, True
        steps = data.get('steps')
        if not isinstance(steps, dict):
            return {}, True
        parsed: dict[str, dict] = {}
        for step, record in steps.items():
            if not isinstance(step, str) or not isinstance(record, dict):
                return {}, True
            fp = record.get('fingerprint')
            kind = record.get('kind')
            attempts = record.get('attempts')
            reason = record.get('reason')
            deadline = record.get('retry_after')
            if (
                not isinstance(fp, str) or not fp.strip()
                or kind not in valid_kinds
                or type(attempts) is not int or attempts < 1
                or not isinstance(reason, str) or not reason.strip()
            ):
                return {}, True
            deadline_dt = None
            if deadline is not None:
                if not isinstance(deadline, str):
                    return {}, True
                deadline_dt = _parse_iso(deadline)
                if deadline_dt is None or datetime.fromisoformat(deadline).tzinfo is None:
                    return {}, True
            parsed[step] = {
                'fingerprint': fp,
                'kind': kind,
                'attempts': attempts,
                'reason': reason,
                'retry_after': deadline,
                'retry_after_dt': deadline_dt,
            }
        return parsed, False
    except (OSError, ValueError, TypeError, OverflowError, yaml.YAMLError):
        return {}, True


def company_roster(
    root: Path,
    *,
    per_role_limit: int = 5,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> dict:
    """Read-only company roster from profiles/company.yaml enriched with verified work state."""
    current_now = _safe_astimezone(now())
    cfg_path = root / 'profiles/company.yaml'
    company = load_company(cfg_path if cfg_path.is_file() else COMPANY_PATH)
    act = activity(root, limit=10_000, now=lambda: current_now)
    quota_book = QuotaBook(root / QUOTA_FILE)
    factory_on = factory.running_pid(root) is not None
    quota_bad = False
    try:
        quota_book.snapshot(current_now)
        # Snapshot validates dates; validate each slot through the same public reader.
        for role_id in company.roles:
            for slot in company.chain(role_id):
                quota_book.resting(slot, current_now)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, yaml.YAMLError):
        quota_bad = True

    running_by_role: dict[str, list[dict]] = {}
    recent_by_role: dict[str, list[dict]] = {}
    for item in act['running']:
        running_by_role.setdefault(str(item.get('role') or ''), []).append(item)
    for item in act['recent']:
        recent_by_role.setdefault(str(item.get('role') or ''), []).append(item)

    # Map per-project state, retry sidecars, waiting-model, and markers without network/CLI calls.
    logs_dir = root / 'topics' / 'logs'
    unverified_scopes: set[str] = set()
    marker_running_by_scope: dict[str, dict] = {}
    markers = sorted([*logs_dir.glob(f'*/{RUNNING_MARKER}'), *logs_dir.glob(f'*/parallel-*/{RUNNING_MARKER}')])
    for marker in markers:
        m_info = _read_agent_marker(marker)
        scope = str(m_info.get('scope') or '')
        if m_info.get('state') == 'unverified':
            unverified_scopes.add(scope)
        elif m_info.get('state') == 'running' and (factory_on or scope in _APP_LIVE_SCOPES):
            marker_running_by_scope[scope] = m_info

    role_waiting_model: dict[str, tuple[str, datetime | None]] = {}
    role_waiting_retry: dict[str, tuple[str, datetime, str]] = {}
    role_errors: dict[str, tuple[str, str]] = {}
    role_unknowns: dict[str, str] = {}
    role_pending_work: dict[str, str] = {}

    if 'chat' in unverified_scopes:
        role_unknowns['coordinator'] = 'Marker chat thiếu định danh tiến trình'
    if 'feedback' in unverified_scopes:
        role_unknowns['feedback_analyst'] = 'Marker phân tích ý kiến thiếu định danh tiến trình'
    if 'researcher' in unverified_scopes or 'channel' in unverified_scopes:
        role_unknowns['researcher'] = 'Marker tìm đề tài/kênh thiếu định danh tiến trình'

    prod_retry_wait: tuple[str, datetime, str] | None = None
    prod_error: tuple[str, str] | None = None
    prod_malformed = False

    step_to_role: dict[str, str] = {}
    for r_id, r_cfg in company.roles.items():
        for s_name in r_cfg.steps:
            step_to_role[s_name] = r_id

    queue_entries: dict[str, QueueEntry] = {}
    try:
        queue_entries = {entry.slug: entry for entry in load_queue(root)}
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        pass

    for path, project in factory.projects(root):
        if project.state in _TERMINAL_STATES:
            continue
        slug = path.name
        note = _blocked_note(root, path, project)
        p_step = _project_pending_step(root, path, project, note)
        owner_role = step_to_role.get(p_step or '')

        a_records, a_bad = _read_agent_retry_sidecar(logs_dir / slug / 'agent-retry.yaml')
        quota_step: str | None = None
        resume_error = False
        resume_unknown_role: str | None = None
        resume_path = logs_dir / slug / 'waiting-model-step.yaml'
        if resume_path.is_file():
            saved_step: object = None
            try:
                resume = read_yaml(resume_path)
                if not isinstance(resume, dict):
                    raise TypeError('Invalid model resume')
                saved_step = resume.get('step')
                saved_fp = resume.get('fingerprint')
                if (
                    resume.get('version') != 1
                    or not isinstance(saved_step, str)
                    or saved_step not in step_to_role
                    or saved_step not in production_retry._AGENT_INPUTS
                    or not isinstance(saved_fp, str)
                    or not saved_fp
                ):
                    raise ValueError('Invalid model resume')
                entry = queue_entries.get(slug)
                brief_context = (
                    json.dumps(
                        {
                            'title': entry.title,
                            'question': entry.question,
                            'doctor_note': entry.doctor_note,
                        },
                        sort_keys=True,
                    )
                    if entry is not None
                    else ''
                )
                expected_fp = production_retry.agent_fingerprint(root, path, saved_step, brief_context)
                if expected_fp == saved_fp:
                    quota_step = saved_step
            except (OSError, ValueError, TypeError, KeyError, AttributeError, yaml.YAMLError):
                resume_error = True
                if isinstance(saved_step, str):
                    resume_unknown_role = step_to_role.get(saved_step)

        # Match runner._run_topic: outstanding agent retry takes precedence over model resume step.
        forced_step = next(iter(a_records)) if a_records else quota_step
        if forced_step is not None:
            p_step = forced_step
            owner_role = step_to_role.get(p_step)

        if slug in unverified_scopes and owner_role:
            role_unknowns.setdefault(owner_role, f'Marker thiếu định danh · {slug}')
        if resume_error:
            unknown_role = resume_unknown_role or owner_role
            if unknown_role:
                role_unknowns.setdefault(unknown_role, f'Hồ sơ chờ model không hợp lệ · {slug}')
        if a_bad and owner_role:
            role_unknowns.setdefault(owner_role, f'Chưa xác minh (agent-retry lỗi · {slug})')

        p_bad = False
        try:
            p_record = production_retry.retry_status(root, path, project.state)
            if p_record['kind'] is None:
                p_record = None
            elif p_record['retry_after']:
                p_record['retry_after_dt'] = _parse_iso(p_record['retry_after'])
        except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, yaml.YAMLError):
            p_record, p_bad = None, True
        if p_bad:
            prod_malformed = True
        elif p_record is not None and p_step == 'produce':
            r_dt = p_record.get('retry_after_dt')
            if p_record['kind'] == 'transient' and r_dt is not None and r_dt > current_now:
                if prod_retry_wait is None or r_dt < prod_retry_wait[1]:
                    prod_retry_wait = (slug, r_dt, p_record['reason'])
            elif p_record['kind'] == 'validation' or p_record['attempts'] >= 3:
                prod_error = prod_error or (slug, p_record['reason'])

        waiting_file = logs_dir / slug / 'waiting-model.txt'
        if waiting_file.is_file() and owner_role:
            until_raw = waiting_file.read_text(encoding='utf-8', errors='replace').strip()
            until_dt = _parse_iso(until_raw)
            chain = company.chain(owner_role)
            chain_exhausted = not quota_bad and bool(chain) and all(quota_book.resting(s, current_now) for s in chain)
            if (until_dt is not None and until_dt > current_now) or (not until_raw and chain_exhausted):
                effective_dt = until_dt or quota_book.earliest_return(chain, current_now)
                role_waiting_model.setdefault(owner_role, (slug, effective_dt))

        if p_step and owner_role:
            step_rec = a_records.get(p_step)
            if step_rec is not None:
                r_dt = step_rec.get('retry_after_dt')
                if step_rec['kind'] == 'transient' and r_dt is not None and r_dt > current_now:
                    existing = role_waiting_retry.get(owner_role)
                    if existing is None or r_dt < existing[1]:
                        role_waiting_retry[owner_role] = (slug, r_dt, step_rec['reason'])
                elif step_rec['kind'] != 'transient' or step_rec['attempts'] >= production_retry.MAX_TRANSIENT_ATTEMPTS:
                    role_errors.setdefault(owner_role, (slug, step_rec['reason']))

        if note:
            if p_step == 'produce':
                prod_error = prod_error or (slug, note)
            elif owner_role and owner_role not in role_waiting_retry:
                role_errors.setdefault(owner_role, (slug, note))
        elif owner_role and (forced_step is not None or project.state not in factory.GATES):
            role_pending_work.setdefault(owner_role, slug)

    prod_running, prod_unverified = _inspect_production_markers(root, now_dt=current_now)
    if prod_running:
        p0 = prod_running[0]
        prod_state = 'working'
        prod_label = f"Đang dựng video · {p0['slug']}"
        prod_detail = p0.get('title') or p0['slug']
        prod_retry_iso = None
    elif prod_unverified or prod_malformed:
        prod_state = 'unknown'
        prod_label = 'Chưa xác minh trạng thái máy dựng'
        prod_detail = (
            prod_unverified[0]['reason']
            if prod_unverified else 'Hồ sơ production-retry.yaml không hợp lệ'
        )
        prod_retry_iso = None
    elif prod_retry_wait is not None:
        slug_w, dt_w, reason_w = prod_retry_wait
        prod_state = 'waiting_retry'
        prod_label = f'Chờ thử lại dựng lúc {_format_hhmm(dt_w)} · {slug_w}'
        prod_detail = reason_w
        prod_retry_iso = dt_w.isoformat()
    elif prod_error is not None:
        slug_e, reason_e = prod_error
        prod_state = 'error'
        prod_label = f'Dừng do lỗi dựng video · {slug_e}'
        prod_detail = reason_e
        prod_retry_iso = None
    else:
        prod_state = 'idle'
        prod_label = 'Đang nghỉ'
        prod_detail = ''
        prod_retry_iso = None

    cap = max(1, int(per_role_limit))
    epoch = datetime.min.replace(tzinfo=UTC)
    roles_payload: list[dict] = []
    for role_id, role in company.roles.items():
        role_running = list(running_by_role.get(role_id, []))
        if not role_running:
            if role_id == 'coordinator' and 'chat' in marker_running_by_scope:
                m_chat = marker_running_by_scope['chat']
                role_running.append({
                    'role': role_id, 'role_name': role.name, 'cli': m_chat['agent'], 'model': '',
                    'slug': 'chung', 'step': 'chat', 'step_label': STEP_LABELS['chat'],
                    'started_at': m_chat['started_at'], 'at': m_chat['started_at'],
                    'duration_s': 0.0, 'running': True,
                })
            elif role_id == 'feedback_analyst' and 'feedback' in marker_running_by_scope:
                m_fb = marker_running_by_scope['feedback']
                role_running.append({
                    'role': role_id, 'role_name': role.name, 'cli': m_fb['agent'], 'model': '',
                    'slug': 'chung', 'step': 'feedback_inbox', 'step_label': STEP_LABELS['feedback_inbox'],
                    'started_at': m_fb['started_at'], 'at': m_fb['started_at'],
                    'duration_s': 0.0, 'running': True, 'job_id': m_fb.get('job_id', ''),
                })
            elif role_id == 'researcher' and 'researcher' in marker_running_by_scope:
                m_res = marker_running_by_scope['researcher']
                role_running.append({
                    'role': role_id, 'role_name': role.name, 'cli': m_res['agent'], 'model': '',
                    'slug': 'chung', 'step': 'topic_research', 'step_label': STEP_LABELS['topic_research'],
                    'started_at': m_res['started_at'], 'at': m_res['started_at'],
                    'duration_s': 0.0, 'running': True, 'job_id': m_res.get('job_id', ''),
                })
            elif role_id == 'researcher' and 'channel' in marker_running_by_scope:
                m_ch = marker_running_by_scope['channel']
                role_running.append({
                    'role': role_id, 'role_name': role.name, 'cli': m_ch['agent'], 'model': '',
                    'slug': 'chung', 'step': 'channel_analytics', 'step_label': STEP_LABELS['channel_analytics'],
                    'started_at': m_ch['started_at'], 'at': m_ch['started_at'],
                    'duration_s': 0.0, 'running': True, 'job_id': m_ch.get('job_id', ''),
                })

        all_recent = sorted(
            recent_by_role.get(role_id, []),
            key=lambda it: _parse_iso(it.get('at')) or epoch,
            reverse=True,
        )
        counts = Counter(
            (str(it.get('cli') or ''), str(it.get('model') or ''))
            for it in [*role_running, *all_recent]
            if it.get('cli') or it.get('model')
        )
        completed_recent = [
            it for it in all_recent
            if not it.get('interrupted') and it.get('event') != 'quota'
        ]
        last_error = bool(completed_recent and completed_recent[0].get('ok') is False)

        chain = company.chain(role_id)
        chain_all_resting = not quota_bad and bool(chain) and all(quota_book.resting(s, current_now) for s in chain)

        work_detail = ''
        retry_after_iso: str | None = None
        resting_until_iso: str | None = None

        if role_running:
            r0 = role_running[0]
            step_lbl = str(r0.get('step_label') or STEP_LABELS.get(str(r0.get('step') or ''), 'Đang làm'))
            slug_lbl = str(r0.get('slug') or '')
            work_state = 'working'
            work_label = (
                f'{step_lbl} · {slug_lbl}'
                if slug_lbl and slug_lbl not in {'chung', 'chat'}
                else step_lbl
            )
            work_detail = f"{r0.get('cli') or ''}/{r0.get('model') or ''}".strip('/')
        elif role_id in role_unknowns or quota_bad:
            work_state = 'unknown'
            work_label = 'Chưa xác minh trạng thái'
            work_detail = role_unknowns.get(role_id, 'Không đọc được trạng thái quota model')
        elif role_id in role_waiting_model or (chain_all_resting and role_id in role_pending_work):
            if role_id in role_waiting_model:
                w_slug, w_dt = role_waiting_model[role_id]
            else:
                w_slug = role_pending_work[role_id]
                w_dt = quota_book.earliest_return(chain, current_now)
            work_state = 'waiting_model'
            when_txt = f' đến {_format_hhmm(w_dt)}' if w_dt else ''
            work_label = f'Chờ model{when_txt} · {w_slug}'
            resting_until_iso = w_dt.isoformat() if w_dt else None
        elif role_id in role_waiting_retry:
            r_slug, r_dt, r_reason = role_waiting_retry[role_id]
            work_state = 'waiting_retry'
            work_label = f'Chờ thử lại lúc {_format_hhmm(r_dt)} · {r_slug}'
            work_detail = r_reason
            retry_after_iso = r_dt.isoformat()
        elif role_id in role_errors:
            work_state = 'error'
            e_slug, e_reason = role_errors[role_id]
            work_label = f'Dừng do lỗi · {e_slug}'
            work_detail = e_reason
        else:
            work_state = 'idle'
            work_label = 'Đang nghỉ'

        roles_payload.append({
            'id': role.id,
            'name': role.name,
            'tier': role.tier,
            'steps': list(role.steps),
            'step_labels': [STEP_LABELS.get(s, s) for s in role.steps],
            'skills': list(role.skills),
            'configured_models': [{'cli': m.cli, 'model': m.model} for m in chain],
            'running': role_running,
            'recent': all_recent[:cap],
            'models_used': [{'cli': c, 'model': m, 'count': n} for (c, m), n in counts.items()],
            'last_error': last_error,
            'work_state': work_state,
            'work_label': work_label,
            'work_detail': work_detail,
            'retry_after': retry_after_iso,
            'resting_until': resting_until_iso,
        })
    return {
        'roles': roles_payload,
        'production_running': prod_running,
        'production': {
            'work_state': prod_state,
            'work_label': prod_label,
            'work_detail': prod_detail,
            'retry_after': prod_retry_iso,
            'running': prod_running,
        },
    }


def _project_preview_url(path: Path, project: ProjectManifestV2) -> str | None:
    rev = path / 'revisions' / project.active_revision
    renders = rev / 'renders'
    if (renders / 'thumbnail.png').is_file():
        return f'/media/{path.name}/thumbnail.png'
    if (rev / 'posts/thumbnail.png').is_file():
        opaque = asset_library._opaque(path.name, project.active_revision, 'posts/thumbnail.png')
        return f'/media/{path.name}/library/{opaque}'
    if (renders / 'review-frames').is_dir():
        sheets = sorted((renders / 'review-frames').glob('*/sheet-*.png'))
        if sheets:
            rel = sheets[0].relative_to(renders).as_posix()
            return f'/media/{path.name}/{rel}'
    return None


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Path):
        return value.as_posix()
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def _safe_yaml(path: Path) -> dict:
    """Read a YAML mapping defensively; return {} on missing, corrupt, or non-dict files."""
    if not path.is_file():
        return {}
    try:
        data = read_yaml(path)
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        return {}
    return _json_safe(data) if isinstance(data, dict) else {}


def _safe_yaml_any(path: Path) -> dict | list:
    """Read a YAML dict or list defensively; return {} on missing or corrupt files."""
    if not path.is_file():
        return {}
    try:
        data = read_yaml(path)
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        return {}
    return _json_safe(data) if isinstance(data, (dict, list)) else {}


def _safe_json(path: Path) -> dict:
    """Read a JSON object defensively; return {} on missing, corrupt, or non-dict files."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8', errors='replace'))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _safe_json_any(path: Path) -> dict | list:
    """Read a JSON dict or list defensively; return {} on missing or corrupt files."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8', errors='replace'))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, (dict, list)) else {}


def _summarize_pronunciation_qa(path: Path) -> dict:
    """Summarize reviews/pronunciation-qa.json for the detail inspector."""
    raw = _safe_json(path)
    if not raw:
        return {}
    flags = raw.get('flags')
    if not isinstance(flags, list):
        flags = [
            item for item in (raw.get('lines') or [])
            if isinstance(item, dict) and (item.get('flagged') or item.get('flags'))
        ]
    return {
        'status': raw.get('status'),
        'blocked': bool(raw.get('blocked')),
        'note': str(raw.get('note') or ''),
        'model_id': str(raw.get('model_id') or ''),
        'checked_count': len(raw.get('lines') or []) if isinstance(raw.get('lines'), list) else 0,
        'flagged': [f for f in flags if isinstance(f, dict)][:30],
    }


def _project_assets_view(root: Path, slug: str) -> list[dict]:
    """List active revision visual/media assets with safe /media/ library URLs."""
    try:
        items = asset_library.list_assets(root, slug=slug)
    except (OSError, ValueError, LookupError, TypeError, yaml.YAMLError):
        return []
    return [
        {**item, 'preview_url': f'/media/{slug}/library/{item["id"]}'}
        for item in items
        if isinstance(item, dict) and item.get('id')
    ]


def _recent_cli_logs(root: Path, slug: str, limit: int = 6) -> list[dict]:
    """Return recent *.log tails under topics/logs/<slug>/ and parallel-*/."""
    log_dir = root / 'topics' / 'logs' / slug
    if not log_dir.is_dir():
        return []
    files = [*log_dir.glob('*.log'), *log_dir.glob('parallel-*/*.log')]
    entries: list[tuple[float, Path]] = []
    for path in files:
        if not path.is_file():
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        entries.append((st.st_mtime, path))
    entries.sort(key=lambda pair: pair[0], reverse=True)
    items: list[dict] = []
    for mtime, path in entries[:limit]:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        items.append({
            'name': path.name,
            'rel_path': path.relative_to(log_dir).as_posix(),
            'updated_at': datetime.fromtimestamp(mtime, tz=UTC).astimezone().isoformat(timespec='seconds'),
            'size_bytes': size,
            'tail': _tail(path, 80),
        })
    return items


def _project_status_line(
    root: Path,
    path: Path,
    project: ProjectManifestV2,
    running_job: dict | None,
    recent_job: dict | None,
    blocked_note: str,
    doctor_question: dict | None = None,
) -> str:
    if running_job is not None:
        step = running_job.get('step_label') or STEP_LABELS.get(str(running_job.get('step') or ''), 'Đang xử lý')
        role = running_job.get('role_name') or running_job.get('role') or 'Agent'
        model = running_job.get('model') or running_job.get('cli') or ''
        return f'{step} · {role} · {model}'.strip(' ·')
    if doctor_question:
        station = str(doctor_question.get('station') or '').strip()
        return f'Chờ ý kiến bác sĩ · Trạm {station}' if station else 'Chờ ý kiến bác sĩ'
    paused_file = root / 'topics/logs' / path.name / 'paused.yaml'
    if paused_file.is_file():
        paused_reason = str(_safe_yaml(paused_file).get('reason') or '').strip()
        return f'Đã tạm dừng · {paused_reason}' if paused_reason else 'Đã tạm dừng tự động'
    waiting_file = root / 'topics/logs' / path.name / 'waiting-model.txt'
    if waiting_file.is_file():
        until_raw = waiting_file.read_text(encoding='utf-8', errors='replace').strip()
        until_dt = _parse_iso(until_raw)
        when = _format_hhmm(until_dt) if until_dt else until_raw
        return f'Chờ model trở lại ({when})'
    if blocked_note:
        return f'Bị chặn · {STAGES[stage_index(project)].lower()}'
    label = STATE_LABELS.get(project.state, project.state.value)
    if recent_job is not None and project.state not in factory.GATES:
        role = recent_job.get('role_name') or recent_job.get('role') or ''
        model = recent_job.get('model') or ''
        if role and model:
            return f'{label} · {role} · {model}'
    return label


def _gate_card_with_style(project_dir: Path) -> dict | None:
    """Attach Station 12 PYH style score to the video gate card when available."""
    card_data = decision_card.card(project_dir)
    if card_data is None or card_data.get('gate') != 'video':
        return card_data
    rev = project_dir / 'revisions' / card_data['revision']
    style = product_review.style_score(rev)
    if style is None:
        return card_data
    return {**card_data, 'style_score': style}


def _project_repair_summary(root: Path, slug: str, roles: dict[str, str]) -> dict | None:
    record = _safe_yaml(root / 'topics' / 'logs' / slug / 'leader-repair.yaml')
    if not record:
        return None
    phase = str(record.get('phase') or '')
    blocked_exists = (
        (root / 'topics' / 'logs' / slug / 'blocked.txt').is_file()
        or (root / 'projects' / slug / 'blocked-reason.md').is_file()
    )
    if not blocked_exists and phase not in {'diagnosing', 'repairing', 'retry_requested', 'waiting_idle'}:
        return None
    attempts = record.get('attempts') if isinstance(record.get('attempts'), int) else 0
    diag = record.get('diagnosis') if isinstance(record.get('diagnosis'), dict) else {}
    delegation = record.get('delegation') if isinstance(record.get('delegation'), dict) else {}
    if phase == 'repairing':
        who = roles.get('repair_engineer') or 'Kỹ sư sửa lỗi'
    elif phase in {'diagnosing', 'waiting_idle'}:
        who = roles.get('coordinator_senior') or 'Trưởng nhóm'
    elif phase == 'retry_requested' and delegation.get('role'):
        role_id = str(delegation['role'])
        who = roles.get(role_id) or role_id
    elif phase == 'needs_attention':
        who = 'Chờ bác sĩ'
    else:
        who = roles.get('coordinator_senior') or 'Trưởng nhóm'
    detail = str(
        diag.get('cause')
        or delegation.get('brief')
        or record.get('attention_reason')
        or record.get('error')
        or ''
    )
    return {
        'phase': phase,
        'attempts': attempts,
        'who': who,
        'detail': detail,
        'attention_reason': str(record.get('attention_reason') or ''),
        'error': str(record.get('error') or ''),
    }


def _project_retry_after(
    root: Path,
    path: Path,
    state: WorkflowState,
    current_now: datetime,
) -> str | None:
    deadlines: list[datetime] = []
    try:
        p_rec = production_retry.retry_status(root, path, state)
        p_dt = _parse_iso(p_rec.get('retry_after')) if isinstance(p_rec, dict) else None
        if p_dt is not None and p_dt > current_now:
            deadlines.append(p_dt)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, yaml.YAMLError):
        pass
    logs_dir = root / 'topics' / 'logs' / path.name
    a_records, _ = _read_agent_retry_sidecar(logs_dir / 'agent-retry.yaml')
    for rec in a_records.values():
        r_dt = rec.get('retry_after_dt')
        if r_dt is not None and r_dt > current_now:
            deadlines.append(r_dt)
    repair_rec = _safe_yaml(logs_dir / 'leader-repair.yaml')
    if repair_rec.get('phase') in {'cooldown', 'repair_failed'}:
        rep_dt = _parse_iso(repair_rec.get('retry_after'))
        if rep_dt is not None and rep_dt > current_now:
            deadlines.append(rep_dt)
    return min(deadlines).isoformat() if deadlines else None


def overview(
    root: Path,
    *,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> dict:
    """Company overview payload for the home page: KPI tiles, decision strip, projects, resting models."""
    codes = project_codes(root)
    current_now = _safe_astimezone(now())
    act = activity(root, limit=30, now=lambda: current_now)
    running_by_slug = {str(item.get('slug')): item for item in act['running'] if item.get('slug')}
    recent_by_slug: dict[str, dict] = {}
    for item in act['recent']:
        slug_key = str(item.get('slug') or '')
        if slug_key and slug_key not in recent_by_slug:
            recent_by_slug[slug_key] = item
    resting, _ = _safe_quota_snapshot(root, current_now)
    queue_dates: dict[str, datetime] = {}
    try:
        for entry in load_queue(root):
            queue_dates[entry.slug] = _safe_astimezone(datetime.combine(entry.added, datetime.min.time()))
    except (OSError, ValueError, TypeError, OverflowError, yaml.YAMLError):
        pass

    logs = root / 'topics' / 'logs'
    factory_on = factory.running_pid(root) is not None
    prod_by_slug = {
        str(item.get('slug')): item
        for item in production_running(root, now=lambda: current_now)
        if item.get('slug')
    }
    verified_jobs = _active_running_jobs(root)
    role_names = _role_names()
    decisions: list[dict] = []
    project_cards: list[dict] = []
    done_states = {WorkflowState.VIDEO_APPROVED, WorkflowState.PACKAGED, WorkflowState.PUBLISHED_MANUAL}
    running_count = 0
    done_7d = 0
    done_30d = 0
    lead_days: list[float] = []

    for path, project in factory.projects(root):
        note = _blocked_note(root, path, project)
        open_q = doctor_questions.open_question(root, path.name)
        current_card = _gate_card_with_style(path)
        title = factory.project_title(path, project)
        if current_card is not None:
            row = {
                'slug': path.name,
                'code': codes[path.name],
                'title': title,
                'gate': current_card['gate'],
                'count': len(current_card['decisions']),
                'revision': project.active_revision,
            }
            if current_card.get('style_score') is not None:
                row['style_score'] = current_card['style_score']
            decisions.append(row)
        if open_q is not None and current_card is None:
            decisions.append({
                'kind': 'doctor_question',
                'slug': path.name,
                'code': codes[path.name],
                'title': title,
                'gate': None,
                'count': len(open_q.get('options') or []),
                'revision': project.active_revision,
                'station': str(open_q.get('station') or ''),
                'question_id': str(open_q.get('id') or ''),
                'question': str(open_q.get('question') or ''),
            })
        guidance = _script_guidance(path, note)
        if (('Storyboard cần hướng dẫn:' in (note or '')
             or 'Góp ý y khoa chưa có vị trí:' in (note or '')) and current_card is None):
            storyboard = 'Storyboard cần hướng dẫn:' in note
            decisions.append({
                'kind': 'product_guidance', 'slug': path.name, 'code': codes[path.name],
                'title': title, 'gate': None, 'count': 0, 'revision': project.active_revision,
                'message': 'Cần bác sĩ xác định phạm vi sửa', 'stuck': note, 'rounds': 0,
                'role': 'Đạo diễn phân cảnh' if storyboard else 'Biên kịch',
                'view': 'storyboard' if storyboard else 'script',
            })
        if 'Trạm 12 cần hướng dẫn:' in (note or '') and current_card is None:
            decisions.append({
                'kind': 'product_guidance', 'slug': path.name, 'code': codes[path.name],
                'title': title, 'gate': None, 'count': 0, 'revision': project.active_revision,
                'message': 'Trạm 12 cần hướng dẫn: cùng issue kẹt hai vòng',
                'stuck': note, 'rounds': 2,
            })
        if guidance and current_card is None and not factory.gate_for_project(path, project):
            decisions.append({
                'kind': 'script_guidance',
                'slug': path.name,
                'code': codes[path.name],
                'title': title,
                'gate': None,
                'count': 0,
                'revision': project.active_revision,
                'message': ('Trạm 07 cần hướng dẫn: cùng issue kẹt hai vòng'
                            if 'Trạm 07 cần hướng dẫn:' in note else CYCLE_LIMIT_REASON),
                'stuck': guidance['stuck'],
                'rounds': guidance['rounds'],
            })
        marker_info = _read_agent_marker(logs / path.name / RUNNING_MARKER)
        marker_live = factory_on and marker_info.get('state') == 'running'
        is_running = (
            path.name in running_by_slug
            or path.name in prod_by_slug
            or marker_live
        )
        if is_running:
            running_count += 1
        manifest_file = path / 'project.yaml'
        mtime_dt = _safe_mtime(manifest_file, current_now)
        if project.state in done_states:
            rev = path / 'revisions' / project.active_revision
            approval_file = rev / 'reviews/video-approval.yaml'
            done_dt = mtime_dt
            if approval_file.is_file():
                try:
                    approval = read_yaml(approval_file)
                    reviewed_at = approval.get('reviewed_at') if isinstance(approval, dict) else None
                    done_dt = _parse_iso(reviewed_at) or mtime_dt
                except (OSError, ValueError, TypeError, yaml.YAMLError):
                    done_dt = mtime_dt
            age_days = max(0.0, (current_now - done_dt).total_seconds() / 86400.0)
            if age_days <= 7.0:
                done_7d += 1
            if age_days <= 30.0:
                done_30d += 1
            start_dt = queue_dates.get(path.name)
            if start_dt is None:
                first_card = path / 'revisions/001/topic/card.yaml'
                if first_card.is_file():
                    start_dt = _safe_mtime_optional(first_card)
            if start_dt is not None and done_dt >= start_dt:
                lead_days.append((done_dt - start_dt).total_seconds() / 86400.0)

        is_paused = (logs / path.name / 'paused.yaml').is_file()
        rev_dir = path / 'revisions' / project.active_revision
        claims_raw = _safe_yaml(rev_dir / 'evidence/ledger.yaml').get('claims')
        lines_raw = _safe_yaml(rev_dir / 'script/script.yaml').get('lines')
        scenes_raw = _safe_yaml(rev_dir / 'storyboard/storyboard.yaml').get('scenes')
        counts = {
            'claims': len(claims_raw) if isinstance(claims_raw, list) else 0,
            'lines': len(lines_raw) if isinstance(lines_raw, list) else 0,
            'scenes': len(scenes_raw) if isinstance(scenes_raw, list) else 0,
            'has_brief': (rev_dir / 'evidence/expert-brief.md').is_file(),
            'has_video': (rev_dir / 'renders/video.mp4').is_file(),
            'has_posts': (rev_dir / 'posts/posts.yaml').is_file(),
        }
        label = STATE_LABELS.get(project.state, project.state.value)
        state_label = (
            'Chờ ý kiến bác sĩ'
            if open_q is not None and current_card is None
            else f'Tạm dừng · {STAGES[stage_index(project)].lower()}'
            if is_paused and current_card is None
            else f'Bị chặn · {STAGES[stage_index(project)].lower()}'
            if note
            else label
        )
        project_cards.append({
            'slug': path.name,
            'code': codes[path.name],
            'title': title,
            'stage_index': stage_index(project),
            'stage': stage_index(project),
            'state': project.state.value,
            'state_label': state_label,
            'gate': factory.gate_for_project(path, project),
            'revision': project.active_revision,
            'blocked': note,
            'doctor_question': open_q,
            'paused': is_paused,
            'is_running': is_running,
            'in_queue': path.name in queue_dates,
            'repair': _project_repair_summary(root, path.name, role_names),
            'retry_after': _project_retry_after(root, path, project.state, current_now),
            'counts': counts,
            'preview_url': _project_preview_url(path, project),
            'status_line': _project_status_line(
                root, path, project,
                running_by_slug.get(path.name),
                recent_by_slug.get(path.name),
                note,
                doctor_question=open_q,
            ),
            'handler': project_handler(
                root, path.name,
                gate=factory.gate_for_project(path, project),
                paused=is_paused and current_card is None,
                blocked_note=note,
                running_jobs=verified_jobs,
                producing=path.name in prod_by_slug,
                roles=role_names,
                doctor_question=open_q,
            ),
            'updated_at': mtime_dt.isoformat(timespec='seconds'),
        })

    from healthvideo.workflows import auto_publish
    publication_work = auto_publish.overview(root)
    avg_days = round(sum(lead_days) / len(lead_days), 1) if lead_days else 0.0
    return {
        'tiles': {
            'running': running_count,
            'waiting_doctor': len(decisions),
            'done_7d': done_7d,
            'done_30d': done_30d,
            'avg_days_topic_to_video': avg_days,
            'models_resting': len(resting),
        },
        'decisions': decisions,
        'auto_publish': publication_work,
        'projects': project_cards,
        'resting': resting,
        'channel': channel_analytics.channel_overview_payload(root),
        'inbox': researcher.inbox_summary(root),
        'running_jobs': verified_jobs,
    }


def timeline(project_dir: Path) -> list[dict]:
    """Scene timeline from the active revision's render-input.json with open change flags."""
    project = ProjectManifestV2.model_validate(read_yaml(project_dir / 'project.yaml'))
    rev = project_dir / 'revisions' / project.active_revision
    render_input = rev / 'renders/render-input.json'
    if not render_input.is_file():
        return []
    try:
        data = read_yaml(render_input)
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    fps = float(data.get('fps') or 30)
    open_scenes: set[str] = set()
    open_briefs: list[str] = []
    changes_dir = rev / 'reviews/changes'
    if changes_dir.is_dir():
        for req_path in sorted(changes_dir.glob('*-requested.yaml')):
            try:
                req = read_yaml(req_path)
            except (OSError, ValueError):
                continue
            if isinstance(req, dict) and not req.get('applied', False):
                ctx = req.get('context')
                if isinstance(ctx, dict) and ctx.get('scene'):
                    open_scenes.add(str(ctx['scene']))
                if req.get('brief'):
                    open_briefs.append(str(req['brief']))
    rows: list[dict] = []
    for scene in data.get('scenes', []):
        if not isinstance(scene, dict):
            continue
        scene_id = str(scene.get('id') or scene.get('scene') or '')
        if 'start_s' in scene and 'end_s' in scene:
            start_s = round(float(scene['start_s']), 2)
            end_s = round(float(scene['end_s']), 2)
        else:
            start_frame = int(scene.get('start_frame', 0))
            duration_frames = int(scene.get('duration_frames', 0))
            start_s = round(start_frame / fps, 2)
            end_s = round((start_frame + duration_frames) / fps, 2)
        is_open = bool(
            scene_id and (
                scene_id in open_scenes
                or any(re.search(rf'\b{re.escape(scene_id)}\b', brief) for brief in open_briefs)
            )
        )
        rows.append({
            'scene': scene_id,
            'start_s': start_s,
            'end_s': end_s,
            'open_change': is_open,
        })
    return rows


def snapshot(root: Path, *, agents: Callable[[], list[str]] | None = None) -> dict:
    """Plain-JSON factory view, assigning stable display codes when first seen."""
    codes = project_codes(root)
    now_dt = _safe_astimezone(datetime.now(UTC))
    logs = root / 'topics' / 'logs'
    items = []
    verified_jobs = _active_running_jobs(root)
    role_names = _role_names()
    for path, project in factory.projects(root):
        blocked = logs / path.name / 'blocked.txt'
        reason = path / 'blocked-reason.md'
        note = ''
        if project.state is WorkflowState.BLOCKED or blocked.exists():
            source = reason if reason.exists() else blocked
            note = source.read_text(encoding='utf-8', errors='replace').strip() if source.exists() else ''
        manifest = path / 'project.yaml'
        gate = factory.gate_for_project(path, project)
        open_q = doctor_questions.open_question(root, path.name)
        is_paused = (logs / path.name / 'paused.yaml').is_file()
        label = STATE_LABELS.get(project.state, project.state.value)
        state_label = (
            'Chờ ý kiến bác sĩ'
            if open_q is not None and not gate
            else f'Tạm dừng · {STAGES[stage_index(project)].lower()}'
            if is_paused and not gate
            else f'Bị chặn · {STAGES[stage_index(project)].lower()}'
            if note
            else label
        )
        items.append({
            'slug': path.name,
            'code': codes[path.name],
            'title': factory.project_title(path, project),
            'state': project.state.value,
            'state_label': state_label,
            'stage': stage_index(project),
            'gate': gate,
            'blocked': note,
            'doctor_question': open_q,
            'paused': is_paused,
            'handler': project_handler(
                root, path.name, gate=gate, paused=is_paused and not gate, blocked_note=note,
                running_jobs=verified_jobs, roles=role_names, doctor_question=open_q,
            ),
            'revision': project.active_revision,
            'comments': len(load_draft(root, path.name)),
            'updated_at': _safe_mtime(manifest, now_dt).isoformat(timespec='seconds'),
        })
    from healthvideo.workflows import telegram_bot

    pid = factory.running_pid(root)
    return {
        'app': APP_ID,
        'factory': {'running': pid is not None, 'pid': pid},
        'xuong': {'running': pid is not None, 'pid': pid},
        'telegram': telegram_bot.bot_status(root),
        'agents': agents() if agents is not None else running_agents(root),
        'stages': list(STAGES),
        'projects': items,
        'waiting': sum(1 for item in items if item['gate']),
        'reviewer': reviewer_name(),
        'pin_set': pin_path().is_file(),
        'standards': len(standards.load(root)),
        'resume_options': {kind.value: [label for _, label in options]
                           for kind, options in RESUME_TARGETS.items()},
        'log': _tail(logs / 'xuong.log', LOG_TAIL),
        'now': now_dt.isoformat(timespec='seconds'),
    }


# ---------- in-app review: products, draft comments, media ----------

MEDIA_TYPES = {'.mp4': 'video/mp4', '.wav': 'audio/wav', '.mp3': 'audio/mpeg',
               '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
_REVIEW_SHEET_EXTS = frozenset({'.jpg', '.jpeg', '.png', '.webp'})
_WORD_TOK_RE = re.compile(r'\w+')
_SCENE_AT_RE = re.compile(r'\b(S\d+)\b', re.IGNORECASE)
_TIME_AT_RE = re.compile(r'(\d{1,2}):(\d{2})(?::(\d{2}))?')


def _safe_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return default


def _normalize_tokens(text: object) -> list[str]:
    return _WORD_TOK_RE.findall(str(text or '').casefold())


def _resolve_beat_frame(
    beat: dict,
    words: list[dict],
    narration: str,
    duration_frames: int,
    fps: float,
) -> int | None:
    raw_sf = beat.get('start_frame')
    if raw_sf is not None and not isinstance(raw_sf, bool):
        frame = _safe_int(raw_sf, -1)
        if frame >= 0:
            return min(frame, duration_frames - 1) if duration_frames > 0 else frame
    at = beat.get('at')
    if isinstance(at, (int, float)) and not isinstance(at, bool):
        frame = max(0, round(float(at) * fps))
        return min(frame, duration_frames - 1) if duration_frames > 0 else frame
    if isinstance(at, str) and at.strip():
        wanted = _normalize_tokens(at)
        if wanted:
            if words:
                indexed: list[tuple[str, int]] = []
                for w in words:
                    wsf = _safe_int(w.get('start_frame'), 0)
                    for tok in _normalize_tokens(w.get('text')):
                        indexed.append((tok, wsf))
                for i in range(len(indexed) - len(wanted) + 1):
                    if [t for t, _ in indexed[i:i + len(wanted)]] == wanted:
                        frame = indexed[i][1]
                        return min(frame, duration_frames - 1) if duration_frames > 0 else frame
            raw_words = str(narration or '').split()
            if raw_words:
                indexed_nar: list[tuple[str, int]] = []
                total_w = len(raw_words)
                for idx_w, rw in enumerate(raw_words):
                    est = round(idx_w * duration_frames / total_w) if duration_frames > 0 else 0
                    for tok in _normalize_tokens(rw):
                        indexed_nar.append((tok, est))
                for i in range(len(indexed_nar) - len(wanted) + 1):
                    if [t for t, _ in indexed_nar[i:i + len(wanted)]] == wanted:
                        frame = indexed_nar[i][1]
                        return min(frame, duration_frames - 1) if duration_frames > 0 else frame
    return None


def _parse_marker_at(
    at_raw: object,
    fps: float,
    scene_by_id: dict[str, dict],
    scenes: list[dict],
) -> tuple[str | None, int | None]:
    text = str(at_raw or '').strip()
    if not text:
        return None, None
    scene_id: str | None = None
    sc_match = _SCENE_AT_RE.search(text)
    if sc_match:
        cand = sc_match.group(1).upper()
        if cand in scene_by_id:
            scene_id = cand
        else:
            for key in scene_by_id:
                if key.upper() == cand:
                    scene_id = key
                    break
            if scene_id is None:
                scene_id = cand
    t_match = _TIME_AT_RE.search(text)
    if t_match:
        if t_match.group(3) is not None:
            sec = int(t_match.group(1)) * 3600 + int(t_match.group(2)) * 60 + int(t_match.group(3))
        else:
            sec = int(t_match.group(1)) * 60 + int(t_match.group(2))
        frame = max(0, round(sec * fps))
        if scene_id is None:
            for sc in scenes:
                if sc['start_frame'] <= frame < sc['end_frame']:
                    scene_id = sc['id']
                    break
        return scene_id, frame
    if scene_id is not None and scene_id in scene_by_id:
        return scene_id, scene_by_id[scene_id]['start_frame']
    return scene_id, None


def _frame_inspector_payload(
    rev: Path,
    slug: str,
    timeline_rows: list[dict],
    product_rev: dict | None,
    pron_qa: dict,
) -> dict:
    """Build frame-accurate multi-track NLE payload from render artifacts or storyboard fallback."""
    render_input = _safe_json(rev / 'renders/render-input.json')
    scene_timing = _safe_json(rev / 'renders/scene-timing.json')
    render_manifest = _safe_json(rev / 'renders/render-manifest.json')
    final_sheets = _safe_yaml(rev / 'reviews/visual/final-contact-sheets.yaml')
    storyboard = _safe_yaml(rev / 'storyboard/storyboard.yaml')

    raw_fps = render_input.get('fps') or scene_timing.get('fps') or 30
    try:
        fps_val = float(raw_fps)
        if fps_val <= 0:
            fps_val = 30.0
    except (ValueError, TypeError):
        fps_val = 30.0
    fps: int | float = int(fps_val) if fps_val.is_integer() else fps_val

    format_profile = str(
        render_input.get('format_profile')
        or storyboard.get('format_profile')
        or ''
    )

    timing_by_scene: dict[str, dict] = {}
    raw_timing_scenes = scene_timing.get('scenes')
    if isinstance(raw_timing_scenes, list):
        for row in raw_timing_scenes:
            if isinstance(row, dict):
                sid = str(row.get('scene_id') or row.get('id') or '')
                if sid:
                    timing_by_scene[sid] = row

    open_change_map: dict[str, bool] = {}
    for row in timeline_rows:
        if isinstance(row, dict) and row.get('scene'):
            open_change_map[str(row['scene'])] = bool(row.get('open_change'))

    open_briefs: dict[str, str] = {}
    open_unscoped_briefs: list[str] = []
    changes_dir = rev / 'reviews/changes'
    if changes_dir.is_dir():
        for req_path in sorted(changes_dir.glob('*-requested.yaml')):
            req = _safe_yaml(req_path)
            if req and not req.get('applied', False):
                ctx = req.get('context') if isinstance(req.get('context'), dict) else {}
                brief = str(req.get('brief') or '').strip()
                if ctx.get('scene'):
                    sc_key = str(ctx['scene'])
                    open_change_map[sc_key] = True
                    if brief and sc_key not in open_briefs:
                        open_briefs[sc_key] = brief
                elif brief:
                    open_unscoped_briefs.append(brief)

    ri_scenes = render_input.get('scenes')
    sb_scenes = storyboard.get('scenes')
    using_render_input = isinstance(ri_scenes, list) and len(ri_scenes) > 0
    source_scenes = ri_scenes if using_render_input else (sb_scenes if isinstance(sb_scenes, list) else [])

    scenes_out: list[dict] = []
    scene_by_id: dict[str, dict] = {}
    line_first_scene: dict[str, dict] = {}
    cursor_frame = 0

    for idx, raw_sc in enumerate(source_scenes):
        if not isinstance(raw_sc, dict):
            continue
        sc_id = str(raw_sc.get('id') or raw_sc.get('scene') or raw_sc.get('scene_id') or f'S{idx + 1:02d}')
        t_row = timing_by_scene.get(sc_id, {})

        if using_render_input:
            start_frame = _safe_int(raw_sc.get('start_frame'), cursor_frame)
            dur_frames = _safe_int(raw_sc.get('duration_frames'), 0)
        else:
            start_frame = _safe_int(
                t_row.get('start_frame') if t_row.get('start_frame') is not None else raw_sc.get('start_frame'),
                cursor_frame,
            )
            dur_raw = (
                t_row.get('duration_frames')
                if t_row.get('duration_frames') is not None
                else raw_sc.get('duration_frames')
            )
            if dur_raw is not None:
                dur_frames = _safe_int(dur_raw, 0)
            elif raw_sc.get('expected_duration_seconds') is not None:
                try:
                    dur_frames = round(float(raw_sc['expected_duration_seconds']) * fps_val)
                except (ValueError, TypeError):
                    dur_frames = 0
            else:
                dur_frames = 0

        start_frame = max(0, start_frame)
        dur_frames = max(0, dur_frames)
        end_frame = start_frame + dur_frames
        cursor_frame = end_frame

        raw_audio_ms = t_row.get('audio_ms') if t_row.get('audio_ms') is not None else raw_sc.get('audio_ms')
        audio_ms = _safe_int(raw_audio_ms, 0) if raw_audio_ms is not None else None

        narration = str(raw_sc.get('narration') or '')
        words_raw = raw_sc.get('words')
        words_out = [
            {
                'text': str(w.get('text') or ''),
                'start_frame': max(0, _safe_int(w.get('start_frame'), 0)),
                'end_frame': max(0, _safe_int(w.get('end_frame'), 0)),
            }
            for w in (words_raw if isinstance(words_raw, list) else [])
            if isinstance(w, dict) and str(w.get('text') or '').strip()
        ]

        beats_raw = raw_sc.get('beats')
        beats_out: list[dict] = []
        for b_item in (beats_raw if isinstance(beats_raw, list) else []):
            if not isinstance(b_item, dict):
                continue
            rel_frame = _resolve_beat_frame(b_item, words_out, narration, dur_frames, fps_val)
            beats_out.append({
                'at': b_item.get('at'),
                'start_frame': rel_frame,
                'abs_frame': (start_frame + rel_frame) if rel_frame is not None else None,
                'focus': b_item.get('focus'),
                'labels': list(b_item.get('labels') or []) if isinstance(b_item.get('labels'), list) else [],
                'action': b_item.get('action'),
            })

        entrances_raw = raw_sc.get('entrances')
        entrances_out: list[dict] = []
        for ent in (entrances_raw if isinstance(entrances_raw, list) else []):
            if not isinstance(ent, dict):
                continue
            ent_sf = max(0, _safe_int(ent.get('start_frame'), 0))
            entrances_out.append({
                'text': str(ent.get('text') or ''),
                'start_frame': ent_sf,
                'abs_frame': start_frame + ent_sf,
            })

        assets_raw = raw_sc.get('visual_assets')
        assets_out = [
            _json_safe(a)
            for a in (assets_raw if isinstance(assets_raw, list) else [])
            if isinstance(a, dict)
        ]

        mascot_pose = raw_sc.get('mascot_pose')
        if mascot_pose is None:
            for a in assets_out:
                if isinstance(a, dict) and a.get('role') == 'mascot' and a.get('pose'):
                    mascot_pose = a.get('pose')
                    break

        is_open = bool(
            open_change_map.get(sc_id, False)
            or any(re.search(rf'\b{re.escape(sc_id)}\b', br) for br in open_unscoped_briefs)
        )
        if is_open and sc_id not in open_briefs:
            for br in open_unscoped_briefs:
                if re.search(rf'\b{re.escape(sc_id)}\b', br):
                    open_briefs[sc_id] = br
                    break

        line_id = raw_sc.get('script_line_id') or raw_sc.get('script_line')
        anatomy = _json_safe(raw_sc.get('anatomy')) if isinstance(raw_sc.get('anatomy'), dict) else None
        motion = _json_safe(raw_sc.get('motion')) if isinstance(raw_sc.get('motion'), dict) else None

        sc_entry = {
            'id': sc_id,
            'index': len(scenes_out),
            'start_frame': start_frame,
            'end_frame': end_frame,
            'duration_frames': dur_frames,
            'start_s': round(start_frame / fps_val, 3),
            'end_s': round(end_frame / fps_val, 3),
            'audio_ms': audio_ms,
            'visual': str(raw_sc.get('visual') or ''),
            'script_line_id': str(line_id) if line_id is not None else None,
            'claim_id': str(raw_sc['claim_id']) if raw_sc.get('claim_id') is not None else None,
            'chapter_id': str(raw_sc['chapter_id']) if raw_sc.get('chapter_id') is not None else None,
            'source_marker': str(raw_sc['source_marker']) if raw_sc.get('source_marker') is not None else None,
            'on_screen_text': str(raw_sc.get('on_screen_text') or ''),
            'narration': narration,
            'mascot_pose': str(mascot_pose) if mascot_pose is not None else None,
            'anatomy': anatomy,
            'motion': motion,
            'beats': beats_out,
            'entrances': entrances_out,
            'words': words_out,
            'assets': assets_out,
            'open_change': is_open,
        }
        scenes_out.append(sc_entry)
        scene_by_id[sc_id] = sc_entry
        if sc_entry['script_line_id'] and sc_entry['script_line_id'] not in line_first_scene:
            line_first_scene[sc_entry['script_line_id']] = sc_entry

    total_frames = max((s['end_frame'] for s in scenes_out), default=0)
    duration_s = round(total_frames / fps_val, 3)

    raw_sfx = render_manifest.get('sfx')
    if not isinstance(raw_sfx, list):
        sfx_file = _safe_json_any(rev / 'renders/sfx.json')
        raw_sfx = sfx_file if isinstance(sfx_file, list) else []
    sfx_out: list[dict] = []
    for ev in raw_sfx:
        if not isinstance(ev, dict):
            continue
        ev_scene = str(ev.get('scene') or '')
        ev_time = ev.get('time')
        ev_at = ev.get('at')
        ev_frame: int | None = None
        if isinstance(ev_time, (int, float)) and not isinstance(ev_time, bool):
            ev_frame = max(0, round(float(ev_time) * fps_val))
        elif ev_scene in scene_by_id and isinstance(ev_at, (int, float)) and not isinstance(ev_at, bool):
            ev_frame = max(0, scene_by_id[ev_scene]['start_frame'] + round(float(ev_at) * fps_val))
        sfx_out.append({
            'id': str(ev.get('id') or ''),
            'scene': ev_scene,
            'at': ev_at,
            'time': float(ev_time) if isinstance(ev_time, (int, float)) and not isinstance(ev_time, bool) else None,
            'frame': ev_frame,
            'volume': ev.get('volume'),
        })

    markers: list[dict] = []
    if isinstance(product_rev, dict):
        for issue in (product_rev.get('issues') or []):
            if not isinstance(issue, dict):
                continue
            at_val = issue.get('at') or issue.get('line') or ''
            sc_id, m_frame = _parse_marker_at(at_val, fps_val, scene_by_id, scenes_out)
            if m_frame is not None and total_frames > 0:
                m_frame = min(m_frame, max(0, total_frames - 1))
            fixable = bool(issue.get('fixable', True))
            blocking = bool(issue.get('blocking_safety', False))
            markers.append({
                'kind': 'issue',
                'source': 'product_review',
                'frame': m_frame,
                'scene': sc_id,
                'at': str(at_val),
                'criterion': str(issue.get('criterion') or ''),
                'label': f'{at_val} · {issue.get("criterion") or ""}'.strip(' ·'),
                'detail': str(issue.get('problem') or ''),
                'fix': str(issue.get('fix') or ''),
                'fixable': fixable,
                'severity': 'error' if (blocking or not fixable) else 'warn',
            })

    if isinstance(pron_qa, dict):
        for flag in (pron_qa.get('flagged') or []):
            if not isinstance(flag, dict):
                continue
            line_id = str(flag.get('line') or '')
            base_sc = line_first_scene.get(line_id)
            m_frame: int | None = None
            sc_id: str | None = None
            if base_sc is not None:
                sc_id = base_sc['id']
                start_offset = flag.get('start')
                offset_frames = (
                    round(float(start_offset) * fps_val)
                    if isinstance(start_offset, (int, float)) and not isinstance(start_offset, bool)
                    else 0
                )
                m_frame = max(0, base_sc['start_frame'] + offset_frames)
                if total_frames > 0:
                    m_frame = min(m_frame, max(0, total_frames - 1))
            sw = str(flag.get('script_word') or '')
            heard = str(flag.get('heard') or '')
            markers.append({
                'kind': 'pronunciation',
                'source': 'pronunciation_qa',
                'frame': m_frame,
                'scene': sc_id,
                'line': line_id,
                'label': f'{line_id}: {sw} → {heard}'.strip(' :→'),
                'detail': str(flag.get('suggestion') or ''),
                'severity': 'warn',
            })

    for sc in scenes_out:
        if sc['open_change']:
            markers.append({
                'kind': 'open_change',
                'source': 'change_request',
                'frame': sc['start_frame'],
                'scene': sc['id'],
                'label': f"{sc['id']} · Đang sửa",
                'detail': open_briefs.get(sc['id'], 'Có yêu cầu sửa đang chờ xử lý'),
                'severity': 'info',
            })

    markers.sort(key=lambda m: (m['frame'] is None, m['frame'] or 0))

    raw_sheets = final_sheets.get('sheets') if isinstance(final_sheets.get('sheets'), list) else []
    sample_frames = [
        int(f) for f in (final_sheets.get('sample_frames') or [])
        if isinstance(f, int) and not isinstance(f, bool) and f >= 0
    ]
    sheets_out: list[dict] = []
    for idx_sh, item in enumerate(raw_sheets):
        raw_path = item.get('path') if isinstance(item, dict) else (item if isinstance(item, str) else '')
        name = Path(str(raw_path or '')).name
        if (not name or '/' in name or '\\' in name or '..' in name
                or Path(name).suffix.lower() not in _REVIEW_SHEET_EXTS):
            continue
        sheets_out.append({
            'name': name,
            'url': f'/media/{slug}/review-sheet/{name}',
            'sample_frames': sample_frames[idx_sh * 25:(idx_sh + 1) * 25],
        })

    return {
        'fps': fps,
        'total_frames': total_frames,
        'duration_s': duration_s,
        'format_profile': format_profile,
        'scenes': scenes_out,
        'sfx': sfx_out,
        'markers': markers,
        'contact_sheets': {
            'sheets': sheets_out,
            'sample_frames': sample_frames,
        },
    }


def _draft_path(root: Path, slug: str) -> Path:
    return root / 'topics' / 'logs' / slug / 'review-draft.yaml'


def load_draft(root: Path, slug: str) -> list[dict]:
    path = _draft_path(root, slug)
    if not path.is_file():
        return []
    items = read_yaml(path).get('items', [])
    return [i for i in items if isinstance(i, dict) and str(i.get('text', '')).strip()] if isinstance(items, list) else []


def save_comment(root: Path, slug: str, target: str, text: str) -> int:
    """Upsert one draft comment for a target (line/claim id or 'chung'); empty text deletes."""
    target = target.strip()[:40] or 'chung'
    items = [i for i in load_draft(root, slug) if i.get('target') != target]
    if text.strip():
        items.append({'target': target, 'text': text.strip()[:4000]})
    write_yaml_atomic(_draft_path(root, slug), {'items': items})
    return len(items)


def clear_draft(root: Path, slug: str) -> None:
    _draft_path(root, slug).unlink(missing_ok=True)


def _read_text(path: Path, limit: int = 20_000) -> str:
    return path.read_text(encoding='utf-8', errors='replace')[:limit] if path.is_file() else ''


def _fast_list_len(path: Path, key: str) -> int:
    data = _safe_yaml(path)
    items = data.get(key)
    return len(items) if isinstance(items, list) else 0


def review_bundle(
    root: Path,
    project_dir: Path,
    project: ProjectManifestV2,
    *,
    lite: bool = False,
    tab: str | None = None,
) -> dict:
    """Everything the doctor needs to inspect or accept a topic, read straight from the active revision."""
    rev = project_dir / 'revisions' / project.active_revision
    logs_dir = root / 'topics' / 'logs' / project_dir.name

    def _collect_media() -> list[dict]:
        items: list[dict] = []
        renders = rev / 'renders'
        for rel, label in (('video.mp4', 'Video hoàn chỉnh'), ('audio/narration-voice.wav', 'Giọng đọc')):
            if (renders / rel).is_file():
                items.append({'label': label, 'url': f'/media/{project_dir.name}/{rel}', 'kind': rel.rsplit('.', 1)[1]})
        for clip in sorted((renders / 'clips').glob('*.mp4')) if renders.is_dir() else []:
            items.append({'label': f'Clip {clip.stem}', 'url': f'/media/{project_dir.name}/clips/{clip.name}', 'kind': 'mp4'})
        return items

    if tab:
        if tab == 'sources':
            ledger = _safe_yaml(rev / 'evidence/ledger.yaml')
            raw_claims = ledger.get('claims')
            claims = [{
                'id': c.get('id'), 'text': c.get('text_public', ''), 'type': c.get('type'),
                'sources': c.get('sources', []), 'applicability': c.get('applicability', ''),
                'technical': c.get('text_technical', ''),
                'support': [{'source_id': s.get('source_id'), 'locator': s.get('locator'), 'quote': s.get('quote')}
                            for s in (c.get('support') if isinstance(c.get('support'), list) else [])
                            if isinstance(s, dict)],
            } for c in (raw_claims if isinstance(raw_claims, list) else []) if isinstance(c, dict)]
            raw_records = ledger.get('records')
            records = [{
                'id': r.get('id'), 'title': r.get('title'), 'year': r.get('year'), 'journal': r.get('journal'),
                'doi': r.get('doi'), 'pmid': r.get('pmid'), 'url': r.get('url'),
            } for r in (raw_records if isinstance(raw_records, list) else []) if isinstance(r, dict)]
            return {
                'tab': 'sources',
                'claims': claims,
                'records': records,
                'expert_brief': _safe_yaml(rev / 'evidence/expert-brief.yaml'),
                'expert_brief_md': _read_text(rev / 'evidence/expert-brief.md', limit=40_000),
                'research_meta': {
                    'question': _safe_yaml(rev / 'evidence/question.yaml'),
                    'search_log': _safe_yaml_any(rev / 'evidence/search-log.yaml'),
                    'included_sources': _safe_yaml_any(rev / 'evidence/included-sources.yaml'),
                    'excluded_sources': _safe_yaml_any(rev / 'evidence/excluded-sources.yaml'),
                },
            }
        if tab == 'script':
            script = _safe_yaml(rev / 'script/script.yaml')
            voice_prep = _safe_yaml(rev / 'script/voice-prep.yaml')
            vp_lines: dict[str, dict | str] = {}
            if isinstance(voice_prep.get('lines'), list):
                for vp in voice_prep['lines']:
                    if isinstance(vp, dict) and vp.get('id'):
                        vp_lines[str(vp['id'])] = vp.get('delivery') or vp
            raw_lines = script.get('lines')
            lines = [{
                'id': line.get('id'), 'text': line.get('text', ''), 'purpose': line.get('purpose'),
                'claim_id': line.get('claim_id'), 'source_marker': line.get('source_marker'),
                'delivery': line.get('delivery') or vp_lines.get(str(line.get('id') or ''), ''),
            } for line in (raw_lines if isinstance(raw_lines, list) else []) if isinstance(line, dict)]
            return {
                'tab': 'script',
                'lines': lines,
                'outline': _safe_yaml(rev / 'script/outline.yaml'),
                'voice_prep': voice_prep,
                'style_lint': _safe_json(rev / 'reviews/style-lint.json'),
                'script_review': review_view(rev),
                'script_review_rounds': _safe_yaml_any(rev / 'reviews/script-review-log.yaml'),
            }
        if tab == 'storyboard':
            return {
                'tab': 'storyboard',
                'storyboard': _safe_yaml(rev / 'storyboard/storyboard.yaml'),
                'clip_plan': _safe_yaml(rev / 'script/clip-plan.yaml') or _safe_yaml(rev / 'storyboard/clip-plan.yaml'),
                'visual_review': _safe_yaml(rev / 'reviews/visual-review.yaml'),
                'assets': _project_assets_view(root, project_dir.name),
            }
        if tab == 'video':
            qa = _safe_json(rev / 'reviews/video-qa.json')
            tl_rows = timeline(project_dir)
            prod_rev = product_review.review_view(rev)
            pron_qa = _summarize_pronunciation_qa(rev / 'reviews/pronunciation-qa.json')
            frame_insp = _frame_inspector_payload(rev, project_dir.name, tl_rows, prod_rev, pron_qa)
            raw_rounds = _safe_yaml_any(rev / 'reviews/product-review-log.yaml')
            rounds_list = raw_rounds if isinstance(raw_rounds, list) else (
                raw_rounds.get('rounds', []) if isinstance(raw_rounds, dict) else []
            )
            compact_rounds = [
                {'round': r.get('round'), 'passed': r.get('passed'), 'summary': str(r.get('summary') or '')[:300]}
                for r in rounds_list if isinstance(r, dict)
            ]
            return {
                'tab': 'video',
                'media': _collect_media(),
                'thumbnail_url': _project_preview_url(project_dir, project),
                'timeline': tl_rows,
                'frame_inspector': frame_insp,
                'product_review': prod_rev,
                'product_review_rounds': compact_rounds,
                'qa': {'status': qa.get('status'),
                       'warnings': [*(qa.get('warnings') or []), *(qa.get('errors') or [])]},
                'qa_detail': {'video_qa': qa, 'pronunciation_qa': pron_qa},
            }
        if tab == 'posts':
            return {
                'tab': 'posts',
                'thumbnail_url': _project_preview_url(project_dir, project),
                'posts': _safe_yaml(rev / 'posts/posts.yaml'),
                'shorts_plan': _safe_yaml(rev / 'posts/shorts-plan.yaml'),
            }
        if tab == 'log':
            return {
                'tab': 'log',
                'activity': activity(root, limit=50, slug=project_dir.name)['items'],
                'repair': _safe_yaml(logs_dir / 'leader-repair.yaml'),
                'cli_logs': _recent_cli_logs(root, project_dir.name),
                'notes': _read_text(rev / 'reviews/medical-revision-notes.md'),
                'feedback': [e for e in standards.load(root) if e.get('slug') == project_dir.name][::-1],
            }

    is_paused = (logs_dir / 'paused.yaml').is_file()
    paused_info = _safe_yaml(logs_dir / 'paused.yaml') if is_paused else {}
    media = _collect_media()
    queue_entry: dict | None = None
    try:
        for item in load_queue(root):
            if item.slug == project_dir.name:
                queue_entry = item.model_dump(mode='json')
                break
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        queue_entry = None

    revs_dir = project_dir / 'revisions'
    revisions = (
        sorted(p.name for p in revs_dir.iterdir() if p.is_dir() and not p.name.startswith('.'))
        if revs_dir.is_dir() else [project.active_revision]
    )
    gate = factory.gate_for_project(project_dir, project)
    open_q = doctor_questions.open_question(root, project_dir.name)
    blocked = _blocked_note(root, project_dir, project)
    label = STATE_LABELS.get(project.state, project.state.value)
    state_label = (
        'Chờ ý kiến bác sĩ'
        if open_q is not None and not gate
        else f'Tạm dừng · {STAGES[stage_index(project)].lower()}'
        if is_paused and not gate
        else f'Bị chặn · {STAGES[stage_index(project)].lower()}'
        if blocked
        else label
    )

    if lite:
        posts_data = _safe_yaml(rev / 'posts/posts.yaml')
        shorts_data = _safe_yaml(rev / 'posts/shorts-plan.yaml')
        posts_count = len(posts_data.get('youtube_titles') or []) + len(shorts_data.get('clips') or [])
        claims_count = _fast_list_len(rev / 'evidence/ledger.yaml', 'claims')
        lines_count = _fast_list_len(rev / 'script/script.yaml', 'lines')
        scenes_count = _fast_list_len(rev / 'storyboard/storyboard.yaml', 'scenes')
        return {
            'lite': True,
            'slug': project_dir.name, 'title': factory.project_title(project_dir, project),
            'code': project_codes(root)[project_dir.name],
            'state': project.state.value, 'state_label': state_label,
            'gate': gate, 'revision': project.active_revision,
            'paused': is_paused, 'paused_info': paused_info, 'blocked': blocked,
            'doctor_question': open_q,
            'stage_index': stage_index(project), 'stages': list(STAGES), 'revisions': revisions,
            'topic_card': _safe_yaml(rev / 'topic/card.yaml'),
            'dossier': _safe_yaml(rev / 'topic/dossier.yaml'),
            'queue_entry': queue_entry,
            'counts': {
                'claims': claims_count,
                'lines': lines_count,
                'scenes': scenes_count,
                'media': len(media),
                'posts': posts_count,
            },
            'lines': [], 'claims': [], 'records': [], 'media': media, 'frames': [],
            'storyboard': {}, 'posts': {}, 'shorts_plan': {}, 'timeline': [], 'frame_inspector': None,
            'thumbnail_url': _project_preview_url(project_dir, project),
            'card': _gate_card_with_style(project_dir),
            'video_stale': project.state in {WorkflowState.MEDICALLY_APPROVED, WorkflowState.PRODUCTION_IN_PROGRESS,
                                             WorkflowState.AWAITING_MEDICAL_REVIEW, WorkflowState.DRAFT_READY},
            'approvals': {
                'medical': _safe_yaml(rev / 'reviews/medical-approval.yaml'),
                'video': _safe_yaml(rev / 'reviews/video-approval.yaml'),
            },
            'running_jobs': [j for j in _active_running_jobs(root) if j.get('slug') == project_dir.name],
            'draft': load_draft(root, project_dir.name),
            'activity': [], 'cli_logs': [], 'feedback': [],
        }

    script = _safe_yaml(rev / 'script/script.yaml')
    ledger = _safe_yaml(rev / 'evidence/ledger.yaml')
    voice_prep = _safe_yaml(rev / 'script/voice-prep.yaml')
    vp_lines: dict[str, dict | str] = {}
    if isinstance(voice_prep.get('lines'), list):
        for vp in voice_prep['lines']:
            if isinstance(vp, dict) and vp.get('id'):
                vp_lines[str(vp['id'])] = vp.get('delivery') or vp

    raw_lines = script.get('lines')
    lines = [{
        'id': line.get('id'), 'text': line.get('text', ''), 'purpose': line.get('purpose'),
        'claim_id': line.get('claim_id'), 'source_marker': line.get('source_marker'),
        'delivery': line.get('delivery') or vp_lines.get(str(line.get('id') or ''), ''),
    } for line in (raw_lines if isinstance(raw_lines, list) else []) if isinstance(line, dict)]

    raw_claims = ledger.get('claims')
    claims = [{
        'id': c.get('id'), 'text': c.get('text_public', ''), 'type': c.get('type'),
        'sources': c.get('sources', []), 'applicability': c.get('applicability', ''),
        'technical': c.get('text_technical', ''),
        'support': [{'source_id': s.get('source_id'), 'locator': s.get('locator'), 'quote': s.get('quote')}
                    for s in (c.get('support') if isinstance(c.get('support'), list) else [])
                    if isinstance(s, dict)],
    } for c in (raw_claims if isinstance(raw_claims, list) else []) if isinstance(c, dict)]

    raw_records = ledger.get('records')
    records = [{
        'id': r.get('id'), 'title': r.get('title'), 'year': r.get('year'), 'journal': r.get('journal'),
        'doi': r.get('doi'), 'pmid': r.get('pmid'), 'url': r.get('url'),
    } for r in (raw_records if isinstance(raw_records, list) else []) if isinstance(r, dict)]

    renders = rev / 'renders'
    frames = []
    if (renders / 'frames').is_dir():
        for frame in sorted((renders / 'frames').glob('*.png')):
            frames.append({'name': frame.name, 'url': f'/media/{project_dir.name}/frames/{frame.name}'})

    expert_brief = _safe_yaml(rev / 'evidence/expert-brief.yaml')
    expert_brief_md = _read_text(rev / 'evidence/expert-brief.md', limit=40_000)
    storyboard = _safe_yaml(rev / 'storyboard/storyboard.yaml')
    qa = _safe_json(rev / 'reviews/video-qa.json')

    tl_rows = timeline(project_dir)
    prod_rev = product_review.review_view(rev)
    pron_qa = _summarize_pronunciation_qa(rev / 'reviews/pronunciation-qa.json')
    frame_insp = _frame_inspector_payload(rev, project_dir.name, tl_rows, prod_rev, pron_qa)
    return {
        'slug': project_dir.name, 'title': factory.project_title(project_dir, project),
        'code': project_codes(root)[project_dir.name],
        'state': project.state.value, 'state_label': state_label,
        'gate': gate, 'revision': project.active_revision,
        'paused': is_paused, 'paused_info': paused_info, 'blocked': blocked,
        'doctor_question': open_q,
        'stage_index': stage_index(project), 'stages': list(STAGES), 'revisions': revisions,
        'topic_card': _safe_yaml(rev / 'topic/card.yaml'),
        'dossier': _safe_yaml(rev / 'topic/dossier.yaml'),
        'queue_entry': queue_entry,
        'lines': lines, 'claims': claims, 'records': records, 'media': media,
        'frames': frames, 'expert_brief': expert_brief, 'expert_brief_md': expert_brief_md,
        'research_meta': {
            'question': _safe_yaml(rev / 'evidence/question.yaml'),
            'search_log': _safe_yaml_any(rev / 'evidence/search-log.yaml'),
            'included_sources': _safe_yaml_any(rev / 'evidence/included-sources.yaml'),
            'excluded_sources': _safe_yaml_any(rev / 'evidence/excluded-sources.yaml'),
        },
        'storyboard': storyboard,
        'outline': _safe_yaml(rev / 'script/outline.yaml'),
        'clip_plan': _safe_yaml(rev / 'script/clip-plan.yaml') or _safe_yaml(rev / 'storyboard/clip-plan.yaml'),
        'voice_prep': voice_prep,
        'style_lint': _safe_json(rev / 'reviews/style-lint.json'),
        'script_review_rounds': _safe_yaml_any(rev / 'reviews/script-review-log.yaml'),
        'product_review_rounds': _safe_yaml_any(rev / 'reviews/product-review-log.yaml'),
        'visual_review': _safe_yaml(rev / 'reviews/visual-review.yaml'),
        'assets': _project_assets_view(root, project_dir.name),
        'posts': _safe_yaml(rev / 'posts/posts.yaml'),
        'shorts_plan': _safe_yaml(rev / 'posts/shorts-plan.yaml'),
        'thumbnail_url': _project_preview_url(project_dir, project),
        'timeline': tl_rows,
        'frame_inspector': frame_insp,
        'card': _gate_card_with_style(project_dir),
        'activity': activity(root, limit=50, slug=project_dir.name)['items'],
        'script_review': review_view(rev),
        'product_review': prod_rev,
        'video_stale': project.state in {WorkflowState.MEDICALLY_APPROVED, WorkflowState.PRODUCTION_IN_PROGRESS,
                                         WorkflowState.AWAITING_MEDICAL_REVIEW, WorkflowState.DRAFT_READY},
        'notes': _read_text(rev / 'reviews/medical-revision-notes.md'),
        'qa': {'status': qa.get('status'),
               'warnings': [*(qa.get('warnings') or []), *(qa.get('errors') or [])]},
        'qa_detail': {
            'video_qa': qa,
            'pronunciation_qa': pron_qa,
        },
        'approvals': {
            'medical': _safe_yaml(rev / 'reviews/medical-approval.yaml'),
            'video': _safe_yaml(rev / 'reviews/video-approval.yaml'),
        },
        'running_jobs': [j for j in _active_running_jobs(root) if j.get('slug') == project_dir.name],
        'repair': _safe_yaml(logs_dir / 'leader-repair.yaml'),
        'cli_logs': _recent_cli_logs(root, project_dir.name),
        'draft': load_draft(root, project_dir.name),
        'feedback': [e for e in standards.load(root) if e.get('slug') == project_dir.name][::-1],
    }


def media_file(project_dir: Path, project: ProjectManifestV2, rel: str) -> Path:
    """Resolve a render file inside the active revision's renders dir, or raise LookupError."""
    renders = (project_dir / 'revisions' / project.active_revision / 'renders').resolve()
    target = (renders / rel).resolve()
    if (not renders.is_relative_to(project_dir.resolve()) or renders not in target.parents
            or target.suffix.lower() not in MEDIA_TYPES or not target.is_file()):
        raise LookupError('Không có file này')
    return target


def review_sheet_file(project_dir: Path, project: ProjectManifestV2, filename: str) -> Path:
    """Resolve a visual review contact sheet inside revisions/<active>/reviews/visual."""
    if (not filename or '/' in filename or '\\' in filename or '..' in filename
            or Path(filename).name != filename):
        raise LookupError('Không có file này')
    proj_root = project_dir.resolve()
    rev = (project_dir / 'revisions' / project.active_revision).resolve()
    if not rev.is_relative_to(proj_root):
        raise LookupError('Không có file này')
    visual_dir = (rev / 'reviews/visual').resolve()
    target = (visual_dir / filename).resolve()
    if (not visual_dir.is_relative_to(rev)
            or not target.is_relative_to(visual_dir)
            or target.parent != visual_dir
            or target.suffix.lower() not in _REVIEW_SHEET_EXTS
            or not target.is_file()):
        raise LookupError('Không có file này')
    return target


def _operator_config() -> Path:
    return pin_path().parent / 'operator.yaml'


def reviewer_name() -> str:
    config = _operator_config()
    return str(read_yaml(config).get('reviewer', '')).strip() if config.exists() else ''


class PinLimiter:
    """In-memory lockout after repeated wrong PINs."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.failures = 0
        self.locked_until = 0.0
        self.lock = threading.Lock()

    def check(self, pin: str, verify: Callable[[str], bool]) -> None:
        with self.lock:
            remaining = self.locked_until - self.clock()
            if remaining > 0:
                raise PermissionError(f'Sai PIN quá nhiều lần; thử lại sau {int(remaining // 60) + 1} phút.')
            if verify(pin):
                self.failures = 0
                return
            self.failures += 1
            if self.failures >= MAX_PIN_FAILURES:
                self.failures = 0
                self.locked_until = self.clock() + LOCKOUT_SECONDS
                raise PermissionError('Sai PIN quá nhiều lần; app khóa duyệt 10 phút.')
            raise PermissionError(f'PIN không đúng (còn {MAX_PIN_FAILURES - self.failures} lần thử).')


def medanim_catalog_payload(root: Path) -> dict:
    """List reusable medical animations and doctor PIN/reviewer readiness."""
    items = medanim_library.list_medanim_library(root)
    counts = Counter(str(item.get('status') or 'invalid') for item in items)
    return {
        'items': items,
        'total': len(items),
        'approved_count': counts.get('approved', 0),
        'pending_count': counts.get('pending', 0),
        'needs_reapproval_count': counts.get('needs_reapproval', 0),
        'rejected_count': counts.get('rejected', 0),
        'invalid_count': counts.get('invalid', 0),
        'pin_set': pin_path().is_file(),
        'reviewer': reviewer_name(),
    }


def medanim_decide(
    root: Path,
    anim_id: str,
    action: str,
    body: dict,
    *,
    limiter: PinLimiter,
    verify: Callable[[str], bool] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> dict:
    """Approve or reject a medical animation library entry after PIN verification."""
    if action not in {'approve', 'reject'}:
        raise LookupError('Không có thao tác này')
    reviewer = reviewer_name() or str(body.get('reviewer', '')).strip()
    if not reviewer:
        raise ValueError('Nhập tên bác sĩ duyệt.')
    reason = str(body.get('reason', '')).strip()
    if action == 'reject' and not reason:
        raise ValueError('Nhập lý do từ chối hoặc yêu cầu sửa.')
    pin_file = pin_path()
    if not pin_file.is_file():
        raise ValueError('Chưa đặt PIN; chạy healthvideo review set-pin một lần.')
    pin = str(body.get('pin', ''))
    limiter.check(pin, verify or (lambda value: verify_pin(value, path=pin_file)))
    if not _operator_config().exists():
        write_yaml_atomic(_operator_config(), {'reviewer': reviewer})
    if action == 'approve':
        record = medanim_library.approve_medanim_entry(
            root,
            anim_id,
            reviewer=reviewer,
            pin=pin,
            note=str(body.get('note', '')),
            pin_file=pin_file,
            now=now(),
        )
        return {
            'approval': record.model_dump(mode='json'),
            'message': f'Đã duyệt hoạt cảnh {anim_id}.',
        }
    record = medanim_library.reject_medanim_entry(
        root,
        anim_id,
        reviewer=reviewer,
        reason=reason,
        pin=pin,
        pin_file=pin_file,
        now=now(),
    )
    return {
        'rejection': record.model_dump(mode='json'),
        'message': f'Đã từ chối hoạt cảnh {anim_id}.',
    }


def decide(root: Path, project_dir: Path, body: dict, *, limiter: PinLimiter,
           verify: Callable[[str], bool] | None = None,
           now: Callable[[], datetime] = lambda: datetime.now().astimezone()) -> str:
    """Apply one gate decision after PIN check; mirrors `healthvideo duyet`."""
    project = ProjectManifestV2.model_validate(read_yaml(project_dir / 'project.yaml'))
    if project.state not in factory.GATES:
        raise ValueError('Project này không ở cổng duyệt.')
    if str(body.get('revision', '')) != project.active_revision:
        raise ValueError('Revision đã thay đổi kể từ lúc mở; tải lại trang và xem lại gói duyệt.')
    gate = GateKind(factory.GATES[project.state])
    action = str(body.get('action', ''))
    if action not in {'approve', 'approve_pronunciation', 'reject', 'card'}:
        raise ValueError('Thiếu lựa chọn duyệt/từ chối.')
    if action == 'approve_pronunciation' and gate is not GateKind.VIDEO:
        raise ValueError('Chấp nhận phát âm chỉ dùng ở cổng video.')
    reviewer = reviewer_name() or str(body.get('reviewer', '')).strip()
    if not reviewer:
        raise ValueError('Nhập tên bác sĩ duyệt.')
    draft = load_draft(root, project_dir.name)
    reason = standards.compose_reason(str(body.get('reason', '')), draft)
    if action == 'reject' and not reason:
        raise ValueError('Nhập lý do từ chối hoặc góp ý vào từng dòng.')
    pin_file = pin_path()
    if not pin_file.is_file():
        raise ValueError('Chưa đặt PIN; chạy healthvideo review set-pin một lần.')
    pin = str(body.get('pin', ''))
    limiter.check(pin, verify or (lambda value: verify_pin(value, path=pin_file)))
    card_note = None
    card_fix = False
    if action == 'card':
        current_card = decision_card.card(project_dir)
        if current_card is None:
            raise ValueError('Project này không ở cổng duyệt.')
        result, card_note = decision_card.compose(
            current_card, body.get('choices', {}), body.get('other', ''))
        card_fix = result == 'send_fix'
        action = 'reject' if card_fix else 'approve'
        reason = standards.compose_reason(card_note, draft) if card_fix else reason
    if not _operator_config().exists():
        write_yaml_atomic(_operator_config(), {'reviewer': reviewer})
    if action == 'reject':
        options = RESUME_TARGETS[gate]
        choice = 1 if card_fix else int(body.get('resume', 1))
        if choice not in range(1, len(options) + 1):
            raise ValueError('Nơi làm lại không hợp lệ.')
        reject_gate(project_dir, gate, reviewer=reviewer, reason=reason,
                    resume_state=options[choice - 1][0], now=now(),
                    reason_code='semantic_issue' if gate is GateKind.VIDEO and choice == 2 else None)
        if card_fix:
            decision_card.remember_fix(project_dir / 'revisions' / project.active_revision,
                                       gate.value, body.get('choices', {}), body.get('other', ''))
        message = f'Đã từ chối cổng {gate.value}; xưởng sẽ sửa theo lý do.'
    else:
        pronunciation = action == 'approve_pronunciation'
        approve_gate(project_dir, gate, reviewer=reviewer,
                     note=standards.compose_reason(
                         card_note if card_note is not None else str(body.get('note', '')), draft),
                     accept_pronunciation=pronunciation,
                     pronunciation_pin=pin if pronunciation else None,
                     pin_file=pin_file, now=now())
        message = f'Đã duyệt cổng {gate.value}.'
    clear_draft(root, project_dir.name)
    if draft or reason:
        message += ' Góp ý đã được ghi nhớ làm chuẩn.'
    if factory.running_pid(root) is None:
        factory.start_background(root)
        message += ' Đã bật xưởng để chạy tiếp.'
    return message


def _console_python() -> str:
    exe = Path(sys.executable)
    console = exe.with_name('python.exe')
    return str(console if exe.name.lower() == 'pythonw.exe' and console.exists() else exe)


def _child_env() -> dict[str, str]:
    env = child_env()
    src = str(Path(__file__).resolve().parents[2])
    paths = [src, *(p for p in env.get('PYTHONPATH', '').split(os.pathsep) if p)]
    env['PYTHONPATH'] = os.pathsep.join(dict.fromkeys(paths))
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


_REVIEW_SCRIPT = (
    'import sys\n'
    'from healthvideo.cli import app\n'
    'try:\n'
    '    app(["duyet", "--root", sys.argv[1]])\n'
    'except SystemExit:\n'
    '    pass\n'
    'input("\\nNhấn Enter để đóng cửa sổ này...")\n'
)


def open_review_console(root: Path, *, popen: Callable[..., object] = subprocess.Popen) -> None:
    """Open a visible console running `duyet`, so the PIN is typed in the doctor's TTY."""
    flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
    popen([_console_python(), '-c', _REVIEW_SCRIPT, str(root.resolve())],
          cwd=root.resolve(), env=_child_env(), shell=False, creationflags=flags)


def _open_path(path: Path) -> None:
    if sys.platform == 'win32':
        os.startfile(str(path.resolve()))
    else:
        webbrowser.open(path.resolve().as_uri())


class _Handler(BaseHTTPRequestHandler):
    server: DashboardServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _host_ok(self) -> bool:
        port = self.server.server_address[1]
        return self.headers.get('Host', '') in {f'127.0.0.1:{port}', f'localhost:{port}'}

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict | list | None, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                   'application/json; charset=utf-8')

    def do_GET(self) -> None:
        if not self._host_ok():
            self._json({'error': 'host'}, HTTPStatus.FORBIDDEN)
            return
        path = unquote(self.path.split('?', 1)[0])
        parts = [p for p in path.split('/') if p]
        query = parse_qs(urlsplit(self.path).query)
        try:
            extra = dashboard_operations.get_route(self.server, parts, query)
            if extra is not None:
                if isinstance(extra, bytes):
                    self._send(HTTPStatus.OK, extra, 'image/png')
                else:
                    self._json(extra)
                return
            if path in {'/', '/index.html'}:
                self._send(HTTPStatus.OK, self.server.html_bytes(), 'text/html; charset=utf-8')
            elif path == '/api/ping':
                self._json({'app': APP_ID})
            elif path == '/api/poll':
                self._json({
                    'status': self.server.cached_state(),
                    'overview': self.server.cached_overview(),
                    'activity': self.server.cached_activity(limit=10, slug=None),
                    'company': self.server.cached_company(),
                })
            elif path == '/api/version':
                self._json(
                    app_update.version_payload(
                        self.server.running_version,
                        repo_dir=self.server.repo_dir,
                    )
                )
            elif path in {'/api/status', '/api/state'}:
                self._json(self.server.cached_state())
            elif path == '/api/overview':
                self._json(self.server.cached_overview())
            elif path == '/api/company':
                self._json(self.server.cached_company())
            elif path == '/api/progress':
                self._json(progress(self.server.root))
            elif path == '/api/activity':
                try:
                    limit = max(1, min(200, int(query.get('limit', ['10'])[0])))
                except ValueError:
                    limit = 10
                slug_filter = query.get('slug', [None])[0] or None
                self._json(self.server.cached_activity(limit=limit, slug=slug_filter))
            elif path == '/api/feedback':
                self._json({'entries': feedback_inbox.view(self.server.root)})
            elif path == '/api/standards':
                self._json({'entries': standards.load(self.server.root)[::-1]})
            elif path == '/api/medanim':
                self._json(self.server.cached_medanim())
            elif len(parts) >= 5 and parts[:2] == ['api', 'medanim'] and parts[3] == 'preview':
                self._file(medanim_library.resolve_medanim_preview(self.server.root, parts[2], '/'.join(parts[4:])))
            elif len(parts) == 4 and parts[0] == 'api' and parts[1] in {'project', 'projects'} and parts[3] == 'card':
                project_dir, _ = self.server.project_dir(parts[2])
                self._json(_gate_card_with_style(project_dir))
            elif len(parts) == 4 and parts[0] == 'api' and parts[1] in {'project', 'projects'} and parts[3] == 'timeline':
                project_dir, _ = self.server.project_dir(parts[2])
                self._json(timeline(project_dir))
            elif len(parts) == 4 and parts[:2] == ['api', 'project'] and parts[3] == 'bundle':
                project_dir, project = self.server.project_dir(parts[2])
                lite_flag = query.get('lite', [''])[0] in {'1', 'true', 'yes'}
                tab_name = (query.get('tab', [''])[0] or '').strip() or None
                self._json(review_bundle(self.server.root, project_dir, project, lite=lite_flag, tab=tab_name))
            elif len(parts) >= 4 and parts[0] == 'media' and parts[2] == 'review-sheet':
                project_dir, project = self.server.project_dir(parts[1])
                self._file(review_sheet_file(project_dir, project, '/'.join(parts[3:])))
            elif len(parts) >= 3 and parts[0] == 'media':
                project_dir, project = self.server.project_dir(parts[1])
                self._file(media_file(project_dir, project, '/'.join(parts[2:])))
            else:
                self._json({'error': 'not found'}, HTTPStatus.NOT_FOUND)
        except LookupError as error:
            self._json({'error': str(error)}, HTTPStatus.NOT_FOUND)
        except (OSError, ValueError) as error:
            self._json({'error': f'{type(error).__name__}: {error}'}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_HEAD(self) -> None:
        if not self._host_ok():
            self.send_response(HTTPStatus.FORBIDDEN)
            self.end_headers()
            return
        path = unquote(self.path.split('?', 1)[0])
        parts = [p for p in path.split('/') if p]
        try:
            if len(parts) >= 5 and parts[:2] == ['api', 'medanim'] and parts[3] == 'preview':
                self._file(medanim_library.resolve_medanim_preview(self.server.root, parts[2], '/'.join(parts[4:])), head_only=True)
            elif len(parts) >= 4 and parts[0] == 'media' and parts[2] == 'review-sheet':
                project_dir, project = self.server.project_dir(parts[1])
                self._file(review_sheet_file(project_dir, project, '/'.join(parts[3:])), head_only=True)
            elif len(parts) >= 3 and parts[0] == 'media':
                project_dir, project = self.server.project_dir(parts[1])
                self._file(media_file(project_dir, project, '/'.join(parts[2:])), head_only=True)
            else:
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
        except (LookupError, OSError, ValueError):
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

    def _file(self, target: Path, *, head_only: bool = False) -> None:
        """Stream a render file, honouring a single `bytes=` Range so video can seek."""
        size = target.stat().st_size
        start, end = 0, size - 1
        status = HTTPStatus.OK
        max_open_chunk = 4 * 1024 * 1024  # 4 MiB cap on open-ended Range so 100 MB MP4 seeks stay snappy
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', self.headers.get('Range', '').strip())
        if match and size and (match[1] or match[2]):
            if match[1]:
                start = int(match[1])
                if match[2]:
                    end = min(int(match[2]), size - 1)
                else:
                    end = min(start + max_open_chunk - 1, size - 1)
            else:
                start = max(0, size - int(match[2]))
            if start > end or start >= size:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            status = HTTPStatus.PARTIAL_CONTENT
        length = end - start + 1 if size else 0
        self.send_response(status)
        self.send_header('Content-Type', MEDIA_TYPES[target.suffix.lower()])
        self.send_header('Content-Length', str(length))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if status is HTTPStatus.PARTIAL_CONTENT:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        if head_only:
            return
        with target.open('rb') as stream:
            stream.seek(start)
            remaining = length
            try:
                while remaining > 0:
                    chunk = stream.read(min(256_000, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return

    def do_POST(self) -> None:
        if not self._host_ok() or not secrets.compare_digest(
                self.headers.get('X-Dashboard-Token', ''), self.server.token):
            self._json({'error': 'forbidden'}, HTTPStatus.FORBIDDEN)
            return
        parts = [p for p in self.path.split('/') if p]
        try:
            length = int(self.headers.get('Content-Length') or 0)
            max_body = 512_000 if parts == ['api', 'channel', 'import-csv'] else MAX_BODY
            if length < 0 or length > max_body:
                raise ValueError('Yêu cầu quá lớn.')
            raw = self.rfile.read(length) if length else b''
            body = json.loads(raw.decode('utf-8')) if raw else {}
            if not isinstance(body, dict):
                raise TypeError('Dữ liệu không hợp lệ.')
            message = self.server.dispatch(parts, body)
        except LookupError as error:
            self._json({'error': str(error)}, HTTPStatus.NOT_FOUND)
        except PermissionError as error:
            self._json({'error': str(error)}, HTTPStatus.FORBIDDEN)
        except (OSError, TypeError, ValueError, RuntimeError) as error:
            self._json({'error': str(error)}, HTTPStatus.BAD_REQUEST)
        else:
            self.server.invalidate_cache()
            payload = {'ok': True, 'message': message}
            if isinstance(message, dict):
                payload = {**message, **payload}
            self._json(payload)


_CACHE_TTL_FAST = 3.0
_CACHE_TTL_MEDIA = 5.0


def _stat_sig(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _dir_sig(directory: Path, *, suffix: str = '', recursive: bool = False) -> tuple:
    if not directory.is_dir():
        return ()
    items: list[tuple[str, int, int]] = []

    def _walk(base: Path, prefix: str) -> None:
        try:
            with os.scandir(base) as entries:
                ordered = sorted(entries, key=lambda entry: entry.name)
        except OSError:
            return
        for entry in ordered:
            rel = f'{prefix}{entry.name}'
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if entry.is_dir(follow_symlinks=False):
                items.append((rel + '/', st.st_mtime_ns, 0))
                if recursive:
                    _walk(Path(entry.path), rel + '/')
            elif not suffix or entry.name.endswith(suffix):
                items.append((rel, st.st_mtime_ns, st.st_size))

    _walk(directory, '')
    return tuple(items)


def _projects_sig(root: Path, *, deep_revisions: bool = False) -> tuple:
    projects_dir = root / 'projects'
    if not projects_dir.is_dir():
        return ()
    items: list[tuple] = [_stat_sig(projects_dir)]
    try:
        with os.scandir(projects_dir) as entries:
            ordered = sorted(entries, key=lambda entry: entry.name)
    except OSError:
        return tuple(items)
    for entry in ordered:
        if not entry.is_dir(follow_symlinks=False):
            continue
        pdir = Path(entry.path)
        row: list[object] = [
            entry.name,
            _stat_sig(pdir / 'project.yaml'),
            _stat_sig(pdir / 'blocked-reason.md'),
        ]
        if deep_revisions:
            revs_dir = pdir / 'revisions'
            if revs_dir.is_dir():
                row.append(_stat_sig(revs_dir))
                try:
                    rev_names = sorted(
                        r.name for r in os.scandir(revs_dir) if r.is_dir(follow_symlinks=False)
                    )
                except OSError:
                    rev_names = []
                for rname in rev_names[-2:]:
                    rdir = revs_dir / rname
                    row.append((
                        rname,
                        _stat_sig(rdir / 'evidence/ledger.yaml'),
                        _stat_sig(rdir / 'script/script.yaml'),
                        _stat_sig(rdir / 'storyboard/storyboard.yaml'),
                        _stat_sig(rdir / 'posts/posts.yaml'),
                        _stat_sig(rdir / 'renders/video.mp4'),
                        _stat_sig(rdir / 'reviews/medical-approval.yaml'),
                        _stat_sig(rdir / 'reviews/video-approval.yaml'),
                        _stat_sig(rdir / 'reviews/script-review.yaml'),
                        _stat_sig(rdir / 'reviews/product-review.yaml'),
                    ))
        items.append(tuple(row))
    return tuple(items)


def _logs_sig(root: Path) -> tuple:
    logs_dir = root / 'topics' / 'logs'
    if not logs_dir.is_dir():
        return ()
    items: list[tuple] = [
        _stat_sig(logs_dir),
        _stat_sig(logs_dir / 'xuong.log'),
        _stat_sig(logs_dir / 'activity.jsonl'),
        _stat_sig(logs_dir / 'quota.yaml'),
    ]
    try:
        with os.scandir(logs_dir) as entries:
            ordered = sorted(entries, key=lambda entry: entry.name)
    except OSError:
        return tuple(items)
    for entry in ordered:
        if not entry.is_dir(follow_symlinks=False):
            continue
        sdir = Path(entry.path)
        items.append((
            entry.name,
            _stat_sig(sdir),
            _stat_sig(sdir / 'blocked.txt'),
            _stat_sig(sdir / 'paused.yaml'),
            _stat_sig(sdir / 'leader-repair.yaml'),
            _stat_sig(sdir / 'review-draft.yaml'),
            _stat_sig(sdir / 'waiting-model.txt'),
            _stat_sig(sdir / 'waiting-model-step.yaml'),
            _stat_sig(sdir / 'agent-retry.yaml'),
            _stat_sig(sdir / 'production-retry.yaml'),
            _stat_sig(sdir / 'doctor-questions.yaml'),
            _stat_sig(sdir / RUNNING_MARKER),
            _stat_sig(sdir / PRODUCTION_RUNNING_MARKER),
        ))
    return tuple(items)


def _state_fingerprint(root: Path, agents: Callable[[], list[str]] | None = None) -> tuple:
    return (
        factory.running_pid(root),
        tuple(agents()) if agents is not None else None,
        _stat_sig(root / 'topics/.xuong.lock'),
        _stat_sig(root / 'topics/.telegram-bot.lock'),
        _stat_sig(root / 'cache/telegram/bot-state.yaml'),
        _stat_sig(root / 'profiles/doctor-feedback.yaml'),
        _stat_sig(root / 'profiles/company.yaml'),
        _stat_sig(pin_path()),
        _stat_sig(_operator_config()),
        _projects_sig(root, deep_revisions=False),
        _logs_sig(root),
    )


def _overview_fingerprint(root: Path) -> tuple:
    return (
        factory.running_pid(root),
        _stat_sig(root / 'topics/.xuong.lock'),
        _stat_sig(root / 'topics/queue.yaml'),
        _stat_sig(root / 'topics/channel-metrics.yaml'),
        _stat_sig(root / 'topics/channel-insights.yaml'),
        _stat_sig(root / 'topics/auto-publish.json'),
        _dir_sig(root / 'topics/auto-publications', suffix='.json'),
        _dir_sig(root / 'topics/channel-publications', suffix='.json'),
        _stat_sig(root / 'profiles/company.yaml'),
        _dir_sig(root / 'topics/inbox', suffix='.dossier.yaml'),
        _projects_sig(root, deep_revisions=True),
        _logs_sig(root),
    )


def _company_fingerprint(root: Path) -> tuple:
    return (
        factory.running_pid(root),
        _stat_sig(root / 'topics/.xuong.lock'),
        _stat_sig(root / 'topics/queue.yaml'),
        _stat_sig(root / 'profiles/company.yaml'),
        _projects_sig(root, deep_revisions=True),
        _logs_sig(root),
    )


def _activity_fingerprint(root: Path) -> tuple:
    return (
        factory.running_pid(root),
        _stat_sig(root / 'topics/logs/activity.jsonl'),
        _stat_sig(root / 'profiles/company.yaml'),
    )


def _medanim_fingerprint(root: Path) -> tuple:
    return (
        _dir_sig(root / 'library/medanim', recursive=True),
        _dir_sig(root / 'video/public/medanim', recursive=True),
        _stat_sig(pin_path()),
        _stat_sig(_operator_config()),
    )


def _research_inbox_fingerprint(root: Path) -> tuple:
    return (
        _stat_sig(root / 'topics/queue.yaml'),
        _dir_sig(root / 'topics/inbox', suffix='.dossier.yaml'),
        _projects_sig(root, deep_revisions=False),
    )


class _ResponseCache:
    """Thread-safe response cache invalidated by source-file (mtime_ns, size) or short TTL."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}
        self._entries: dict[str, tuple[float, object, object]] = {}

    def _lock_for(self, key: str) -> threading.Lock:
        with self._lock:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._key_locks[key] = lock
            return lock

    def get_or_compute(
        self,
        key: str,
        fingerprint_fn: Callable[[], object],
        ttl_s: float,
        compute_fn: Callable[[], object],
    ) -> object:
        fp = fingerprint_fn()
        now = self._clock()
        with self._lock:
            hit = self._entries.get(key)
            if hit is not None and hit[1] == fp and (now - hit[0]) < ttl_s:
                return hit[2]
        with self._lock_for(key):
            fp = fingerprint_fn()
            now = self._clock()
            with self._lock:
                hit = self._entries.get(key)
                if hit is not None and hit[1] == fp and (now - hit[0]) < ttl_s:
                    return hit[2]
            value = compute_fn()
            computed_at = self._clock()
            with self._lock:
                self._entries[key] = (computed_at, fp, value)
            return value

    def invalidate(self) -> None:
        with self._lock:
            self._entries.clear()


def _load_or_create_token(root: Path) -> str:
    path = root / TOKEN_FILE
    if path.is_file():
        try:
            saved = path.read_text(encoding='utf-8').strip()
        except OSError:
            saved = ''
        if saved:
            return saved
    generated = secrets.token_urlsafe(24)
    write_text_atomic(path, generated)
    return generated


class DashboardServer(ThreadingHTTPServer):
    """HTTP server bound to loopback; actions never touch approval records."""

    daemon_threads = True
    # On Windows, SO_REUSEADDR lets a second bind shadow an active listener (e.g. recv.py)
    # instead of failing with WinError 10048/10013 so port fallback triggers reliably.
    allow_reuse_address = sys.platform != 'win32'

    def server_bind(self) -> None:
        if sys.platform == 'win32' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, root: Path, port: int, *, token: str | None = None,
                 agents: Callable[[], list[str]] | None = None,
                 actions: dict[str, Callable[..., str]] | None = None,
                 repo_dir: Path | None = None) -> None:
        hide_child_consoles()
        self.root = root.resolve()
        self.repo_dir = (repo_dir or REPO_ROOT).resolve()
        self.running_version = (
            app_update.read_running_version(self.repo_dir)
            if repo_dir is not None
            else app_update.startup_version()
        )
        self.token = token or _load_or_create_token(self.root)
        self.agents = agents
        self.limiter = PinLimiter()
        self._studio_proc: object | None = None
        self._studio_log_handle: object | None = None
        self._studio_lock = threading.Lock()
        self._cache = _ResponseCache()
        self._html_cache: tuple[tuple[int, int] | None, bytes] | None = None
        super().__init__(('127.0.0.1', port), _Handler)
        self.actions = actions or default_actions(self)

    def invalidate_cache(self) -> None:
        self._cache.invalidate()

    def html_bytes(self) -> bytes:
        sig = _stat_sig(HTML_PATH)
        cached = self._html_cache
        if cached is not None and cached[0] == sig:
            return cached[1]
        raw = HTML_PATH.read_text(encoding='utf-8').replace('__TOKEN__', self.token).encode('utf-8')
        self._html_cache = (sig, raw)
        return raw

    def cached_state(self) -> dict:
        return self._cache.get_or_compute(
            'state',
            lambda: _state_fingerprint(self.root, self.agents),
            _CACHE_TTL_FAST,
            lambda: snapshot(self.root, agents=self.agents),
        )

    def cached_overview(self) -> dict:
        return self._cache.get_or_compute(
            'overview',
            lambda: _overview_fingerprint(self.root),
            _CACHE_TTL_FAST,
            lambda: overview(self.root),
        )

    def cached_company(self) -> dict:
        return self._cache.get_or_compute(
            'company',
            lambda: _company_fingerprint(self.root),
            _CACHE_TTL_FAST,
            lambda: company_roster(self.root),
        )

    def cached_activity(self, *, limit: int = 10, slug: str | None = None) -> dict:
        return self._cache.get_or_compute(
            f'activity:{limit}:{slug or ""}',
            lambda: _activity_fingerprint(self.root),
            _CACHE_TTL_FAST,
            lambda: activity(self.root, limit=limit, slug=slug),
        )

    def cached_medanim(self) -> dict:
        return self._cache.get_or_compute(
            'medanim',
            lambda: _medanim_fingerprint(self.root),
            _CACHE_TTL_MEDIA,
            lambda: medanim_catalog_payload(self.root),
        )

    def cached_research_inbox(self) -> dict:
        return self._cache.get_or_compute(
            'research_inbox',
            lambda: _research_inbox_fingerprint(self.root),
            _CACHE_TTL_MEDIA,
            lambda: dashboard_operations.research_inbox_payload(self.root),
        )

    @property
    def url(self) -> str:
        return f'http://127.0.0.1:{self.server_address[1]}/'

    def project_dir(self, slug: str) -> tuple[Path, ProjectManifestV2]:
        layout = dashboard_operations.project_layout(self.root, slug)
        return layout.project_dir, layout.manifest

    def start_studio(self) -> dict[str, str]:
        with self._studio_lock:
            if self._studio_proc is None:
                try:
                    with urlopen('http://127.0.0.1:3000', timeout=2) as response:
                        if b'<title>Remotion Studio</title>' in response.read(65536):
                            return {'url': 'http://127.0.0.1:3000'}
                except (OSError, URLError):
                    pass
            log_path = self.root / 'cache/studio.log'
            log_path.parent.mkdir(parents=True, exist_ok=True)
            if self._studio_proc is None or getattr(self._studio_proc, 'poll', lambda: None)() is not None:
                if self._studio_log_handle is not None:
                    try:
                        self._studio_log_handle.close()
                    except OSError:
                        pass
                log_file = log_path.open('a', encoding='utf-8')
                self._studio_log_handle = log_file
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                cwd = self.root if (self.root / 'video').is_dir() else REPO_ROOT
                argv = resolve_pnpm_argv(['--dir', 'video', 'exec', 'remotion', 'studio'])
                self._studio_proc = subprocess.Popen(
                    argv,
                    cwd=cwd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    shell=False,
                    creationflags=flags,
                )
            url = 'http://127.0.0.1:3000'
            if log_path.is_file():
                text = _read_text(log_path, limit=8000)
                match = re.search(r'https?://(?:localhost|127\.0\.0\.1):\d+', text)
                if match:
                    url = match.group(0)
            deadline = time.monotonic() + 60
            while True:
                try:
                    with urlopen(url, timeout=2) as response:
                        if response.status == HTTPStatus.OK:
                            break
                except (OSError, URLError):
                    pass
                if self._studio_proc.poll() is not None:
                    raise RuntimeError('Remotion Studio đã dừng khi khởi động. Xem cache/studio.log.')
                if time.monotonic() >= deadline:
                    raise RuntimeError('Remotion Studio đang khởi động lâu. Thử mở lại sau ít giây; xem cache/studio.log.')
                time.sleep(0.3)
            return {'url': url}

    def server_close(self) -> None:
        handle = getattr(self, '_studio_log_handle', None)
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
            self._studio_log_handle = None
        super().server_close()

    def dispatch(self, parts: list[str], body: dict | None = None) -> str | dict:
        if parts == ['api', 'studio']:
            return self.start_studio()
        if len(parts) == 4 and parts[:2] == ['api', 'medanim'] and parts[3] in {'approve', 'reject'}:
            return medanim_decide(self.root, parts[2], parts[3], body or {}, limiter=self.limiter)
        extra = dashboard_operations.post_route(self, parts, body or {})
        if extra is not None:
            return extra
        if len(parts) == 3 and parts[0] == 'api' and parts[1] in {'standards', 'feedback'}:
            key = f'{parts[1]}/{parts[2]}'
            if key in self.actions:
                return self.actions[key](body or {})
        if len(parts) == 3 and parts[0] == 'api' and parts[1] in {'factory', 'review', 'app'}:
            key = f'{parts[1]}/{parts[2]}'
            if key in self.actions:
                return self.actions[key]()
        if len(parts) == 4 and parts[0] == 'api' and parts[1] == 'project':
            key = f'project/{parts[3]}'
            if key in self.actions:
                return self.actions[key](parts[2], body or {})
        raise LookupError('Không có thao tác này')


def answer_doctor_question(root: Path, slug: str, body: dict) -> dict:
    """Answer an open doctor question, notify coordinator chat, record standard, and release wait."""
    allowed = {'question_id', 'option_id', 'text', 'expected_revision'}
    if set(body) - allowed:
        raise ValueError('Trường dữ liệu câu hỏi không hợp lệ; không nhận PIN.')
    with dashboard_operations._MUTATION_LOCK:
        layout = dashboard_operations.project_layout(root, slug)
        expected_revision = body.get('expected_revision')
        if expected_revision != layout.manifest.active_revision:
            raise ValueError('Revision đã thay đổi; tải lại trước khi trả lời.')
        answered = doctor_questions.answer(
            root,
            slug,
            str(body.get('question_id') or ''),
            body.get('option_id'),
            str(body.get('text') or ''),
        )
        product_review.apply_doctor_answer(layout.project_dir, answered)
        ans = answered['answer']
        station = str(answered.get('station') or '').strip()
        label = str(ans.get('option_label') or '').strip()
        extra_text = str(ans.get('text') or '').strip()
        escalation_note = ''
        if str(answered.get('kind') or '') == 'escalation':
            opt_id = str(ans.get('option_id') or '').strip()
            if opt_id == 'pause_project':
                dashboard_operations.pause_project(
                    root,
                    slug,
                    reason=extra_text or 'Bác sĩ chọn tạm dừng từ thẻ trình cấp trên.',
                )
            elif opt_id == 'retry_repair_cycle':
                repair_path = root / 'topics' / 'logs' / slug / 'leader-repair.yaml'
                if repair_path.is_file():
                    rep = _safe_yaml(repair_path)
                    if rep:
                        rep['attempts_before_incident'] = (
                            rep.get('attempts') if isinstance(rep.get('attempts'), int) else 0
                        )
                        for stale_key in ('phase', 'attention_reason', 'error', 'retry_after'):
                            rep.pop(stale_key, None)
                        write_yaml_atomic(repair_path, rep)
                if (
                    repair_service._is_repair_production_side_state(layout)
                    and (layout.artifact_root / product_review.LOG).is_file()
                ):
                    change_request.mark_applied(layout.project_dir)
                    resume_gate(
                        layout.project_dir,
                        GateKind.VIDEO,
                        target=WorkflowState.PRODUCTION_IN_PROGRESS,
                        now=datetime.now(UTC),
                    )
                dashboard_operations.retry_project(
                    root,
                    slug,
                    expected_revision=layout.manifest.active_revision,
                    allow_repair_release=True,
                )
                factory.wake_background(root)
            else:
                if extra_text:
                    ctx = {
                        'source': 'doctor-escalation',
                        'question_id': answered['id'],
                        'revision': layout.manifest.active_revision,
                    }
                    if layout.manifest.state in {
                        WorkflowState.DRAFT_READY,
                        WorkflowState.NEEDS_MEDICAL_REVISION,
                    }:
                        change_request.request_change(layout.project_dir, 'edit_script', extra_text, ctx)
                    elif layout.manifest.state in {
                        WorkflowState.MEDICALLY_APPROVED,
                        WorkflowState.PRODUCTION_IN_PROGRESS,
                        WorkflowState.NEEDS_PRODUCTION_REVISION,
                    }:
                        change_request.request_change(layout.project_dir, 'edit_production', extra_text, ctx)
                elif (
                    repair_service._is_repair_production_side_state(layout)
                    and (layout.artifact_root / product_review.LOG).is_file()
                ):
                    change_request.mark_applied(layout.project_dir)
                    resume_gate(
                        layout.project_dir,
                        GateKind.VIDEO,
                        target=WorkflowState.PRODUCTION_IN_PROGRESS,
                        now=datetime.now(UTC),
                    )
                try:
                    dashboard_operations.retry_project(
                        root,
                        slug,
                        expected_revision=layout.manifest.active_revision,
                        allow_repair_release=True,
                    )
                    factory.wake_background(root)
                except ValueError as exc:
                    escalation_note = f' ({exc})'
        decision_text = '. '.join(part for part in (label, extra_text) if part)
        chat_text = (
            f'Quyết định Trạm {station}: {decision_text}'
            if station
            else f'Quyết định bác sĩ: {decision_text}'
        )
        chat_msg = chat.post(
            root,
            slug,
            chat_text[:4000],
            {'slug': slug, 'revision': layout.manifest.active_revision, 'view': 'overview'},
        )
        standards.record(
            root,
            slug=slug,
            gate=f'tram-{station}' if station else 'question',
            revision=layout.manifest.active_revision,
            kind='comment',
            text=chat_text[:4000],
            reviewer=reviewer_name(),
        )
        factory.wake_background(root)
        return {
            'answered': answered,
            'chat_message_id': chat_msg['id'],
            'summary': f'Đã ghi nhận: {chat_text}{escalation_note}',
        }


def default_actions(server: DashboardServer) -> dict[str, Callable[..., str]]:
    root = server.root

    def start() -> str:
        pid = factory.start_background(root)
        repair_service.ensure_background(root)
        return f'Xưởng đang chạy (PID {pid}).'

    def stop() -> str:
        pid = factory.stop_background(root)
        return f'Đã dừng xưởng PID {pid}.' if pid else 'Xưởng không chạy.'

    def review() -> str:
        if not any(p.state in factory.GATES for _, p in factory.projects(root)):
            return 'Không có video nào đang chờ duyệt.'
        open_review_console(root)
        return 'Đã mở cửa sổ duyệt — chọn A/R và gõ PIN trong cửa sổ đó.'

    def packet(slug: str, body: dict) -> str:
        path, project = server.project_dir(slug)
        if project.state not in factory.GATES:
            raise ValueError('Project này không ở cổng duyệt.')
        _open_path(factory.write_review_packet(root, path, project))
        return 'Đã mở gói duyệt trong tab mới.'

    def folder(slug: str, body: dict) -> str:
        path, _ = server.project_dir(slug)
        _open_path(path)
        return 'Đã mở thư mục project.'

    def decision(slug: str, body: dict) -> str:
        path, _ = server.project_dir(slug)
        return decide(root, path, body, limiter=server.limiter)

    def comment(slug: str, body: dict) -> str:
        server.project_dir(slug)
        count = save_comment(root, slug, str(body.get('target', '')), str(body.get('text', '')))
        return f'Đã lưu nháp góp ý ({count} mục).'

    def add_standard(body: dict) -> str:
        entry = standards.record(root, slug='chung', gate='chung', revision='-', kind='comment',
                                 text=str(body.get('text', ''))[:4000], reviewer=reviewer_name())
        if entry is None:
            raise ValueError('Nhập nội dung chuẩn cần ghi nhớ.')
        return 'Đã ghi nhớ chuẩn mới; agent sẽ áp dụng từ lượt chạy tới.'

    def add_feedback(body: dict) -> str:
        project = str(body.get('project') or feedback_inbox.GENERAL)
        if project != feedback_inbox.GENERAL:
            server.project_dir(project)
        entry = feedback_inbox.add(root, project, str(body.get('text', '')))
        feedback_inbox.start(root, entry['id'])
        return 'Đã nhận ý kiến; agent đang phân tích.'

    def retry_feedback(body: dict) -> str:
        entry = feedback_inbox.retry(root, str(body.get('id', '')))
        feedback_inbox.start(root, entry['id'])
        return 'Đang phân tích lại.'

    def answer_question(slug: str, body: dict) -> dict:
        return answer_doctor_question(root, slug, body)

    def quit_app() -> str:
        from healthvideo.workflows import telegram_bot

        with contextlib.suppress(OSError, RuntimeError, ValueError):
            telegram_bot.stop_background(root)
        threading.Thread(target=server.shutdown, daemon=True).start()
        return 'App đã tắt (xưởng nền vẫn chạy nếu đang bật).'

    def update_app() -> dict:
        from healthvideo.workflows import telegram_bot

        return app_update.trigger_app_update(
            root=root,
            port=server.server_address[1],
            check_active_jobs=lambda: _active_work_blocker(root),
            is_factory_running=lambda: factory.running_pid(root) is not None,
            stop_factory=stop,
            stop_telegram=lambda: telegram_bot.stop_background(root),
            quit_app=lambda: threading.Thread(target=server.shutdown, daemon=True).start(),
        )

    return {
        'factory/start': start, 'factory/stop': stop, 'review/open': review,
        'project/packet': packet, 'project/folder': folder, 'project/decide': decision,
        'project/comment': comment, 'project/answer-question': answer_question,
        'standards/add': add_standard, 'feedback/add': add_feedback,
        'feedback/retry': retry_feedback, 'app/quit': quit_app, 'app/update': update_app,
    }


def _is_pyh_state_payload(data: object) -> bool:
    return (
        isinstance(data, dict)
        and isinstance(data.get('projects'), list)
        and (data.get('app') == APP_ID or 'xuong' in data or 'factory' in data)
    )


def existing_dashboard(port: int) -> bool:
    from urllib.error import HTTPError

    for route in ('/api/state', '/api/status'):
        try:
            with urlopen(f'http://127.0.0.1:{port}{route}', timeout=0.25) as response:
                data = json.loads(response.read().decode('utf-8'))
                if _is_pyh_state_payload(data):
                    return True
        except HTTPError:
            continue
        except (URLError, OSError, ValueError):
            return False
    return False


def server_state_path(root: Path) -> Path:
    return root / SERVER_STATE_FILE


def read_server_state(root: Path) -> dict | None:
    path = server_state_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    port = data.get('port')
    if type(port) is not int or not (1024 <= port <= 65535):
        return None
    return data


def write_server_state(root: Path, port: int, url: str) -> Path:
    path = server_state_path(root)
    payload = {
        'port': port,
        'url': url,
        'pid': os.getpid(),
        'process_token': process_token(os.getpid()),
        'started_at': datetime.now(UTC).isoformat(timespec='seconds'),
    }
    write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def clear_server_state(root: Path, *, port: int | None = None) -> None:
    path = server_state_path(root)
    data = read_server_state(root)
    if data is None:
        return
    if data.get('pid') == os.getpid() and (port is None or data.get('port') == port):
        path.unlink(missing_ok=True)


def find_running_dashboard(root: Path, *, port: int = DEFAULT_PORT) -> tuple[int, str] | None:
    candidates: list[int] = []
    if port == DEFAULT_PORT:
        saved = read_server_state(root)
        if saved is not None:
            candidates.append(saved['port'])
        candidates.extend(range(DEFAULT_PORT, FALLBACK_PORT_END + 1))
    else:
        candidates.append(port)
    for candidate in dict.fromkeys(candidates):
        if existing_dashboard(candidate):
            return candidate, f'http://127.0.0.1:{candidate}/'
    return None


def dashboard_url(root: Path, *, port: int = DEFAULT_PORT) -> str | None:
    found = find_running_dashboard(root, port=port)
    return found[1] if found is not None else None


def _is_port_in_use(error: OSError) -> bool:
    winerror = getattr(error, 'winerror', None)
    return error.errno in {errno.EADDRINUSE, errno.EACCES} or winerror in {10048, 10013}


def _bind_dashboard_server(root: Path, port: int) -> DashboardServer:
    candidates = (
        list(range(DEFAULT_PORT, FALLBACK_PORT_END + 1))
        if port == DEFAULT_PORT
        else [port]
    )
    last_error: OSError | None = None
    for index, candidate in enumerate(candidates):
        try:
            return DashboardServer(root, candidate)
        except OSError as error:
            if not _is_port_in_use(error) or index == len(candidates) - 1:
                raise
            last_error = error
    assert last_error is not None
    raise last_error


def serve(root: Path, *, port: int = DEFAULT_PORT, open_browser: bool = True,
          echo: Callable[[str], object] = print) -> None:
    """Run the dashboard until quit; reuse an already-open one or fall back to a free port."""
    hide_child_consoles()
    found = find_running_dashboard(root, port=port)
    if found is not None:
        _, url = found
        if open_browser:
            webbrowser.open(url)
        echo(f'App đã mở sẵn: {url}')
        return
    from healthvideo.workflows import telegram_bot

    telegram_bot.ensure_background(root)
    server = _bind_dashboard_server(root, port)
    bound_port = server.server_address[1]
    write_server_state(root, bound_port, server.url)
    echo(f'App xưởng: {server.url} (đóng bằng nút "Tắt app")')
    if open_browser:
        threading.Timer(0.3, webbrowser.open, args=(server.url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        clear_server_state(root, port=bound_port)
        server.server_close()


_SHORTCUT_SCRIPT = """
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$p = [Console]::In.ReadToEnd() | ConvertFrom-Json
$shell = New-Object -ComObject WScript.Shell
# WScript.Shell saves through the ANSI code page ("Xưởng" -> "Xu?ng"); save ASCII, rename after.
$tmp = Join-Path (Split-Path -LiteralPath $p.path) 'pyh-shortcut.tmp.lnk'
$link = $shell.CreateShortcut($tmp)
$link.TargetPath = $p.target
$link.Arguments = $p.arguments
$link.WorkingDirectory = $p.cwd
$link.Description = $p.description
if ($p.icon) { $link.IconLocation = $p.icon }
$link.Save()
Move-Item -LiteralPath $tmp -Destination $p.path -Force
"""


def shortcut_spec(root: Path, desktop: Path) -> dict[str, str]:
    """Desktop link that starts the dashboard without any console window."""
    exe = Path(sys.executable)
    pythonw = exe.with_name('pythonw.exe')
    icon = Path(__file__).with_name('dashboard.ico')
    return {
        'path': str(desktop / 'Xưởng video.lnk'),
        'target': str(pythonw if pythonw.exists() else exe),
        'arguments': f'-c "from healthvideo.cli import app; app()" app --root "{root.resolve()}"',
        'cwd': str(root.resolve()),
        'description': 'Mở app điều khiển xưởng video Protect Your Health',
        'icon': str(icon) if icon.exists() else '',
    }


def desktop_dir() -> Path:
    """Real Desktop folder, including OneDrive-redirected desktops."""
    if sys.platform == 'win32':
        try:
            out = subprocess.run(
                ['powershell', '-NoProfile', '-NonInteractive', '-Command',
                 '[Environment]::GetFolderPath("Desktop")'],
                capture_output=True, text=True, encoding='utf-8', timeout=20, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            ).stdout.strip()
            if out:
                return Path(out)
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / 'Desktop'


def install_shortcut(root: Path, *, desktop: Path | None = None,
                     runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> Path:
    spec = shortcut_spec(root, desktop or desktop_dir())
    if sys.platform != 'win32':
        raise RuntimeError('Lối tắt Desktop chỉ hỗ trợ Windows.')
    result = runner(['powershell', '-NoProfile', '-NonInteractive', '-Command', _SHORTCUT_SCRIPT],
                    input=json.dumps(spec, ensure_ascii=False), text=True, encoding='utf-8',
                    capture_output=True, timeout=30, check=False, shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError('Không tạo được lối tắt Desktop.')
    return Path(spec['path'])
