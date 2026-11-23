"""Read-only recovery previews and explicit local app operations.

Retry releases the runner's existing hold; it never starts a second worker.
"""

from __future__ import annotations

import importlib
import json
import re
import shutil
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

from healthvideo.agents import RUNNING_MARKER, cancel_running_job
from healthvideo.domain.asset_manifest import (
    load_asset_manifest,
    validate_asset_manifest,
)
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.process import is_same_process
from healthvideo.project_codes import project_codes
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.storage.queue import add_to_queue, load_queue, remove_from_queue
from healthvideo.workflows import (
    channel_analytics,
    chat,
    doctor_questions,
    factory,
    researcher,
)
from healthvideo.workflows.gate_review import reopen_gate
from healthvideo.workflows.production_retry import AGENT_RETRY_FILE
from healthvideo.workflows.review import approval_is_stale, latest_approval
from healthvideo.workflows.runner import next_step

_MUTATION_LOCK = threading.RLock()


def inside(base: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError('Đường dẫn nằm ngoài thư mục cho phép.')
    return resolved


def check_revision_paths(project: Path, revision: Path) -> None:
    """Validate delegated gate I/O before it can follow a nested junction."""
    inside(project, revision)
    for relative in (
        'assets', 'script', 'storyboard', 'evidence', 'topic', 'posts', 'workflow', 'renders',
        'reviews', 'reviews/medical', 'reviews/video', 'reviews/visual',
        'assets/asset-manifest.yaml', 'assets/library.yaml', 'assets/license-ledger.yaml',
        'script/script.yaml', 'script/outline.yaml', 'storyboard/storyboard.yaml',
        'storyboard/clip-plan.yaml', 'evidence/ledger.yaml',
        'reviews/medical-approval.yaml', 'reviews/video-approval.yaml',
        'reviews/imported-contact-sheet.png', 'reviews/imported-contact-sheet.yaml',
    ):
        inside(revision, revision / relative)
    manifest = revision / 'assets/asset-manifest.yaml'
    if manifest.is_file():
        for asset in load_asset_manifest(manifest).assets:
            inside(revision, revision / asset.path)


def project_layout(root: Path, slug: str):
    if not re.fullmatch(r'[a-z0-9-]{3,80}', slug):
        raise LookupError('Slug không hợp lệ.')
    project = inside(root, root / 'projects' / slug)
    if not (project / 'project.yaml').is_file():
        raise LookupError('Không có project này.')
    inside(project, project / 'project.yaml')
    layout = resolve_project_layout(project)
    inside(project, layout.artifact_root)
    return layout


def add_topic(root: Path, body: dict) -> dict:
    values = {key: body.get(key) for key in ('slug', 'title', 'question')}
    for key, value in values.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'Nhập {key}.')
        values[key] = value.strip()
    entry = QueueEntry(**values, doctor_note=body.get('doctor_note'), added=datetime.now().astimezone().date())
    with _MUTATION_LOCK:
        inside(root, root / 'topics/queue.yaml')
        add_to_queue(root, entry)
    return entry.model_dump(mode='json')


def _retry_api():
    try:
        return importlib.import_module('healthvideo.workflows.production_retry')
    except ModuleNotFoundError as exc:
        if exc.name != 'healthvideo.workflows.production_retry':
            raise
        return None


def project_operations(root: Path, slug: str) -> dict:
    layout = project_layout(root, slug)
    rev = layout.artifact_root
    script = rev / 'script/script.yaml'
    lines = read_yaml(inside(rev, script)).get('lines', []) if script.is_file() else []
    cache = inside(layout.project_dir, layout.project_dir / 'cache/tts')
    cached = sum(1 for p in cache.glob('*.wav') if p.is_file() and p.resolve().is_relative_to(cache))
    api = _retry_api()
    retry = api.retry_status(root, layout.project_dir, layout.manifest.state) if api else {
        'allowed': False, 'reason': 'API retry chưa được cài đặt.', 'kind': 'unavailable',
    }
    blocked = inside(root, root / 'topics/logs' / slug / 'blocked.txt')
    board = inside(rev, rev / 'storyboard/storyboard.yaml')
    scenes = read_yaml(board).get('scenes', []) if board.is_file() else []
    return {
        'slug': slug, 'code': project_codes(root).get(slug), 'revision': layout.manifest.active_revision,
        'state': layout.manifest.state.value, 'gate': factory.GATES.get(layout.manifest.state),
        'next_step': next_step(layout.manifest.state), 'retry_status': retry,
        'scenes': [{'id': s['id'], 'label': s.get('narration', '')[:100]} for s in scenes if s.get('visual') == 'whiteboard'],
        'blocked': blocked.read_text(encoding='utf-8')[:4000] if blocked.is_file() else '',
        'paused': factory.is_paused(root, slug),
        'doctor_question': doctor_questions.open_question(root, slug),
        'cache': {'files': cached, 'lines': len(lines), 'verified_hits': None, 'max_requests': len(lines),
                  'note': 'File cache chưa kiểm hash/giọng/provider; số yêu cầu tối đa cho một lượt TTS.'},
    }


