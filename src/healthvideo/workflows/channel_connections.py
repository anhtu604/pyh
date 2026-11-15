"""Local desktop OAuth. Provider credentials never enter project files."""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import secrets
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

_LOCK = threading.RLock()
SCOPES = {
    'youtube': ('https://www.googleapis.com/auth/youtube.readonly',
                'https://www.googleapis.com/auth/youtube.upload',
                'https://www.googleapis.com/auth/yt-analytics.readonly'),
    'tiktok': ('user.info.basic', 'video.list', 'video.publish'),
}
TOKEN_URL = {'youtube': 'https://oauth2.googleapis.com/token',
             'tiktok': 'https://open.tiktokapis.com/v2/oauth/token/'}


class ConnectionError(ValueError):
    """Safe public error, with no provider response or credentials."""


def _platform(platform):
    if platform not in SCOPES:
        raise ConnectionError('Unsupported channel platform')
    return platform


def _dpapi(data, decrypt=False):
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    result = Blob()
    function = (ctypes.windll.crypt32.CryptUnprotectData if decrypt
                else ctypes.windll.crypt32.CryptProtectData)
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ConnectionError('Cannot protect local channel credentials')
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.windll.kernel32.LocalFree(result.data)


class SecretStore:
    def __init__(self, root):
        namespace = hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share'))
        self.path = base / 'HealthVideo' / 'channels' / (namespace + '.bin')

    def read(self):
        if not self.path.exists():
            return {}
        try:
            raw = self.path.read_bytes()
            return json.loads(_dpapi(raw, True) if os.name == 'nt' else raw)
        except Exception:  # noqa: BLE001 - secrets must never escape through provider errors
            raise ConnectionError('Cannot read local channel credentials') from None

    def write(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        raw = json.dumps(value).encode()
        if os.name == 'nt':
            raw = _dpapi(raw)
        temporary = self.path.with_suffix('.' + secrets.token_hex(8) + '.tmp')
        try:
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(raw)
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)


_store = SecretStore


def _http(method, url, *, form=None, json_body=None, token=None):
    headers = {'Accept': 'application/json'}
    data = None
    if form is not None:
        data = urlencode(form).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    try:
        with urlopen(Request(url, data=data, headers=headers, method=method), timeout=25) as response:
            result = json.loads(response.read(8_000_000))
        if not isinstance(result, dict):
            raise TypeError()
        error = result.get('error')
        if error and (not isinstance(error, dict) or error.get('code') != 'ok'):
            raise ValueError()
        return result
    except Exception:  # noqa: BLE001 - public transport boundary redacts all provider details
        raise ConnectionError('Channel provider request failed; check app setup or reconnect') from None


def _status(entry, platform):
    browser = entry.get('browser_session') if platform == 'tiktok' else None
    if browser:
        expired = bool(browser.get('needs_reauth') or browser.get('expires_at') is not None
                       and browser['expires_at'] <= time.time())
        return {'configured': True, 'connected': True, 'account_id': browser['account_id'],
                'account_title': 'TikTok · phiên ' + browser['account_id'][-12:],
                'can_sync': False, 'can_publish': not expired, 'needs_reauth': expired,
                'last_verified_at': browser.get('last_verified_at'), 'expires_at': browser.get('expires_at'),
                'connection_method': 'browser_session', 'identity_source': 'session_cookie'}
    token = entry.get('token', {})
    scopes = set(token.get('scopes', []))
    connected = bool(entry.get('account_id') and token.get('access_token'))
    usable = connected and not entry.get('needs_reauth') and (
        token.get('expires_at', 0) > time.time() + 60 or bool(token.get('refresh_token')))
    sync = SCOPES[platform][0 if platform == 'youtube' else 1]
    publish = SCOPES[platform][1 if platform == 'youtube' else 2]
    return {'configured': bool(entry.get('client_id')), 'connected': connected, 'connection_method': 'oauth',
            'account_id': entry.get('account_id'), 'account_title': entry.get('account_title'),
            'can_sync': bool(usable and sync in scopes),
            'can_publish': bool(usable and publish in scopes),
            'needs_reauth': bool(connected and not usable or entry.get('needs_reauth'))}


