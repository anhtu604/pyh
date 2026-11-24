"""Explicit, gate-bound channel publication with durable uncertain outcomes."""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryFile
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.posts import PostSet
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    sha256_file,
    write_text_atomic,
)
from healthvideo.workflows import package

YT_SCOPE = 'https://www.googleapis.com/auth/youtube.upload'
TT_BASE = 'https://open.tiktokapis.com/v2/post/publish/'


def _connections():
    from healthvideo.workflows import channel_connections
    return channel_connections


def _inside(base, path):
    path = path.resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError('Path outside approved project')
    return path


def _account(root, platform):
    status = _connections().connection_status(root)
    accounts = status.get('accounts', status)
    account = accounts.get(platform) if isinstance(accounts, dict) else next(
        (a for a in accounts if a.get('platform') == platform), None)
    if not account or not account.get('connected', True):
        raise ValueError('Channel is not connected')
    identity = account.get('account_id') or account.get('channel_id') or account.get('open_id')
    if not identity:
        raise ValueError('Connected account identity is missing')
    return {'id': identity, 'name': account.get('display_name', account.get('account_title', account.get('title', '')))}


def _validated(root, slug, platform, clip_id, title_index):
    from healthvideo.workflows.dashboard_operations import project_layout
    if platform not in ('youtube', 'tiktok'):
        raise ValueError('Unsupported platform')
    if clip_id is not None and (not isinstance(clip_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', clip_id)):
        raise ValueError('Invalid clip ID')
    if platform == 'tiktok' and not clip_id:
        raise ValueError('TikTok requires an approved clip')
    layout = project_layout(Path(root), slug)
    if layout.manifest.state is not WorkflowState.PACKAGED:
        raise ValueError('Publication requires packaged active revision')
    rev = layout.artifact_root
    # Constrain all gate inputs as well as the selected payload before gate hashing.
    for path in rev.rglob('*'):
        _inside(rev, path)
    approvals = {kind.value: package._ensure_v2_gate_approval(rev, kind)
                 for kind in (GateKind.MEDICAL, GateKind.VIDEO)}
    pub = _inside(rev, rev / 'publish')
    manifest = json.loads((pub / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('slug') != slug or manifest.get('approval_stale') is not False:
        raise ValueError('Invalid package identity')
    if manifest.get('approval_bindings') != {k: package._approval_binding(v) for k, v in approvals.items()}:
        raise ValueError('Package approval bindings changed')
    for name, digest in manifest.get('payload_sha256', {}).items():
        if sha256_file(_inside(pub, pub / name)) != digest:
            raise ValueError('Package payload hash changed')
    posts_data = read_yaml(pub / 'posts.yaml')
    package._require_approved_hash(approvals['video'], 'posts/posts.yaml', canonical_json_hash(posts_data))
    posts = PostSet.model_validate(posts_data)
    if type(title_index) is not int or not 0 <= title_index < len(posts.youtube_titles):
        raise ValueError('Invalid approved title index')
    relative = f'clips/{clip_id}.mp4' if clip_id else 'video.mp4'
    asset = _inside(pub, pub / relative)
    digest = sha256_file(asset)
    if manifest.get('payload_sha256', {}).get(relative) != digest:
        raise ValueError('Asset missing from package manifest')
    if clip_id:
        renders = json.loads((rev / 'renders/render-manifest.json').read_text(encoding='utf-8'))
        original = renders.get('clips', {}).get(clip_id)
        if not original:
            raise ValueError('Clip missing from approved render manifest')
        original = 'renders/' + original
    else:
        original = 'renders/video.mp4'
    package._require_approved_hash(approvals['video'], original, digest)
    caption = (getattr(posts.clip_captions[clip_id], 'tiktok' if platform == 'tiktok' else 'shorts')
               if clip_id else posts.youtube_description)
    public = {'platform': platform, 'slug': slug, 'revision': layout.manifest.active_revision,
              'clip_id': clip_id, 'sha256': digest, 'title': package.CLAIM_REF.sub('', posts.youtube_titles[title_index]),
              'caption': package.CLAIM_REF.sub('', caption), 'tags': list(posts.youtube_tags), 'gates_current': True, 'account': _account(root, platform)}
    if platform == 'youtube' and not clip_id and posts.thumbnail is not None:
        thumbnail = _inside(pub, pub / 'thumbnail.png')
        thumb_hash = sha256_file(thumbnail)
        if manifest.get('payload_sha256', {}).get('thumbnail.png') != thumb_hash:
            raise ValueError('Thumbnail missing from approved package')
        package._require_approved_hash(approvals['video'], 'posts/thumbnail.png', thumb_hash)
        public['thumbnail_sha256'] = thumb_hash
    return public, asset


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Provider redirect refused')


def urlopen(request, timeout):
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


def _request(method, url, *, token=None, body=None, headers=None):
    headers = dict(headers or {})
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if isinstance(body, dict):
        body = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json; charset=UTF-8'
    try:
        with urlopen(Request(url, data=body, headers=headers, method=method), timeout=60) as response:
            raw = response.read()
            try:
                data = json.loads(raw) if raw else {}
            except ValueError:
                if method != 'PUT':
                    raise
                data = {}
            return response.status, dict(response.headers), data
    except HTTPError as exc:
        if exc.code == 308:
            return 308, dict(exc.headers), {}
        raise RuntimeError(f'Provider HTTP {exc.code}; publication not confirmed') from None


def _tt(endpoint, token, body):
    _, _, result = _request('POST', TT_BASE + endpoint + '/', token=token, body=body)
    code = result.get('error', {}).get('code')
    if code != 'ok':
        raise RuntimeError('TikTok API error: ' + str(code or 'invalid_response'))
    return result['data']


def publication_preview(root, slug, platform, clip_id=None, title_index=0):
    result, _ = _validated(root, slug, platform, clip_id, title_index)
    if platform == 'tiktok':
        authorization = _connections().authorized_account(root, platform, required_scopes=('video.publish',))
        if authorization['account_id'] != result['account']['id']:
            raise ValueError('Connected account changed during preview')
        if authorization.get('connection_method') == 'browser_session':
            result.update(connection_method='browser_session', privacy_options=['private', 'public'],
                          constraints={'experimental_browser_session': True, 'per_video_consent_required': True,
                                       'music_rights_confirmation_required': True, 'noncommercial_only': True})
            return result
        token = authorization['access_token']
        result['creator_info'] = _tt('creator_info/query', token, {})
        result['constraints'] = {'unaudited_private_only': True, 'internal_utility_audit_eligible': False,
                                 'per_video_consent_required': True, 'music_rights_confirmation_required': True,
                                 'noncommercial_only': True}
        result['privacy_options'] = [v for v in result['creator_info'].get('privacy_level_options', []) if v == 'SELF_ONLY']
    else:
        result['privacy_options'] = ['private', 'unlisted', 'public']
    result['connection_method'] = 'oauth'
    return result


def _receipt_path(root, key):
    base = Path(root) / 'topics/channel-publications'
    base.mkdir(parents=True, exist_ok=True)
    return _inside(Path(root), base / (key + '.json'))


@contextmanager
def _lock(path):
    lock = path.with_suffix('.lock')
    try:
        handle = lock.open('x')
    except FileExistsError:
        raise ValueError('Publication already in progress; reconcile existing receipt') from None
    try:
        yield
    finally:
        handle.close()
        lock.unlink()


def _save(path, receipt):
    write_text_atomic(path, json.dumps(receipt, ensure_ascii=False))
    return receipt


def _safe_upload_url(url, platform):
    parsed = urlparse(url)
    host = parsed.hostname or ''
    allowed = (host == 'www.googleapis.com' or host.endswith('.googleapis.com')) if platform == 'youtube' else (
        host.endswith(('.tiktokapis.com', '.tiktok.com')))
    if parsed.scheme != 'https' or not allowed or parsed.username or parsed.password:
        raise ValueError('Invalid provider upload endpoint')
    return url


def _duration(asset):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                             '-of', 'json', str(asset)], capture_output=True, check=True, timeout=30)
    duration = float(json.loads(result.stdout)['format']['duration'])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Invalid video duration')
    return duration


def _snapshot(asset, expected_hash):
    stream = TemporaryFile()  # noqa: SIM115 - ownership transfers to upload context
    digest = hashlib.sha256()
    try:
        with asset.open('rb') as source:
            while chunk := source.read(8 * 1024 * 1024):
                digest.update(chunk)
                stream.write(chunk)
        if digest.hexdigest() != expected_hash:
            raise ValueError('Approved asset changed before upload')
        stream.seek(0)
        return stream
    except (OSError, ValueError):
        stream.close()
        raise


def _thumbnail_bytes(preview, asset):
    digest = preview.get('thumbnail_sha256')
    if not digest:
        return None
    with _snapshot(asset.parent / 'thumbnail.png', digest) as stream:
        return stream.read()


def _finish_thumbnail(root, path, receipt, *, data=None, token=None):
    if receipt.get('thumbnail_status') in ('uploaded', 'not_applicable'):
        return receipt
    fresh, asset = _validated(root, receipt['slug'], 'youtube', receipt.get('clip_id'), receipt.get('title_index', 0))
    for key in ('revision', 'sha256', 'account', 'thumbnail_sha256'):
        if fresh.get(key) != receipt.get(key):
            raise ValueError('Approved thumbnail package or account changed; cannot retry')
    if not receipt.get('thumbnail_sha256'):
        receipt['thumbnail_status'] = 'not_applicable'
        return _save(path, receipt)
    data = data if data is not None else _thumbnail_bytes(fresh, asset)
    authorization = _connections().authorized_account(root, 'youtube', required_scopes=(YT_SCOPE,))
    if authorization['account_id'] != receipt['account']['id']:
        raise ValueError('Connected account changed before thumbnail upload')
    try:
        status, _, result = _request('POST', 'https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId='
                 + receipt['video_id'] + '&uploadType=media', token=authorization['access_token'],
                 body=data, headers={'Content-Type': 'image/png'})
        if status != 200 or not result.get('items'):
            raise ValueError('Thumbnail acknowledgement missing')
        receipt['thumbnail_status'] = 'uploaded'
        receipt.pop('thumbnail_error', None)
    except Exception:  # noqa: BLE001 - preserve confirmed video; redact provider failures
        receipt.update(thumbnail_status='failed', thumbnail_error='Thumbnail upload failed; check status to retry thumbnail only')
    return _save(path, receipt)


def publish_approved(root, slug, *, platform, clip_id=None, privacy=None, title_index=0,
                     confirmed=False, music_usage_confirmed=False, noncommercial_confirmed=False,
                     expected_account_id=None, expected_revision=None, expected_sha256=None):
    if confirmed is not True:
        raise ValueError('Explicit per-video publication consent is required')
    if platform == 'tiktok' and (music_usage_confirmed is not True or noncommercial_confirmed is not True):
        raise ValueError('Confirm music rights and noncommercial content for this TikTok post')
    preview, asset = _validated(root, slug, platform, clip_id, title_index)
    if expected_revision != preview['revision'] or expected_sha256 != preview['sha256']:
        raise ValueError('Approved revision or video changed since preview; preview again')
    if expected_account_id != preview['account']['id']:
        raise ValueError('Account changed since preview; preview again')
    if privacy is None:
        raise ValueError('Explicit visibility selection is required')
    scope = YT_SCOPE if platform == 'youtube' else 'video.publish'
    authorization = _connections().authorized_account(root, platform, required_scopes=(scope,))
    if authorization['account_id'] != preview['account']['id']:
        raise ValueError('Connected account changed before authorization')
    browser = authorization.get('connection_method') == 'browser_session'
    token = authorization.get('access_token')
    creator = None
    if platform == 'youtube':
        if privacy not in ('private', 'unlisted', 'public'):
            raise ValueError('Invalid YouTube privacy')
    elif browser:
        if privacy not in ('private', 'public'):
            raise ValueError('Invalid TikTok browser visibility')
    else:
        creator = _tt('creator_info/query', token, {})
        if privacy != 'SELF_ONLY':
            raise ValueError('Unaudited internal integration supports private TikTok tests only')
        if privacy not in creator.get('privacy_level_options', []):
            raise ValueError('Visibility is not permitted by creator settings')
        if _duration(asset) > creator.get('max_video_post_duration_sec', 0):
            raise ValueError('Clip exceeds creator duration limit')
    identity = {k: preview[k] for k in ('platform', 'slug', 'revision', 'clip_id', 'sha256', 'account')}
    dedup = {**identity, 'account': preview['account']['id']}
    key = hashlib.sha256(json.dumps(dedup, sort_keys=True).encode()).hexdigest()
    path = _receipt_path(root, key)
    with _lock(path):
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
        # Revalidate both gates immediately before recording the remote intent.
        fresh, _ = _validated(root, slug, platform, clip_id, title_index)
        if fresh != preview:
            raise ValueError('Approved package or channel changed; preview again')
        stream = _snapshot(asset, preview['sha256'])
        thumbnail_data = _thumbnail_bytes(preview, asset)
        if _account(root, platform)['id'] != preview['account']['id']:
            stream.close()
            raise ValueError('Connected account changed before upload')
        receipt = {**identity, 'receipt_id': key, 'privacy': privacy, 'status': 'needs_reconciliation'}
        receipt.update(title_index=title_index, connection_method='browser_session' if browser else 'oauth')
        if platform == 'youtube':
            receipt.update(thumbnail_sha256=preview.get('thumbnail_sha256'),
                           thumbnail_status='pending' if thumbnail_data is not None else 'not_applicable')
        _save(path, receipt)  # Durable intent precedes every remote mutation.
        try:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(0)
            receipt['file_size'] = size
            _save(path, receipt)
            if not size:
                raise ValueError('Empty video')
            if browser:
                from healthvideo.workflows import tiktok_browser
                result = tiktok_browser.upload_snapshot(stream, sha256=preview['sha256'],
                    caption=preview['caption'], privacy=privacy, authorization=authorization)
                receipt.update(result, status='pending_verification',
                               guidance='Check the TikTok profile in your browser. Acceptance does not confirm publication; do not resend blindly.')
                stream.close()
                return _save(path, receipt)
            if platform == 'youtube':
                _, headers, _ = _request('POST', 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status',
                    token=token, body={'snippet': {'title': preview['title'], 'description': preview['caption'], 'tags': preview['tags']},
                                      'status': {'privacyStatus': privacy}},
                    headers={'X-Upload-Content-Length': str(size), 'X-Upload-Content-Type': 'video/mp4'})
                url = _safe_upload_url(next(v for k, v in headers.items() if k.lower() == 'location'), platform)
                chunk_size = 8 * 1024 * 1024
            else:
                chunk_size = min(size, 10 * 1024 * 1024)
                count = max(1, size // chunk_size)
                if size > 4 * 1024 ** 3 or count > 1000:
                    raise ValueError('Video exceeds TikTok transfer limits')
                data = _tt('video/init', token, {'post_info': {'title': preview['caption'], 'privacy_level': privacy,
                    'disable_duet': True, 'disable_stitch': True, 'disable_comment': True},
                    'source_info': {'source': 'FILE_UPLOAD', 'video_size': size, 'chunk_size': chunk_size, 'total_chunk_count': count}})
                receipt['publish_id'] = data['publish_id']
                _save(path, receipt)
                url = _safe_upload_url(data['upload_url'], platform)
            _connections().store_publication_secret(root, key, url)
            with stream:
                offset = 0
                while offset < size:
                    # TikTok merges the final remainder into the last full chunk.
                    amount = size - offset if platform == 'tiktok' and size - offset < 2 * chunk_size else chunk_size
                    chunk = stream.read(amount)
                    status, _, result = _request('PUT', url, token=token if platform == 'youtube' else None,
                        body=chunk, headers={'Content-Type': 'video/mp4', 'Content-Length': str(len(chunk)),
                        'Content-Range': f'bytes {offset}-{offset + len(chunk) - 1}/{size}'})
                    offset += len(chunk)
                    if platform == 'youtube' and offset < size and status != 308:
                        raise RuntimeError('Unexpected upload acknowledgement')
            if platform == 'youtube':
                if status not in (200, 201) or not result.get('id'):
                    raise RuntimeError('YouTube upload completion not confirmed')
                receipt.update(status='posted', video_id=result['id'])
                _save(path, receipt)  # Video confirmation survives thumbnail/network failure.
                return _finish_thumbnail(root, path, receipt, data=thumbnail_data, token=token)
            else:
                receipt['status'] = 'pending'
                _save(path, receipt)
                return publication_status(root, key)
        except (OSError, ValueError, RuntimeError, KeyError, StopIteration) as exc:
            stream.close()
            if browser:
                from healthvideo.workflows import tiktok_browser
                if isinstance(exc, tiktok_browser.SessionExpired):
                    tiktok_browser.invalidate_session(root, preview['account']['id'])
            # Never expose provider bodies, bearer URLs, tokens or arbitrary exception text.
            receipt['error'] = 'Lượt đăng bị gián đoạn; kiểm tra trạng thái trước khi thử lại.'
        return _save(path, receipt)


def publication_status(root, receipt_id):
    if not isinstance(receipt_id, str) or not re.fullmatch('[a-f0-9]{64}', receipt_id):
        raise ValueError('Invalid receipt ID')
    path = _receipt_path(root, receipt_id)
    receipt = json.loads(path.read_text(encoding='utf-8'))
    if _account(root, receipt['platform'])['id'] != receipt['account']['id']:
        raise ValueError('Connected account changed')
    if receipt.get('connection_method') == 'browser_session':
        return receipt
    if receipt['platform'] == 'youtube' and receipt['status'] == 'posted':
        with _lock(path):
            return _finish_thumbnail(root, path, receipt)
    if receipt['platform'] == 'youtube' and receipt['status'] == 'needs_reconciliation':
        url = _connections().load_publication_secret(root, receipt_id)
        if not url:
            return receipt
        authorization = _connections().authorized_account(root, 'youtube', required_scopes=(YT_SCOPE,))
        if authorization['account_id'] != receipt['account']['id']:
            raise ValueError('Connected account changed')
        token = authorization['access_token']
        status, _, data = _request('PUT', _safe_upload_url(url, 'youtube'), token=token, body=b'',
                                   headers={'Content-Length': '0', 'Content-Range': f"bytes */{receipt['file_size']}"})
        if status in (200, 201) and data.get('id'):
            receipt.update(status='posted', video_id=data['id'])
            _save(path, receipt)
            return _finish_thumbnail(root, path, receipt)
        return receipt
    if receipt['platform'] == 'tiktok' and receipt.get('publish_id'):
        authorization = _connections().authorized_account(root, 'tiktok', required_scopes=('video.publish',))
        if authorization['account_id'] != receipt['account']['id']:
            raise ValueError('Connected account changed')
        token = authorization['access_token']
        data = _tt('status/fetch', token, {'publish_id': receipt['publish_id']})
        state = data.get('status')
        receipt['provider_status'] = state
        receipt['status'] = 'posted' if state == 'PUBLISH_COMPLETE' else 'failed' if state == 'FAILED' else 'pending'
        if state == 'FAILED':
            receipt['failure_reason'] = data.get('fail_reason')
        return _save(path, receipt)
    return receipt