_SLUG_RE = re.compile(r'^[a-z0-9-]+$')
_ARCHIVE_ID_RE = re.compile(r'^[A-Za-z0-9_.-]+$')


def _validate_slug(slug: str) -> str:
    if not slug or len(slug) > 80 or '/' in slug or '\\' in slug or '..' in slug or not _SLUG_RE.fullmatch(slug):
        raise ValueError(f'Slug không hợp lệ: {slug!r}')
    return slug


def _production_marker_live(root: Path, slug: str) -> dict | None:
    marker = root / 'topics' / 'logs' / slug / '.production-running'
    if not marker.is_file():
        return None
    try:
        data = json.loads(marker.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    pid = data.get('pid')
    token = data.get('process_token')
    if (
        isinstance(pid, int)
        and not isinstance(pid, bool)
        and pid > 0
        and isinstance(token, str)
        and token.strip()
        and is_same_process(pid, token)
    ):
        return data
    return None


def _assert_safe_project_tree(root: Path, slug: str, *, deep: bool = False) -> tuple[Path, Path]:
    _validate_slug(slug)
    projects_base = root / 'projects'
    logs_base = root / 'topics' / 'logs'
    project_dir = projects_base / slug
    logs_dir = logs_base / slug
    if project_dir.is_symlink() or logs_dir.is_symlink():
        raise ValueError(f'Thư mục dự án không an toàn: {slug}')
    inside(projects_base, project_dir)
    inside(logs_base, logs_dir)
    revs_dir = project_dir / 'revisions'
    if project_dir.exists() and revs_dir.exists():
        if revs_dir.is_symlink():
            raise ValueError(f'Thư mục revision không an toàn: {slug}')
        inside(project_dir, revs_dir)
        for rev in sorted(revs_dir.iterdir()):
            if rev.is_symlink():
                raise ValueError(f'Thư mục revision không an toàn: {rev.name}')
            if rev.is_dir():
                check_revision_paths(project_dir, rev)
    if deep and project_dir.exists():
        for child in project_dir.rglob('*'):
            if child.is_symlink():
                raise ValueError(f'Đường dẫn dự án chứa liên kết ngoài phạm vi cho phép: {child.name}')
            inside(project_dir, child)
    return project_dir, logs_dir


def pause_project(root: Path, slug: str, *, reason: str = '') -> dict:
    """Pause factory and repair automation for a project without stopping the xuong daemon."""
    project_dir, logs_dir = _assert_safe_project_tree(root, slug)
    with _MUTATION_LOCK:
        in_queue = any(item.slug == slug for item in load_queue(root))
        if not project_dir.exists() and not in_queue:
            raise LookupError(f'Không tìm thấy dự án: {slug}')
        paused_path = logs_dir / 'paused.yaml'
        payload = {
            'paused_at': datetime.now(UTC).isoformat(timespec='seconds'),
            'reason': (reason or '').strip(),
        }
        write_yaml_atomic(paused_path, payload)
        cancelled = cancel_running_job(root, slug=slug)
        prod_live = _production_marker_live(root, slug)
    note = (
        'Đã đặt tạm dừng; bước dựng video đang chạy sẽ tự dừng sau khi hoàn tất lượt hiện tại.'
        if prod_live
        else f'Đã tạm dừng và huỷ {len(cancelled)} tiến trình agent đang chạy.'
        if cancelled
        else 'Đã tạm dừng tự động cho dự án.'
    )
    return {
        'ok': True,
        'slug': slug,
        'paused': True,
        'paused_at': payload['paused_at'],
        'cancelled_jobs': len(cancelled),
        'production_running': prod_live is not None,
        'note': note,
    }


def resume_project(root: Path, slug: str) -> dict:
    """Clear the pause marker so xuong can pick up the project on its next pass."""
    project_dir, logs_dir = _assert_safe_project_tree(root, slug)
    with _MUTATION_LOCK:
        in_queue = any(item.slug == slug for item in load_queue(root))
        paused_path = logs_dir / 'paused.yaml'
        if not project_dir.exists() and not in_queue and not paused_path.exists():
            raise LookupError(f'Không tìm thấy dự án: {slug}')
        was_paused = paused_path.exists()
        paused_path.unlink(missing_ok=True)
    factory.wake_background(root)
    return {
        'ok': True,
        'slug': slug,
        'paused': False,
        'resumed': was_paused,
        'note': (
            'Đã tiếp tục tự động; xưởng sẽ chạy lại dự án ở vòng kế tiếp.'
            if was_paused
            else 'Dự án hiện không tạm dừng.'
        ),
    }


def delete_project(root: Path, slug: str, *, confirmed: bool = False, reason: str = '') -> dict:
    """Safely remove a project from queue and archive its files into cache/deleted-projects."""
    if confirmed is not True:
        raise ValueError('Bác sĩ cần xác nhận xoá dự án trên app.')
    project_dir, logs_dir = _assert_safe_project_tree(root, slug, deep=True)
    with _MUTATION_LOCK:
        in_queue = any(item.slug == slug for item in load_queue(root))
        if not project_dir.exists() and not logs_dir.exists() and not in_queue:
            raise LookupError(f'Không tìm thấy dự án: {slug}')
        if _production_marker_live(root, slug) is not None:
            raise ValueError(
                'Dự án đang kết xuất video (.production-running). Hãy bấm Tạm dừng và chờ lượt dựng hiện tại xong rồi hãy xoá.'
            )
        paused_path = logs_dir / 'paused.yaml'
        paused_payload = {
            'paused_at': datetime.now(UTC).isoformat(timespec='seconds'),
            'reason': (reason or 'Đã xoá từ Dashboard').strip(),
        }
        write_yaml_atomic(paused_path, paused_payload)
        cancel_running_job(root, slug=slug)
        step_marker = logs_dir / chat.STEP_MARKER
        deadline = time.monotonic() + 1.0
        while step_marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        if step_marker.exists():
            raise ValueError('Bước xử lý vừa kết thúc chưa kịp đóng; thử lại sau vài giây.')

        title = ''
        if (project_dir / 'project.yaml').is_file():
            try:
                manifest = read_yaml(project_dir / 'project.yaml')
                if isinstance(manifest, dict):
                    title = str(manifest.get('title') or '')
            except (OSError, ValueError):
                title = ''

        stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
        archive_base = root / 'cache' / 'deleted-projects'
        archive_dir = archive_base / f'{stamp}-{slug}'
        suffix = 1
        while archive_dir.exists():
            archive_dir = archive_base / f'{stamp}-{slug}-{suffix}'
            suffix += 1
        archive_dir.mkdir(parents=True, exist_ok=False)

        removed_entry = remove_from_queue(root, slug)
        if not title and removed_entry is not None:
            title = removed_entry.title

        moved_project = False
        try:
            if project_dir.exists():
                shutil.move(str(project_dir), str(archive_dir / 'project'))
                moved_project = True
            if logs_dir.exists():
                shutil.move(str(logs_dir), str(archive_dir / 'logs'))
        except OSError:
            if removed_entry is not None and not (archive_dir / 'project').exists():
                try:
                    add_to_queue(root, removed_entry)
                except ValueError:
                    pass
            shutil.rmtree(archive_dir, ignore_errors=True)
            raise

        queue_entry_data = (
            json.loads(removed_entry.model_dump_json()) if removed_entry is not None else None
        )
        meta = {
            'id': archive_dir.name,
            'slug': slug,
            'title': title or slug,
            'deleted_at': datetime.now(UTC).isoformat(timespec='seconds'),
            'reason': (reason or '').strip(),
            'has_project': moved_project,
            'queue_entry': queue_entry_data,
        }
        write_yaml_atomic(archive_dir / 'meta.yaml', meta)
    return {
        'ok': True,
        'slug': slug,
        'deleted': True,
        'archive_id': archive_dir.name,
        'removed_from_queue': removed_entry is not None,
    }


def list_deleted_projects(root: Path) -> list[dict]:
    """List deleted project archives stored under cache/deleted-projects."""
    deleted_root = root / 'cache' / 'deleted-projects'
    if not deleted_root.is_dir():
        return []
    items: list[dict] = []
    for entry in sorted(deleted_root.iterdir(), key=lambda p: p.name, reverse=True):
        if entry.is_symlink() or not entry.is_dir():
            continue
        try:
            inside(deleted_root, entry)
        except ValueError:
            continue
        meta_path = entry / 'meta.yaml'
        if not meta_path.is_file():
            continue
        try:
            meta = read_yaml(meta_path)
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict) or not meta.get('slug'):
            continue
        items.append({
            'id': entry.name,
            'slug': str(meta['slug']),
            'title': str(meta.get('title') or meta['slug']),
            'deleted_at': str(meta.get('deleted_at') or ''),
            'reason': str(meta.get('reason') or ''),
            'has_project': (entry / 'project').is_dir(),
            'has_queue_entry': isinstance(meta.get('queue_entry'), dict),
        })
    return items