def connection_status(root: Path):
    with _LOCK:
        data = _store(root).read()
        return {p: _status(data.get(p, {}), p) for p in SCOPES}


def configure_connection(root: Path, platform: str, body: dict):
    _platform(platform)
    try:
        credentials = body
        if platform == 'youtube' and body.get('credentials_json'):
            downloaded = body['credentials_json']
            if isinstance(downloaded, str):
                downloaded = json.loads(downloaded)
            credentials = downloaded['installed']
        client_id = credentials['client_id'].strip()
        client_secret = credentials.get('client_secret', '').strip()
        if not client_id or not client_secret or len(client_id) > 4096 or len(client_secret) > 4096:
            raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ConnectionError('Valid desktop app client ID and secret are required') from None
    with _LOCK:
        store = _store(root)
        data = store.read()
        data[platform] = {'client_id': client_id, 'client_secret': client_secret}
        store.write(data)
        return _status(data[platform], platform)


def begin_connection(root: Path, platform: str, redirect_uri: str):
    _platform(platform)
    try:
        uri = urlsplit(redirect_uri)
        valid = (uri.scheme == 'http' and uri.hostname in ('127.0.0.1', 'localhost', '::1')
                 and uri.port and uri.path == f'/api/channel/oauth/{platform}/callback'
                 and not uri.query and not uri.fragment and not uri.username and not uri.password)
        if not valid:
            raise ValueError()
    except (TypeError, ValueError, AttributeError):
        raise ConnectionError('OAuth redirect must use the local callback URL') from None
    with _LOCK:
        store = _store(root)
        data = store.read()
        entry = data.get(platform, {})
        if not entry.get('client_id'):
            raise ConnectionError('Configure a desktop OAuth app first')
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        entry['pending'] = {'state': state, 'verifier': verifier,
                            'redirect_uri': redirect_uri, 'created_at': time.time()}
        digest = hashlib.sha256(verifier.encode()).digest()
        challenge = (base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
                     if platform == 'youtube' else digest.hex())
        query = {'response_type': 'code', 'state': state, 'redirect_uri': redirect_uri,
                 'scope': (' ' if platform == 'youtube' else ',').join(SCOPES[platform]),
                 'code_challenge': challenge, 'code_challenge_method': 'S256'}
        query['client_id' if platform == 'youtube' else 'client_key'] = entry['client_id']
        if platform == 'youtube':
            query.update(access_type='offline', prompt='consent')
        data[platform] = entry
        store.write(data)
        base = ('https://accounts.google.com/o/oauth2/v2/auth' if platform == 'youtube'
                else 'https://www.tiktok.com/v2/auth/authorize/')
        return {'authorization_url': base + '?' + urlencode(query), 'redirect_uri': redirect_uri}


def _token(result, previous=None):
    if not isinstance(result.get('access_token'), str) or not result['access_token']:
        raise ConnectionError('Provider did not grant an access token')
    previous = previous or {}
    scope = result.get('scope')
    scopes = (scope.replace(',', ' ').split() if isinstance(scope, str)
              else previous.get('scopes', []))
    try:
        expiry = max(0, int(result.get('expires_in', 0)))
    except (ValueError, TypeError):
        raise ConnectionError('Provider token expiry invalid') from None
    return {'access_token': result['access_token'],
            'refresh_token': result.get('refresh_token', previous.get('refresh_token')),
            'expires_at': time.time() + expiry, 'scopes': scopes}


