"""Localhost dashboard for the factory: watch, control, and decide gates.

Gate decisions still need the approver PIN, typed by the doctor in the app and
verified here; the PIN is never stored, logged, or passed to agents.
"""

from __future__ import annotations

import json
import os
import re
import secrets
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

from healthvideo.agents import ACTIVITY_FILE, QUOTA_FILE, RUNNING_MARKER, QuotaBook
from healthvideo.approver_pin import pin_path, verify_pin
from healthvideo.company import COMPANY_PATH, REPO_ROOT, load_company
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.env import child_env
from healthvideo.process import resolve_pnpm_argv
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.queue import load_queue
from healthvideo.workflows import (
    asset_library,
    dashboard_operations,
    decision_card,
    factory,
    feedback_inbox,
    product_review,
    standards,
)
from healthvideo.workflows.gate_review import approve_gate, reject_gate
from healthvideo.workflows.script_review import review_view

APP_ID = 'healthvideo-dashboard'
DEFAULT_PORT = 8765
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


def running_agents(root: Path) -> list[str]:
    """Agents the factory itself is running now, from the runner's per-topic marker."""
    if factory.running_pid(root) is None:
        return []
    names = []
    for marker in sorted((root / 'topics' / 'logs').glob(f'*/{RUNNING_MARKER}')):
        first = marker.read_text(encoding='utf-8', errors='replace').splitlines()[:1]
        names.append(first[0].strip() if first else 'agent')
    return names


STEP_LABELS: dict[str, str] = {
    'create': 'Đang tạo dự án',
    'scout': 'Đang trinh sát chủ đề',
    'research': 'Đang nghiên cứu y văn',
    'draft': 'Đang viết kịch bản',
    'script_review': 'Đang chấm kịch bản',
    'posts': 'Đang soạn bài đăng',
    'produce': 'Đang dựng video',
    'visual_review': 'Đang chọn hình minh họa',
    'product_review': 'Đang kiểm định video',
    'revise_medical': 'Đang sửa theo góp ý y khoa',
    'revise_production': 'Đang sửa hình/nhịp video',
    'revise_product': 'Đang sửa lỗi sản phẩm',
    'chat': 'Đang trả lời chat',
    'chat_deep': 'Đang phân tích chuyên sâu',
    'coordinator': 'Đang điều phối chat',
    'feedback_inbox': 'Đang phân tích ý kiến',
}