def restore_project(root: Path, archive_id: str) -> dict:
    """Restore an archived deleted project back into projects/ and topics/queue.yaml (paused)."""
    if not archive_id or not _ARCHIVE_ID_RE.fullmatch(archive_id) or '..' in archive_id:
        raise ValueError('Mã lưu trữ dự án không hợp lệ.')
    deleted_root = root / 'cache' / 'deleted-projects'
    archive_dir = deleted_root / archive_id
    if archive_dir.is_symlink() or not archive_dir.is_dir():
        raise LookupError(f'Không tìm thấy bản lưu dự án: {archive_id}')
    inside(deleted_root, archive_dir)
    meta = read_yaml(archive_dir / 'meta.yaml')
    if not isinstance(meta, dict) or not meta.get('slug'):
        raise ValueError('Metadata lưu trữ dự án không hợp lệ.')
    slug = _validate_slug(str(meta['slug']))
    with _MUTATION_LOCK:
        project_target = root / 'projects' / slug
        logs_target = root / 'topics' / 'logs' / slug
        if project_target.exists():
            raise ValueError(f'Dự án {slug} đã tồn tại trong thư mục projects/.')
        if any(item.slug == slug for item in load_queue(root)):
            raise ValueError(f'Chủ đề {slug} đã có trong hàng đợi.')
        if (archive_dir / 'logs').is_dir() and not logs_target.exists():
            logs_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(archive_dir / 'logs'), str(logs_target))
        write_yaml_atomic(logs_target / 'paused.yaml', {
            'paused_at': datetime.now(UTC).isoformat(timespec='seconds'),
            'reason': 'Khôi phục từ mục đã xoá — bấm Tiếp tục để chạy lại.',
        })
        queue_added = False
        raw_entry = meta.get('queue_entry')
        if isinstance(raw_entry, dict):
            entry = QueueEntry.model_validate(raw_entry)
            add_to_queue(root, entry)
            queue_added = True
        try:
            if (archive_dir / 'project').is_dir():
                project_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(archive_dir / 'project'), str(project_target))
        except OSError:
            if queue_added:
                remove_from_queue(root, slug)
            raise
        shutil.rmtree(archive_dir, ignore_errors=True)
    return {
        'ok': True,
        'slug': slug,
        'paused': True,
        'queue_added': queue_added,
    }