def complete_connection(root: Path, platform: str, params: dict):
    _platform(platform)
    with _LOCK:
        store = _store(root)
        data = store.read()
        entry = data.get(platform, {})
        pending = entry.get('pending', {})
        state = params.get('state')
        if (not isinstance(state, str) or not pending or
                not secrets.compare_digest(state, pending['state']) or
                not 0 <= time.time() - pending['created_at'] <= 600):
            raise ConnectionError('OAuth state invalid or expired; start connection again')
        entry.pop('pending')
        store.write(data)
        if params.get('error'):
            raise ConnectionError('Channel authorization was declined')
        code = params.get('code')
        if not isinstance(code, str) or not code:
            raise ConnectionError('Authorization code missing')
        form = {'grant_type': 'authorization_code', 'code': code,
                'redirect_uri': pending['redirect_uri'], 'code_verifier': pending['verifier'],
                'client_secret': entry['client_secret']}
        form['client_id' if platform == 'youtube' else 'client_key'] = entry['client_id']
        token = _token(_http('POST', TOKEN_URL[platform], form=form))
        if platform == 'youtube':
            account = _http('GET', 'https://www.googleapis.com/youtube/v3/channels?' +
                            urlencode({'part': 'snippet', 'mine': 'true'}), token=token['access_token'])
            items = account.get('items', [])
            if not items or not items[0].get('id'):
                raise ConnectionError('No YouTube channel found for this account')
            account_id, title = items[0]['id'], items[0].get('snippet', {}).get('title', '')
        else:
            account = _http('GET', 'https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name',
                            token=token['access_token']).get('data', {}).get('user', {})
            account_id, title = account.get('open_id'), account.get('display_name', '')
            if not account_id:
                raise ConnectionError('TikTok account verification failed')
        entry.update(token=token, account_id=account_id, account_title=title, needs_reauth=False)
        store.write(data)
        return _status(entry, platform)


def access_token(root: Path, platform: str, required_scopes: tuple[str, ...] = ()) -> str:
    _platform(platform)
    with _LOCK:
        store = _store(root)
        data = store.read()
        entry = data.get(platform, {})
        if platform == 'tiktok' and entry.get('browser_session'):
            raise ConnectionError('Browser session does not support OAuth analytics')
        token = entry.get('token', {})
        if not entry.get('account_id') or not token.get('access_token') or entry.get('needs_reauth'):
            raise ConnectionError('Connect the channel first')
        if not set(required_scopes).issubset(token.get('scopes', [])):
            raise ConnectionError('Required permission missing; reconnect the channel')
        if token.get('expires_at', 0) <= time.time() + 60:
            if not token.get('refresh_token'):
                raise ConnectionError('Channel authorization expired; reconnect')
            form = {'grant_type': 'refresh_token', 'refresh_token': token['refresh_token'],
                    'client_secret': entry['client_secret']}
            form['client_id' if platform == 'youtube' else 'client_key'] = entry['client_id']
            try:
                token = _token(_http('POST', TOKEN_URL[platform], form=form), token)
            except Exception:  # noqa: BLE001 - redact provider errors and mark reauthorization
                entry['needs_reauth'] = True
                store.write(data)
                raise ConnectionError('Channel refresh failed; reconnect') from None
            entry['token'] = token
            store.write(data)
            if not set(required_scopes).issubset(token['scopes']):
                raise ConnectionError('Required permission missing; reconnect the channel')
        return token['access_token']


def authorized_account(root: Path, platform: str, required_scopes: tuple[str, ...] = ()):
    """Internal account/token snapshot; never serialize into a browser response."""
    with _LOCK:
        _platform(platform)
        entry = _store(root).read().get(platform, {})
        browser = entry.get('browser_session') if platform == 'tiktok' else None
        if browser:
            if _status(entry, platform)['needs_reauth']:
                raise ConnectionError('TikTok session expired; reconnect')
            if set(required_scopes) - {'video.publish'}:
                raise ConnectionError('Browser session does not support OAuth analytics')
            return {**browser, 'connection_method': 'browser_session',
                    'account_title': 'TikTok · UID ' + browser['account_id']}
        token = access_token(root, platform, required_scopes)
        entry = _store(root).read()[platform]
        return {'account_id': entry['account_id'],
                'account_title': entry.get('account_title', ''), 'access_token': token}


def disconnect_connection(root: Path, platform: str):
    _platform(platform)
    with _LOCK:
        store = _store(root)
        data = store.read()
        entry = data.get(platform, {})
        token = entry.get('token', {}).get('access_token')
        data[platform] = {k: v for k, v in entry.items() if k in ('client_id', 'client_secret')}
        store.write(data)
        if token:
            try:
                if platform == 'youtube':
                    _http('POST', 'https://oauth2.googleapis.com/revoke', form={'token': token})
                else:
                    _http('POST', 'https://open.tiktokapis.com/v2/oauth/revoke/', form={
                        'client_key': entry['client_id'], 'client_secret': entry['client_secret'],
                        'token': token})
            except Exception:  # noqa: BLE001 - local disconnect succeeds despite provider failure
                return _status(data[platform], platform)
        return _status(data[platform], platform)