def _parse_iso(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.astimezone()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo else parsed.astimezone()
    except ValueError:
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
    """Recent completed agent events plus any currently running (start without end) jobs."""
    path = root / ACTIVITY_FILE
    roles = _role_names()
    current_now = now()
    open_starts: dict[tuple[str, str, str, str, str], tuple[dict, datetime | None]] = {}
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
            key = (
                str(row.get('slug') or ''),
                str(row.get('step') or ''),
                str(row.get('role') or ''),
                str(row.get('cli') or ''),
                str(row.get('model') or ''),
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
    from healthvideo.workflows.factory import _process_token

    running: list[dict] = []
    for start_row, start_dt in open_starts.values():
        pid = start_row.get('pid')
        if isinstance(pid, int) and _process_token(pid) is None:
            # The process that started this job died (app or factory restarted): not running.
            history.append({**start_row, 'started_at': start_row.get('at'), 'duration_s': 0.0,
                            'running': False, 'ok': False, 'interrupted': True})
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


def company_roster(
    root: Path,
    *,
    per_role_limit: int = 5,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> dict:
    """Read-only company roster from profiles/company.yaml enriched with per-role activity."""
    cfg_path = root / 'profiles/company.yaml'
    company = load_company(cfg_path if cfg_path.is_file() else COMPANY_PATH)
    act = activity(root, limit=10_000, now=now)
    running_by_role: dict[str, list[dict]] = {}
    recent_by_role: dict[str, list[dict]] = {}
    for item in act['running']:
        running_by_role.setdefault(str(item.get('role') or ''), []).append(item)
    for item in act['recent']:
        recent_by_role.setdefault(str(item.get('role') or ''), []).append(item)

    cap = max(1, int(per_role_limit))
    epoch = datetime.min.replace(tzinfo=UTC)
    roles_payload: list[dict] = []
    for role_id, role in company.roles.items():
        role_running = running_by_role.get(role_id, [])
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
        roles_payload.append({
            'id': role.id,
            'name': role.name,
            'tier': role.tier,
            'steps': list(role.steps),
            'step_labels': [STEP_LABELS.get(s, s) for s in role.steps],
            'skills': list(role.skills),
            'configured_models': [{'cli': m.cli, 'model': m.model} for m in company.chain(role.id)],
            'running': role_running,
            'recent': all_recent[:cap],
            'models_used': [{'cli': c, 'model': m, 'count': n} for (c, m), n in counts.items()],
            'last_error': bool(all_recent and all_recent[0].get('ok') is False),
        })
    return {'roles': roles_payload}


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


def _project_status_line(
    root: Path,
    path: Path,
    project: ProjectManifestV2,
    running_job: dict | None,
    recent_job: dict | None,
    blocked_note: str,
) -> str:
    if running_job is not None:
        step = running_job.get('step_label') or STEP_LABELS.get(str(running_job.get('step') or ''), 'Đang xử lý')
        role = running_job.get('role_name') or running_job.get('role') or 'Agent'
        model = running_job.get('model') or running_job.get('cli') or ''
        return f'{step} · {role} · {model}'.strip(' ·')
    waiting_file = root / 'topics/logs' / path.name / 'waiting-model.txt'
    if waiting_file.is_file():
        until_raw = waiting_file.read_text(encoding='utf-8', errors='replace').strip()
        until_dt = _parse_iso(until_raw)
        when = until_dt.strftime('%H:%M') if until_dt else until_raw
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


def overview(
    root: Path,
    *,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> dict:
    """Company overview payload for the home page: KPI tiles, decision strip, projects, resting models."""
    current_now = now()
    act = activity(root, limit=30, now=lambda: current_now)
    running_by_slug = {str(item.get('slug')): item for item in act['running'] if item.get('slug')}
    recent_by_slug: dict[str, dict] = {}
    for item in act['recent']:
        slug_key = str(item.get('slug') or '')
        if slug_key and slug_key not in recent_by_slug:
            recent_by_slug[slug_key] = item
    resting = QuotaBook(root / QUOTA_FILE).snapshot(current_now)
    queue_dates: dict[str, datetime] = {}
    try:
        for entry in load_queue(root):
            queue_dates[entry.slug] = datetime.combine(entry.added, datetime.min.time()).astimezone()
    except (OSError, ValueError):
        pass

    logs = root / 'topics' / 'logs'
    decisions: list[dict] = []
    project_cards: list[dict] = []
    done_states = {WorkflowState.VIDEO_APPROVED, WorkflowState.PACKAGED, WorkflowState.PUBLISHED_MANUAL}
    inactive_states = done_states | {WorkflowState.IDEA, WorkflowState.TOPIC_REJECTED, WorkflowState.BLOCKED} | set(factory.GATES)
    running_count = 0
    done_7d = 0
    done_30d = 0
    lead_days: list[float] = []

    for path, project in factory.projects(root):
        blocked = logs / path.name / 'blocked.txt'
        reason = path / 'blocked-reason.md'
        note = ''
        if project.state is WorkflowState.BLOCKED or blocked.exists():
            source = reason if reason.exists() else blocked
            note = source.read_text(encoding='utf-8', errors='replace').strip() if source.exists() else ''
        current_card = decision_card.card(path)
        title = factory.project_title(path, project)
        if current_card is not None:
            decisions.append({
                'slug': path.name,
                'title': title,
                'gate': current_card['gate'],
                'count': len(current_card['decisions']),
                'revision': project.active_revision,
            })
        marker = logs / path.name / RUNNING_MARKER
        is_running = (
            path.name in running_by_slug
            or marker.is_file()
            or (project.state not in inactive_states and not note)
        )
        if is_running:
            running_count += 1
        manifest_file = path / 'project.yaml'
        mtime_dt = datetime.fromtimestamp(manifest_file.stat().st_mtime).astimezone()
        if project.state in done_states:
            rev = path / 'revisions' / project.active_revision
            approval_file = rev / 'reviews/video-approval.yaml'
            done_dt = mtime_dt
            if approval_file.is_file():
                done_dt = _parse_iso(read_yaml(approval_file).get('reviewed_at')) or mtime_dt
            age_days = max(0.0, (current_now - done_dt).total_seconds() / 86400.0)
            if age_days <= 7.0:
                done_7d += 1
            if age_days <= 30.0:
                done_30d += 1
            start_dt = queue_dates.get(path.name)
            if start_dt is None:
                first_card = path / 'revisions/001/topic/card.yaml'
                if first_card.is_file():
                    start_dt = datetime.fromtimestamp(first_card.stat().st_mtime).astimezone()
            if start_dt is not None and done_dt >= start_dt:
                lead_days.append((done_dt - start_dt).total_seconds() / 86400.0)

        label = STATE_LABELS.get(project.state, project.state.value)
        project_cards.append({
            'slug': path.name,
            'title': title,
            'stage_index': stage_index(project),
            'stage': stage_index(project),
            'state': project.state.value,
            'state_label': f'Bị chặn · {STAGES[stage_index(project)].lower()}' if note else label,
            'gate': factory.GATES.get(project.state),
            'revision': project.active_revision,
            'blocked': note,
            'preview_url': _project_preview_url(path, project),
            'status_line': _project_status_line(
                root, path, project,
                running_by_slug.get(path.name),
                recent_by_slug.get(path.name),
                note,
            ),
            'updated_at': mtime_dt.isoformat(timespec='seconds'),
        })

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
        'projects': project_cards,
        'resting': resting,
        'channel': {'connected': False},
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
    """Plain-JSON view of the factory for the dashboard; reads files only."""
    logs = root / 'topics' / 'logs'
    items = []
    for path, project in factory.projects(root):
        blocked = logs / path.name / 'blocked.txt'
        reason = path / 'blocked-reason.md'
        note = ''
        if project.state is WorkflowState.BLOCKED or blocked.exists():
            source = reason if reason.exists() else blocked
            note = source.read_text(encoding='utf-8', errors='replace').strip() if source.exists() else ''
        manifest = path / 'project.yaml'
        label = STATE_LABELS.get(project.state, project.state.value)
        items.append({
            'slug': path.name,
            'title': factory.project_title(path, project),
            'state': project.state.value,
            'state_label': f'Bị chặn · {STAGES[stage_index(project)].lower()}' if note else label,
            'stage': stage_index(project),
            'gate': factory.GATES.get(project.state),
            'blocked': note,
            'revision': project.active_revision,
            'comments': len(load_draft(root, path.name)),
            'updated_at': datetime.fromtimestamp(manifest.stat().st_mtime).astimezone().isoformat(timespec='seconds'),
        })
    pid = factory.running_pid(root)
    return {
        'app': APP_ID,
        'factory': {'running': pid is not None, 'pid': pid},
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
        'now': datetime.now().astimezone().isoformat(timespec='seconds'),
    }


# ---------- in-app review: products, draft comments, media ----------

MEDIA_TYPES = {'.mp4': 'video/mp4', '.wav': 'audio/wav', '.mp3': 'audio/mpeg',
               '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}


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


def review_bundle(root: Path, project_dir: Path, project: ProjectManifestV2) -> dict:
    """Everything the doctor needs to accept a topic, read straight from the active revision."""
    rev = project_dir / 'revisions' / project.active_revision
    script = read_yaml(rev / 'script/script.yaml') if (rev / 'script/script.yaml').is_file() else {}
    ledger = read_yaml(rev / 'evidence/ledger.yaml') if (rev / 'evidence/ledger.yaml').is_file() else {}
    lines = [{
        'id': line.get('id'), 'text': line.get('text', ''), 'purpose': line.get('purpose'),
        'claim_id': line.get('claim_id'), 'source_marker': line.get('source_marker'),
    } for line in script.get('lines', [])]
    claims = [{
        'id': c.get('id'), 'text': c.get('text_public', ''), 'type': c.get('type'),
        'sources': c.get('sources', []), 'applicability': c.get('applicability', ''),
        'technical': c.get('text_technical', ''),
        'support': [{'source_id': s.get('source_id'), 'locator': s.get('locator'), 'quote': s.get('quote')}
                    for s in c.get('support', [])],
    } for c in ledger.get('claims', [])]
    records = [{
        'id': r.get('id'), 'title': r.get('title'), 'year': r.get('year'), 'journal': r.get('journal'),
        'doi': r.get('doi'), 'pmid': r.get('pmid'), 'url': r.get('url'),
    } for r in ledger.get('records', [])]
    media = []
    renders = rev / 'renders'
    for rel, label in (('video.mp4', 'Video hoàn chỉnh'), ('audio/narration-voice.wav', 'Giọng đọc')):
        if (renders / rel).is_file():
            media.append({'label': label, 'url': f'/media/{project_dir.name}/{rel}', 'kind': rel.rsplit('.', 1)[1]})
    for clip in sorted((renders / 'clips').glob('*.mp4')) if renders.is_dir() else []:
        media.append({'label': f'Clip {clip.stem}', 'url': f'/media/{project_dir.name}/clips/{clip.name}', 'kind': 'mp4'})
    frames = []
    if (renders / 'frames').is_dir():
        for frame in sorted((renders / 'frames').glob('*.png')):
            frames.append({'name': frame.name, 'url': f'/media/{project_dir.name}/frames/{frame.name}'})
    expert_brief = (
        read_yaml(rev / 'evidence/expert-brief.yaml')
        if (rev / 'evidence/expert-brief.yaml').is_file() else {}
    )
    storyboard = (
        read_yaml(rev / 'storyboard/storyboard.yaml')
        if (rev / 'storyboard/storyboard.yaml').is_file() else {}
    )
    qa = read_yaml(rev / 'reviews/video-qa.json') if (rev / 'reviews/video-qa.json').is_file() else {}
    return {
        'slug': project_dir.name, 'title': factory.project_title(project_dir, project),
        'state': project.state.value, 'state_label': STATE_LABELS.get(project.state, project.state.value),
        'gate': factory.GATES.get(project.state), 'revision': project.active_revision,
        'lines': lines, 'claims': claims, 'records': records, 'media': media,
        'frames': frames, 'expert_brief': expert_brief, 'storyboard': storyboard,
        'timeline': timeline(project_dir),
        'card': decision_card.card(project_dir),
        'activity': activity(root, limit=50, slug=project_dir.name)['items'],
        'script_review': review_view(rev),
        'product_review': product_review.review_view(rev),
        'video_stale': project.state in {WorkflowState.MEDICALLY_APPROVED, WorkflowState.PRODUCTION_IN_PROGRESS,
                                         WorkflowState.AWAITING_MEDICAL_REVIEW, WorkflowState.DRAFT_READY},
        'notes': _read_text(rev / 'reviews/medical-revision-notes.md'),
        'qa': {'status': qa.get('status'), 'warnings': [*qa.get('warnings', []), *qa.get('errors', [])]},
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
                html = HTML_PATH.read_text(encoding='utf-8').replace('__TOKEN__', self.server.token)
                self._send(HTTPStatus.OK, html.encode('utf-8'), 'text/html; charset=utf-8')
            elif path == '/api/ping':
                self._json({'app': APP_ID})
            elif path == '/api/status':
                self._json(snapshot(self.server.root, agents=self.server.agents))
            elif path == '/api/overview':
                self._json(overview(self.server.root))
            elif path == '/api/company':
                self._json(company_roster(self.server.root))
            elif path == '/api/progress':
                self._json(progress(self.server.root))
            elif path == '/api/activity':
                try:
                    limit = max(1, min(200, int(query.get('limit', ['10'])[0])))
                except ValueError:
                    limit = 10
                slug_filter = query.get('slug', [None])[0] or None
                self._json(activity(self.server.root, limit=limit, slug=slug_filter))
            elif path == '/api/feedback':
                self._json({'entries': feedback_inbox.view(self.server.root)})
            elif path == '/api/standards':
                self._json({'entries': standards.load(self.server.root)[::-1]})
            elif len(parts) == 4 and parts[0] == 'api' and parts[1] in {'project', 'projects'} and parts[3] == 'card':
                project_dir, _ = self.server.project_dir(parts[2])
                self._json(decision_card.card(project_dir))
            elif len(parts) == 4 and parts[0] == 'api' and parts[1] in {'project', 'projects'} and parts[3] == 'timeline':
                project_dir, _ = self.server.project_dir(parts[2])
                self._json(timeline(project_dir))
            elif len(parts) == 4 and parts[:2] == ['api', 'project'] and parts[3] == 'bundle':
                project_dir, project = self.server.project_dir(parts[2])
                self._json(review_bundle(self.server.root, project_dir, project))
            elif len(parts) >= 3 and parts[0] == 'media':
                project_dir, project = self.server.project_dir(parts[1])
                self._file(media_file(project_dir, project, '/'.join(parts[2:])))
            else:
                self._json({'error': 'not found'}, HTTPStatus.NOT_FOUND)
        except LookupError as error:
            self._json({'error': str(error)}, HTTPStatus.NOT_FOUND)
        except (OSError, ValueError) as error:
            self._json({'error': f'{type(error).__name__}: {error}'}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _file(self, target: Path) -> None:
        """Stream a render file, honouring a single `bytes=` Range so video can seek."""
        size = target.stat().st_size
        start, end = 0, size - 1
        status = HTTPStatus.OK
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', self.headers.get('Range', '').strip())
        if match and size and (match[1] or match[2]):
            if match[1]:
                start = int(match[1])
                end = min(int(match[2]), size - 1) if match[2] else size - 1
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
            if length < 0 or length > MAX_BODY:
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
            payload = {'ok': True, 'message': message}
            if isinstance(message, dict):
                payload = {**message, **payload}
            self._json(payload)


class DashboardServer(ThreadingHTTPServer):
    """HTTP server bound to loopback; actions never touch approval records."""

    daemon_threads = True

    def __init__(self, root: Path, port: int, *, token: str | None = None,
                 agents: Callable[[], list[str]] | None = None,
                 actions: dict[str, Callable[..., str]] | None = None) -> None:
        super().__init__(('127.0.0.1', port), _Handler)
        self.root = root.resolve()
        self.token = token or secrets.token_urlsafe(24)
        self.agents = agents
        self.limiter = PinLimiter()
        self._studio_proc: object | None = None
        self._studio_log_handle: object | None = None
        self._studio_lock = threading.Lock()
        self.actions = actions or default_actions(self)

    @property
    def url(self) -> str:
        return f'http://127.0.0.1:{self.server_address[1]}/'

    def project_dir(self, slug: str) -> tuple[Path, ProjectManifestV2]:
        layout = dashboard_operations.project_layout(self.root, slug)
        return layout.project_dir, layout.manifest

    def start_studio(self) -> dict[str, str]:
        with self._studio_lock:
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
            return {'url': url}

    def server_close(self) -> None:
        if self._studio_log_handle is not None:
            try:
                self._studio_log_handle.close()
            except OSError:
                pass
            self._studio_log_handle = None
        super().server_close()

    def dispatch(self, parts: list[str], body: dict | None = None) -> str | dict:
        if parts == ['api', 'studio']:
            return self.start_studio()
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


def default_actions(server: DashboardServer) -> dict[str, Callable[..., str]]:
    root = server.root

    def start() -> str:
        return f'Xưởng đang chạy (PID {factory.start_background(root)}).'

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

    def quit_app() -> str:
        threading.Thread(target=server.shutdown, daemon=True).start()
        return 'App đã tắt (xưởng nền vẫn chạy nếu đang bật).'

    return {
        'factory/start': start, 'factory/stop': stop, 'review/open': review,
        'project/packet': packet, 'project/folder': folder, 'project/decide': decision,
        'project/comment': comment, 'standards/add': add_standard,
        'feedback/add': add_feedback, 'feedback/retry': retry_feedback,
        'app/quit': quit_app,
    }


def existing_dashboard(port: int) -> bool:
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/ping', timeout=1) as response:
            return json.loads(response.read().decode('utf-8')).get('app') == APP_ID
    except (URLError, OSError, ValueError):
        return False


def serve(root: Path, *, port: int = DEFAULT_PORT, open_browser: bool = True,
          echo: Callable[[str], object] = print) -> None:
    """Run the dashboard until quit; reuse an already-open one on the same port."""
    url = f'http://127.0.0.1:{port}/'
    if existing_dashboard(port):
        if open_browser:
            webbrowser.open(url)
        echo(f'App đã mở sẵn: {url}')
        return
    server = DashboardServer(root, port)
    echo(f'App xưởng: {server.url} (đóng bằng nút "Tắt app")')
    if open_browser:
        threading.Timer(0.3, webbrowser.open, args=(server.url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
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