def _editable(root: Path, slug: str, expected_revision: str):
    layout = project_layout(root, slug)
    if expected_revision != layout.manifest.active_revision:
        raise ValueError('Revision đã thay đổi; tải lại trước khi thao tác.')
    marker = inside(root, root / 'topics/logs' / slug / RUNNING_MARKER)
    parallel_running = any((root / 'topics/logs' / slug).glob(f'parallel-*/{RUNNING_MARKER}'))
    # A blocked project or one waiting on a doctor question is skipped by the factory loop,
    # so it can be fixed while the factory runs.
    blocked = inside(root, root / 'topics/logs' / slug / 'blocked.txt').is_file()
    waiting_question = doctor_questions.open_question(root, slug) is not None
    if marker.exists() or parallel_running or (factory.running_pid(root) is not None and not blocked and not waiting_question):
        raise ValueError('Hãy dừng xưởng và chờ agent kết thúc trước khi thao tác.')
    check_revision_paths(layout.project_dir, layout.artifact_root)
    inside(root, root / 'profiles/doctor-feedback.yaml')
    return layout


def _step_marker_orphaned(marker: Path) -> bool:
    try:
        raw = marker.read_text(encoding='utf-8', errors='replace').strip()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    if not raw:
        return False
    try:
        meta = json.loads(raw)
    except ValueError:
        return False
    if not isinstance(meta, dict):
        return False
    pid = meta.get('pid')
    token = meta.get('process_token')
    if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0 and isinstance(token, str) and token:
        return not is_same_process(pid, token)
    return False