def store_publication_secret(root: Path, key: str, value):
    with _LOCK:
        store = _store(root)
        data = store.read()
        data.setdefault('_publications', {})[key] = value
        store.write(data)


def load_publication_secret(root: Path, key: str):
    with _LOCK:
        return _store(root).read().get('_publications', {}).get(key)


def sync_connected_channel(root: Path, platform: str):
    # A reconfiguration cannot relabel another account's in-flight metric response.
    with _LOCK:
        return _sync_connected_channel(root, platform)


def _sync_connected_channel(root: Path, platform: str):
    _platform(platform)
    token = access_token(root, platform, (SCOPES[platform][0 if platform == 'youtube' else 1],))
    account_id = connection_status(root)[platform]['account_id']
    fetched = datetime.now(UTC).isoformat()
    records = []
    if platform == 'youtube':
        channel = _http('GET', 'https://www.googleapis.com/youtube/v3/channels?' +
                        urlencode({'part': 'contentDetails', 'mine': 'true'}), token=token)
        try:
            playlist = channel['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        except (KeyError, IndexError, TypeError):
            raise ConnectionError('YouTube uploads playlist unavailable') from None
        cursor = ''
        for _ in range(20):
            page = _http('GET', 'https://www.googleapis.com/youtube/v3/playlistItems?' + urlencode({
                'part': 'contentDetails', 'playlistId': playlist, 'maxResults': 50,
                'pageToken': cursor}), token=token)
            ids = [i.get('contentDetails', {}).get('videoId') for i in page.get('items', [])]
            ids = [i for i in ids if i]
            if ids:
                videos = _http('GET', 'https://www.googleapis.com/youtube/v3/videos?' + urlencode({
                    'part': 'snippet,statistics', 'id': ','.join(ids)}), token=token)
                for video in videos.get('items', []):
                    stats, snippet = video.get('statistics', {}), video.get('snippet', {})
                    record = {'slug': 'youtube-' + video['id'],
                              'url': 'https://www.youtube.com/watch?v=' + video['id'],
                              'title_used': snippet.get('title') or '',
                              'published_at': snippet.get('publishedAt') or '',
                              'recorded_at': fetched, 'source': 'youtube_api', 'metrics_observed': []}
                    if 'viewCount' in stats:
                        record['views'] = int(stats['viewCount'])
                        record['metrics_observed'].append('views')
                    records.append(record)
            next_cursor = page.get('nextPageToken')
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
    else:
        cursor = 0
        for _ in range(20):
            page = _http('POST', 'https://open.tiktokapis.com/v2/video/list/?fields='
                         'id,title,share_url,create_time,view_count,share_count,comment_count',
                         token=token, json_body={'max_count': 20, 'cursor': cursor}).get('data', {})
            for video in page.get('videos', []):
                record = {'slug': 'tiktok-' + video['id'], 'url': video.get('share_url') or '',
                          'title_used': video.get('title') or '', 'recorded_at': fetched,
                          'source': 'tiktok_api', 'metrics_observed': []}
                if 'create_time' in video:
                    record['published_at'] = datetime.fromtimestamp(
                        video['create_time'], UTC).isoformat()
                if 'view_count' in video:
                    record['views'] = int(video['view_count'])
                    record['metrics_observed'].append('views')
                if 'share_count' in video:
                    record['shares_saves'] = int(video['share_count'])
                    record['metrics_observed'].append('shares_saves')
                records.append(record)
            next_cursor = page.get('cursor')
            if not page.get('has_more') or next_cursor is None or next_cursor == cursor:
                break
            cursor = next_cursor
    for record in records:
        record.update(platform=platform, source_account_id=account_id)
    return {'records': records, 'fetched_at': fetched, 'platform': platform,
            'account_id': account_id}
