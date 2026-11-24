"""Dashboard opt-in, transition-only publication; never scan old work for uploads."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml, write_text_atomic
from healthvideo.workflows import channel_publishing as publishing

SETTINGS = 'topics/auto-publish.json'
EVENTS = 'topics/auto-publications'
ERROR = 'Chưa đăng được. Kiểm tra kết nối và gói duyệt, rồi bấm Thử đăng lại.'
UNCERTAIN = 'Chưa xác định kết quả. Kiểm tra trạng thái trước khi đăng lại; không tự gửi lại.'


def _now():
    return datetime.now(UTC)


def load_settings(root):
    path = Path(root) / SETTINGS
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {
        'youtube_enabled': False, 'youtube_privacy': 'public',
    }


def save_settings(root, body):
    """Called only by the authenticated dashboard POST, never by an agent step."""
    if set(body) != {'youtube_enabled', 'youtube_privacy'} or type(body['youtube_enabled']) is not bool:
        raise ValueError('Cài đặt tự động đăng không hợp lệ.')
    if body['youtube_privacy'] not in ('public', 'unlisted', 'private'):
        raise ValueError('Chọn quyền hiển thị YouTube hợp lệ.')
    path = Path(root) / SETTINGS
    path.parent.mkdir(parents=True, exist_ok=True)
    with publishing._lock(path):
        old = load_settings(root)
        settings = {**old, **body}
        if body['youtube_enabled']:
            account = publishing._account(root, 'youtube')
            auth = publishing._connections().authorized_account(root, 'youtube', required_scopes=(publishing.YT_SCOPE,))
            if auth['account_id'] != account['id']:
                raise ValueError('Kênh YouTube đã thay đổi. Hãy kiểm tra kết nối.')
            if not old['youtube_enabled'] or old.get('account') != account:
                settings['enabled_since'] = _now().isoformat()
            settings['account'] = account
        write_text_atomic(path, json.dumps(settings, ensure_ascii=False))
    return settings


def _event_path(root, event_id):
    if not isinstance(event_id, str) or not re.fullmatch('[a-f0-9]{64}', event_id):
        raise ValueError('Việc đăng không hợp lệ.')
    return Path(root) / EVENTS / (event_id + '.json')


def _save(path, item):
    write_text_atomic(path, json.dumps(item, ensure_ascii=False))


def _send_youtube(root, item):
    expected = item['youtube_preview']
    return publishing.publish_approved(root, item['slug'], platform='youtube',
        privacy=item['privacy'], confirmed=True,
        expected_account_id=expected['account']['id'], expected_revision=expected['revision'],
        expected_sha256=expected['sha256'])


def on_packaged(root, slug):
    """Best effort hook called only after the existing packaging transition succeeds."""
    try:
        _on_packaged(Path(root), slug)
    except Exception:  # noqa: BLE001 - publication/storage failure cannot undo packaging
        # No arbitrary exceptions in logs: provider/OS errors may contain secrets.
        return


def _on_packaged(root, slug):
    from healthvideo.workflows.dashboard_operations import project_layout

    settings = load_settings(root)
    if not settings['youtube_enabled']:
        return
    layout = project_layout(root, slug)
    if layout.manifest.state is not WorkflowState.PACKAGED:
        return
    event_id = hashlib.sha256(f'{slug}:{layout.manifest.active_revision}'.encode()).hexdigest()
    path = _event_path(root, event_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with publishing._lock(path):
        if path.exists():
            return  # Restart/repeated hooks never initiate another attempt.
        item = {'id': event_id, 'slug': slug, 'revision': layout.manifest.active_revision,
                'privacy': settings['youtube_privacy'], 'account': settings['account'],
                'youtube': {'status': 'not_started'}, 'tiktok': []}
        try:
            approval = read_yaml(layout.artifact_root / 'reviews/video-approval.yaml')
            if datetime.fromisoformat(str(approval['reviewed_at'])) < datetime.fromisoformat(settings['enabled_since']):
                return  # No backfill, including old approvals packaged after opt-in.
            preview, _ = publishing._validated(root, slug, 'youtube', None, 0)
            if preview['account']['id'] != settings['account']['id']:
                raise ValueError('Account changed')
            item['youtube_preview'] = preview
            # Prepare TikTok offline. Creator info is refreshed on explicit preview POST.
            manifest = json.loads((layout.artifact_root / 'publish/manifest.json').read_text(encoding='utf-8'))
            for name in manifest.get('payload_sha256', {}):
                match = re.fullmatch(r'clips/([A-Za-z0-9_-]{1,80})\.mp4', name)
                if match:
                    try:
                        clip, _ = publishing._validated(root, slug, 'tiktok', match[1], 0)
                        item['tiktok'].append(clip)
                    except (OSError, ValueError, KeyError):
                        item['tiktok_error'] = 'Chưa chuẩn bị được TikTok. Kiểm tra kết nối và gói clip.'
            item['youtube'] = {'status': 'needs_reconciliation', 'message': UNCERTAIN}
            _save(path, item)  # Durable local attempt precedes publisher/network.
            item['youtube'] = _send_youtube(root, item)
        except Exception:  # noqa: BLE001 - redact, preserve project and approvals
            item['youtube'] = {'status': 'error', 'message': ERROR}
        _save(path, item)


def retry_youtube(root, event_id):
    """Explicit doctor retry; publisher's receipt lock still forbids blind re-upload."""
    path = _event_path(root, event_id)
    with publishing._lock(path):
        item = json.loads(path.read_text(encoding='utf-8'))
        if 'youtube_preview' not in item:
            # A preflight failure may be fixed, but cannot silently change the opted-in account.
            preview, _ = publishing._validated(root, item['slug'], 'youtube', None, 0)
            if preview['account']['id'] != item['account']['id'] or preview['revision'] != item['revision']:
                raise ValueError('Gói hoặc kênh đã thay đổi. Hãy xem trước lại trong tab Kênh.')
            item['youtube_preview'] = preview
        try:
            item['youtube'] = _send_youtube(root, item)
        except Exception:  # noqa: BLE001 - no provider exception text in dashboard
            item['youtube'] = {'status': 'error', 'message': ERROR}
        _save(path, item)
        return item['youtube']


def overview(root):
    """Read local state only. Opening overview must never query a provider."""
    root = Path(root)
    receipts = []
    for path in (root / 'topics/channel-publications').glob('*.json'):
        try:
            receipts.append(json.loads(path.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            continue
    items = []
    for path in (root / EVENTS).glob('*.json'):
        try:
            item = json.loads(path.read_text(encoding='utf-8'))
            project = read_yaml(root / 'projects' / item['slug'] / 'project.yaml')
            if project['state'] != 'packaged' or project['active_revision'] != item['revision']:
                continue
            for preview in [item.get('youtube_preview'), *item['tiktok']]:
                if not preview:
                    continue
                receipt = next((r for r in receipts if all(r.get(k) == preview.get(k)
                    for k in ('slug', 'revision', 'platform', 'clip_id', 'sha256'))
                    and r.get('account', {}).get('id') == preview['account']['id']), None)
                if receipt:
                    if preview['platform'] == 'youtube':
                        item['youtube'] = receipt
                    else:
                        preview['receipt'] = receipt
            items.append(item)
        except (OSError, ValueError, KeyError):
            continue
    return {'settings': load_settings(root), 'items': items}