def retry_project(
    root: Path,
    slug: str,
    *,
    expected_revision: str,
    allow_repair_release: bool = False,
) -> dict:
    with _MUTATION_LOCK, chat.locked(root):
        layout = _editable(root, slug, expected_revision)
        log_dir = root / 'topics/logs' / slug
        step_marker = inside(root, log_dir / chat.STEP_MARKER)
        if step_marker.exists():
            if _step_marker_orphaned(step_marker):
                step_marker.unlink(missing_ok=True)
            else:
                raise ValueError('Bước đang chạy. Tải lại sau khi bước kết thúc.')
        if next_step(layout.manifest.state) is None:
            raise ValueError('Project không có bước có thể thử lại; giữ nguyên cổng duyệt.')
        # Validate local inputs before releasing the hold. No provider calls here.
        rev = layout.artifact_root
        for relative, model in (('script/script.yaml', Script), ('storyboard/storyboard.yaml', Storyboard)):
            path = inside(rev, rev / relative)
            if path.is_file():
                model.model_validate(read_yaml(path))
        manifest = inside(rev, rev / 'assets/asset-manifest.yaml')
        if manifest.is_file():
            validate_asset_manifest(rev, load_asset_manifest(manifest))
        approval = latest_approval(layout.project_dir, GateKind.MEDICAL)
        if approval is not None and approval_is_stale(layout.project_dir, layout.manifest, GateKind.MEDICAL):
            raise ValueError('Tệp đã duyệt y khoa đã đổi; bác sĩ phải mở lại cổng y khoa.')
        if next_step(layout.manifest.state) == 'produce':
            from healthvideo.workflows.produce import (
                _ensure_v2_medical_approval_current,
            )

            _ensure_v2_medical_approval_current(rev)
        api = _retry_api()
        if api is None:
            raise ValueError('API retry chưa sẵn sàng; chưa thay đổi trạng thái.')
        inside(root, log_dir / 'production-retry.yaml')
        agent_hold = log_dir / AGENT_RETRY_FILE
        blocked_note = log_dir / 'blocked.txt'
        inside(root, agent_hold)
        inside(root, blocked_note)
        retry = api.retry_status(root, layout.project_dir, layout.manifest.state)
        if not allow_repair_release and retry.get('kind') == 'validation' and not retry.get('allowed'):
            raise ValueError(retry.get('reason') or 'Sửa đầu vào trước khi thử lại.')
        api.clear_retry(root, slug)
        agent_hold.unlink(missing_ok=True)
        blocked_note.unlink(missing_ok=True)
        if allow_repair_release:
            repair_path = inside(root, log_dir / 'leader-repair.yaml')
            if repair_path.is_file():
                try:
                    repair_data = read_yaml(repair_path)
                except (OSError, TypeError, ValueError, yaml.YAMLError):
                    repair_data = {}
                if isinstance(repair_data, dict) and repair_data.get('phase') in {
                    'needs_attention',
                    'repair_failed',
                }:
                    repair_path.unlink(missing_ok=True)
        factory.wake_background(root)
        return project_operations(root, slug)


def reopen_project(root: Path, slug: str, *, expected_revision: str, reviewer: str,
                   reason: str, changed: list[str], limiter, pin: str = '') -> dict:
    from healthvideo.workflows.dashboard import pin_path, reviewer_name, verify_pin

    reviewer = reviewer_name() or reviewer
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError('Nhập tên bác sĩ xác nhận mở lại.')
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('Nhập lý do mở lại.')
    if not isinstance(changed, list) or not all(isinstance(p, str) for p in changed):
        raise ValueError('Danh sách tệp thay đổi không hợp lệ.')
    with _MUTATION_LOCK:
        layout = _editable(root, slug, expected_revision)
        pin_file = pin_path()
        if not pin_file.is_file():
            raise ValueError('Chưa đặt PIN; chạy healthvideo review set-pin một lần.')
        limiter.check(pin, lambda value: verify_pin(value, path=pin_file))
        record = reopen_gate(layout.project_dir, GateKind.MEDICAL, reviewer=reviewer.strip(),
                             reason=reason.strip(), changed=changed, resume_state=WorkflowState.DRAFT_READY,
                             now=datetime.now().astimezone())
        return record.model_dump(mode='json')


def get_route(server, parts: list[str], query: dict) -> dict | bytes | None:
    from healthvideo.workflows import asset_library as library

    if parts == ['api', 'channel', 'browser-status']:
        from healthvideo.workflows import tiktok_browser
        return tiktok_browser.browser_status(server.root)

    if parts == ['api', 'channel', 'connections']:
        from healthvideo.workflows import channel_connections
        return channel_connections.connection_status(server.root)
    if len(parts) == 5 and parts[:3] == ['api', 'channel', 'oauth'] and parts[4] == 'callback':
        from healthvideo.workflows import channel_connections
        if any(len(v) != 1 for v in query.values()):
            raise ValueError('Duplicate OAuth parameters')
        return channel_connections.complete_connection(server.root, parts[3], {k: v[0] for k, v in query.items()})
    if parts == ['api', 'chat']:
        from healthvideo.workflows import chat

        return {'messages': chat.load(server.root, query.get('slug', [None])[0] or None)[-100:]}
    if parts == ['api', 'topics']:
        return {'entries': [e.model_dump(mode='json') for e in load_queue(server.root)]}
    if parts == ['api', 'research', 'inbox']:
        return {
            'summary': researcher.inbox_summary(server.root),
            'items': researcher.load_inbox(server.root),
        }
    if parts == ['api', 'channel']:
        return channel_analytics.channel_overview_payload(server.root)
    if parts == ['api', 'projects', 'deleted']:
        return {'items': list_deleted_projects(server.root)}
    if len(parts) == 4 and parts[:2] == ['api', 'project'] and parts[3] == 'operations':
        return project_operations(server.root, parts[2])
    if parts == ['api', 'library']:
        return {'items': library.list_assets(server.root, slug=query.get('slug', [None])[0] or None,
                                            kind=query.get('kind', [None])[0] or None,
                                            query=query.get('query', [''])[0])}
    if len(parts) == 4 and parts[0] == 'media' and parts[2] == 'library':
        item, _ = library.resolve_asset(server.root, parts[3])
        if item['slug'] != parts[1]:
            raise LookupError('Ảnh không thuộc project này.')
        return library.preview_asset(server.root, parts[3])
    return None


def post_route(server, parts: list[str], body: dict) -> dict | None:
    if len(parts) == 3 and parts[:2] == ['api', 'channel'] and parts[2] in {
        'configure', 'connect', 'disconnect', 'sync-api', 'publish-preview', 'publish', 'publish-status',
        'browser-install', 'browser-login', 'browser-disconnect',
    }:
        return _channel_post(server, parts[2], body)
    if parts in (['api', 'chat'], ['api', 'chat', 'confirm']):
        from healthvideo.workflows import chat

        allowed = {'slug', 'id'} if parts[-1] == 'confirm' else {'slug', 'text', 'context'}
        if set(body) - allowed:
            raise ValueError('Trường chat không hợp lệ; không nhận PIN.')
        if parts[-1] == 'confirm':
            return chat.confirm(server.root, body.get('slug') or None, body.get('id'))
        return chat.post(server.root, body.get('slug') or None, body.get('text'), body.get('context', {}))
    if len(parts) == 3 and parts[:2] == ['api', 'library']:
        return _library_post(server, parts[2], body)
    if parts == ['api', 'topics', 'add']:
        return add_topic(server.root, body)
    if parts == ['api', 'research', 'sync-sheet']:
        sheet_id = channel_analytics.parse_sheet_reference(body.get('sheet_url'))[0]
        return researcher.sync_reference_sheet(server.root, spreadsheet_id=sheet_id)
    if parts == ['api', 'research', 'discover']:
        return researcher.discover_topics_with_agent(
            server.root,
            query=str(body.get('query') or '').strip() or 'phòng bệnh thường gặp tại Việt Nam',
        )
    if parts == ['api', 'research', 'promote']:
        return researcher.promote_inbox_topic(
            server.root,
            str(body.get('slug') or ''),
            doctor_note=body.get('doctor_note'),
        )
    if parts == ['api', 'research', 'reject']:
        return researcher.reject_inbox_topic(
            server.root,
            str(body.get('slug') or ''),
            reason=str(body.get('reason') or ''),
        )
    if parts == ['api', 'channel', 'sync-sheet']:
        return channel_analytics.sync_channel_sheet(
            server.root,
            spreadsheet_id_or_url=body.get('sheet_url') or None,
            sheet_title=str(body.get('tab') or channel_analytics.CHANNEL_TAB_TITLE),
        )
    if parts == ['api', 'channel', 'import-csv']:
        return channel_analytics.import_channel_csv(
            server.root,
            str(body.get('csv_text') or ''),
            platform=str(body.get('platform') or 'youtube'),
        )
    if parts == ['api', 'channel', 'upsert']:
        return channel_analytics.upsert_video_metric(server.root, body)
    if parts == ['api', 'channel', 'analyze']:
        return channel_analytics.analyze_channel_performance(
            server.root, focus=str(body.get('question') or '')
        )
    if parts == ['api', 'channel', 'create-sheet']:
        return channel_analytics.create_channel_sheet(
            server.root,
            title=str(body.get('title') or 'PYH - Theo dõi Hiệu quả Kênh'),
        )
    if parts == ['api', 'jobs', 'cancel']:
        return {
            'cancelled': cancel_running_job(
                server.root,
                job_id=body.get('job_id'),
                slug=body.get('slug'),
                role=body.get('role'),
            )
        }
    if parts == ['api', 'projects', 'restore']:
        return restore_project(server.root, str(body.get('id', '')))
    if len(parts) == 4 and parts[:2] == ['api', 'project']:
        if parts[3] == 'pause':
            return pause_project(server.root, parts[2], reason=str(body.get('reason', '')))
        if parts[3] == 'resume':
            return resume_project(server.root, parts[2])
        if parts[3] == 'delete':
            return delete_project(
                server.root,
                parts[2],
                confirmed=body.get('confirmed') is True,
                reason=str(body.get('reason', '')),
            )
        if parts[3] == 'retry':
            return retry_project(
                server.root,
                parts[2],
                expected_revision=body.get('expected_revision'),
                allow_repair_release=bool(body.get('force')),
            )
        if parts[3] == 'reopen':
            if body.get('confirmed') is not True:
                raise ValueError('Bác sĩ cần xác nhận mở lại trên app.')
            return reopen_project(server.root, parts[2], expected_revision=body.get('expected_revision'),
                                  reviewer=body.get('reviewer'), reason=body.get('reason'), changed=body.get('changed'),
                                  limiter=server.limiter, pin=str(body.get('pin', '')))
    return None


def _library_post(server, action: str, body: dict) -> dict:
    from healthvideo.workflows import asset_library as library

    allowed = {
        'select': {'slug', 'expected_revision'},
        'import': {'slug', 'expected_revision', 'selection_id', 'origin', 'prompt', 'license', 'source_url'},
        'bind': {'slug', 'expected_revision', 'asset_id', 'scene_id'},
        'open': {'id', 'folder'},
    }
    if action not in allowed:
        raise LookupError('Không có thao tác thư viện này.')
    if set(body) - allowed[action]:
            raise ValueError('Chỉ nhận ID lựa chọn; không nhận đường dẫn từ trình duyệt.')
    if action == 'open':
        from healthvideo.workflows.dashboard import _open_path

        _, path = library.resolve_asset(server.root, body.get('id'))
        if not body.get('folder') and path.suffix.lower() == '.svg':
            raise ValueError('SVG chỉ xem thẻ an toàn hoặc mở thư mục.')
        _open_path(path.parent if body.get('folder') else path)
        return {'opened': True}
    layout = project_layout(server.root, body.get('slug', ''))
    if body.get('expected_revision') != layout.manifest.active_revision:
        raise ValueError('Revision đã thay đổi; tải lại.')
    if not hasattr(server, 'image_selections'):
        server.image_selections = library.ImageSelections()
    if action == 'select':
        return server.image_selections.select(layout.project_dir)
    if action == 'import':
        source = server.image_selections.consume(layout.project_dir, body.get('selection_id'))
        return library.import_image(layout.project_dir, source, origin=body.get('origin'), prompt=body.get('prompt'),
                                    license=body.get('license'), source_url=body.get('source_url'),
                                    now=datetime.now().astimezone())
    with _MUTATION_LOCK:
        _editable(server.root, body['slug'], body.get('expected_revision'))
        library.bind_image(layout.project_dir, body.get('asset_id'), body.get('scene_id'),
                           expected_revision=body.get('expected_revision'))
    return {'bound': True}


def _channel_post(server, action: str, body: dict) -> dict:
    from healthvideo.workflows import channel_connections as connections
    from healthvideo.workflows import channel_publishing as publishing

    platform = body.get('platform')
    if action in ('browser-install', 'browser-login', 'browser-disconnect'):
        from healthvideo.workflows import tiktok_browser
        if platform != 'tiktok' or set(body) != {'platform'}:
            raise ValueError('Only TikTok browser operation is supported; no session input accepted')
        operation = {'browser-install': tiktok_browser.install_backend,
                     'browser-login': tiktok_browser.begin_login,
                     'browser-disconnect': tiktok_browser.disconnect}[action]
        return operation(server.root)
    if action == 'configure':
        return connections.configure_connection(server.root, platform, {key: body[key] for key in ('client_id', 'client_secret', 'credentials_json') if key in body})
    if action == 'connect':
        redirect_uri = f'http://127.0.0.1:{server.server_address[1]}/api/channel/oauth/{platform}/callback'
        return connections.begin_connection(server.root, platform, redirect_uri=redirect_uri)
    if action == 'disconnect':
        return connections.disconnect_connection(server.root, platform)
    if action == 'sync-api':
        return channel_analytics.save_synced_metrics(server.root, connections.sync_connected_channel(server.root, platform))
    if action == 'publish-status':
        return publishing.publication_status(server.root, body.get('receipt_id'))
    allowed = {'slug', 'platform', 'clip_id', 'title_index'}
    if action == 'publish':
        allowed |= {'privacy', 'confirmed', 'music_usage_confirmed', 'noncommercial_confirmed', 'expected_account_id', 'expected_revision', 'expected_sha256'}
    if set(body) - allowed:
        raise ValueError('Only approved publication metadata is accepted')
    args = {'platform': platform, 'clip_id': body.get('clip_id'), 'title_index': body.get('title_index', 0)}
    if action == 'publish-preview':
        return publishing.publication_preview(server.root, body.get('slug'), **args)
    if body.get('confirmed') is not True:
        raise ValueError('Explicit per-video publication consent is required')
    if platform == 'tiktok' and (body.get('music_usage_confirmed') is not True or body.get('noncommercial_confirmed') is not True):
        raise ValueError('Confirm music rights and noncommercial content for this TikTok post')
    return publishing.publish_approved(server.root, body.get('slug'), privacy=body.get('privacy'),
        confirmed=body.get('confirmed') is True, music_usage_confirmed=body.get('music_usage_confirmed') is True,
        noncommercial_confirmed=body.get('noncommercial_confirmed') is True,
        expected_account_id=body.get('expected_account_id'),
        expected_revision=body.get('expected_revision'), expected_sha256=body.get('expected_sha256'), **args)
