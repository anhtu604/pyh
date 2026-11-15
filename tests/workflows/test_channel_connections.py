import copy
import hashlib
from urllib.parse import parse_qs, urlsplit

import pytest

from healthvideo.workflows import channel_connections as c


@pytest.fixture
def setup(monkeypatch, tmp_path):
    class Memory:
        def __init__(self):
            self.data = {}

        def read(self):
            return copy.deepcopy(self.data)

        def write(self, value):
            self.data = copy.deepcopy(value)

    store = Memory()
    monkeypatch.setattr(c, '_store', lambda root: store)
    monkeypatch.setattr(c.time, 'time', lambda: 1000)
    c.configure_connection(tmp_path, 'youtube', {'client_id': 'client', 'client_secret': 'SECRET'})
    return tmp_path, store


def begin(root, platform='youtube'):
    result = c.begin_connection(root, platform, f'http://127.0.0.1:8765/api/channel/oauth/{platform}/callback')
    return parse_qs(urlsplit(result['authorization_url']).query)


def connect(monkeypatch, root, scopes=None):
    query = begin(root)
    def http(method, url, **kwargs):
        if url == c.TOKEN_URL['youtube']:
            return {'access_token': 'TOKEN', 'refresh_token': 'REFRESH', 'expires_in': 3600,
                    'scope': ' '.join(scopes if scopes is not None else c.SCOPES['youtube'])}
        assert 'mine=true' in url
        return {'items': [{'id': 'channel123', 'snippet': {'title': 'Verified'}}]}
    monkeypatch.setattr(c, '_http', http)
    return c.complete_connection(root, 'youtube', {'state': query['state'][0], 'code': 'CODE'})


def test_configure_is_not_connected_and_no_secrets_in_status(setup):
    root, _ = setup
    status = c.connection_status(root)
    assert status['youtube']['configured']
    assert not status['youtube']['connected']
    assert 'SECRET' not in str(status)


def test_state_mismatch_expiry_and_replay(monkeypatch, setup):
    root, store = setup
    query = begin(root)
    calls = []
    monkeypatch.setattr(c, '_http', lambda *a, **k: calls.append(a))
    with pytest.raises(c.ConnectionError, match='state'):
        c.complete_connection(root, 'youtube', {'state': 'wrong', 'code': 'CODE'})
    store.data['youtube']['pending']['created_at'] = 0
    with pytest.raises(c.ConnectionError, match='expired'):
        c.complete_connection(root, 'youtube', {'state': query['state'][0]})
    assert calls == []
    query = begin(root)
    with pytest.raises(c.ConnectionError, match='declined'):
        c.complete_connection(root, 'youtube', {'state': query['state'][0], 'error': 'SECRET'})
    with pytest.raises(c.ConnectionError, match='state'):
        c.complete_connection(root, 'youtube', {'state': query['state'][0], 'code': 'CODE'})


def test_verified_account_partial_grants(monkeypatch, setup):
    root, _ = setup
    status = connect(monkeypatch, root, c.SCOPES['youtube'][:1])
    assert status['account_id'] == 'channel123'
    assert status['connected'] and status['can_sync'] and not status['can_publish']
    with pytest.raises(c.ConnectionError, match='permission'):
        c.access_token(root, 'youtube', (c.SCOPES['youtube'][1],))


def test_refresh_rotation_and_disconnect_failure(monkeypatch, setup):
    root, store = setup
    connect(monkeypatch, root)
    store.data['youtube']['token']['expires_at'] = 999
    monkeypatch.setattr(c, '_http', lambda *a, **k: {
        'access_token': 'NEW', 'refresh_token': 'ROTATED', 'expires_in': 3600})
    assert c.access_token(root, 'youtube') == 'NEW'
    assert store.data['youtube']['token']['refresh_token'] == 'ROTATED'
    assert c.connection_status(root)['youtube']['can_publish']
    def fail(*a, **k):
        raise RuntimeError('SECRET')
    monkeypatch.setattr(c, '_http', fail)
    assert not c.disconnect_connection(root, 'youtube')['connected']
    assert set(store.data['youtube']) == {'client_id', 'client_secret'}


def test_tiktok_hex_pkce_and_loopback_validation(setup):
    root, store = setup
    c.configure_connection(root, 'tiktok', {'client_id': 'client', 'client_secret': 'SECRET'})
    query = begin(root, 'tiktok')
    verifier = store.data['tiktok']['pending']['verifier']
    assert query['code_challenge'][0] == hashlib.sha256(verifier.encode()).hexdigest()
    for uri in ('https://evil.test/api/channel/oauth/tiktok/callback',
                'http://127.0.0.1:80/other', 'http://localhost/api/channel/oauth/tiktok/callback'):
        with pytest.raises(c.ConnectionError):
            c.begin_connection(root, 'tiktok', uri)


def test_transport_redacts_provider_error(monkeypatch):
    def fail(*a, **k):
        raise RuntimeError('SECRET token code')
    monkeypatch.setattr(c, 'urlopen', fail)
    with pytest.raises(c.ConnectionError) as error:
        c._http('POST', c.TOKEN_URL['youtube'], form={'code': 'SECRET'})
    assert 'SECRET' not in str(error.value)


def test_youtube_pagination_observed_only(monkeypatch, setup):
    root, _ = setup
    connect(monkeypatch, root)
    pages = []
    def http(method, url, **kwargs):
        if '/channels?' in url:
            return {'items': [{'contentDetails': {'relatedPlaylists': {'uploads': 'UP'}}}]}
        if '/playlistItems?' in url:
            pages.append(url)
            return {'items': [{'contentDetails': {'videoId': str(len(pages))}}],
                    **({'nextPageToken': 'NEXT'} if len(pages) == 1 else {})}
        return {'items': [{'id': str(len(pages)), 'snippet': {'title': 'Video'},
                           'statistics': {'viewCount': '7'} if len(pages) == 1 else {}}]}
    monkeypatch.setattr(c, '_http', http)
    payload = c.sync_connected_channel(root, 'youtube')
    records = payload['records']
    assert len(records) == 2 and len(pages) == 2
    assert records[0]['views'] == 7
    assert 'views' not in records[1]
    assert all('retention' not in r and 'ctr' not in r for r in records)
    from healthvideo.workflows.channel_analytics import (
        load_metrics,
        save_synced_metrics,
    )
    assert save_synced_metrics(root, payload)['imported_count'] == 2
    saved = load_metrics(root)
    assert all(r.platform == 'youtube' and r.source_account_id == 'channel123' for r in saved)


def test_secret_store_outside_project_and_namespaced(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'private'))
    first = c.SecretStore(tmp_path / 'repo')
    assert not first.path.is_relative_to(tmp_path / 'repo')
    assert first.path != c.SecretStore(tmp_path / 'other').path
    first.write({'secret': 'SENSITIVE'})
    assert first.read() == {'secret': 'SENSITIVE'}
    if c.os.name == 'nt':
        assert b'SENSITIVE' not in first.path.read_bytes()


def test_tiktok_account_and_pagination(monkeypatch, setup):
    root, _ = setup
    c.configure_connection(root, 'tiktok', {'client_id': 'client', 'client_secret': 'SECRET'})
    state = begin(root, 'tiktok')['state'][0]
    pages = []
    def http(method, url, **kwargs):
        if url == c.TOKEN_URL['tiktok']:
            return {'access_token': 'TOKEN', 'expires_in': 3600,
                    'scope': 'user.info.basic,video.list'}
        if '/user/info/' in url:
            return {'data': {'user': {'open_id': 'actual-user', 'display_name': 'Actual'}}}
        pages.append(kwargs['json_body']['cursor'])
        return {'data': {'videos': [{'id': str(len(pages)), 'view_count': 0}],
                         'cursor': 123, 'has_more': len(pages) == 1}}
    monkeypatch.setattr(c, '_http', http)
    status = c.complete_connection(root, 'tiktok', {'state': state, 'code': 'CODE'})
    assert status['account_id'] == 'actual-user' and status['can_sync']
    assert not status['can_publish']
    payload = c.sync_connected_channel(root, 'tiktok')
    records = payload['records']
    assert pages == [0, 123]
    assert [r['views'] for r in records] == [0, 0]
    assert records[0]['metrics_observed'] == ['views']
    from healthvideo.workflows.channel_analytics import (
        load_metrics,
        save_synced_metrics,
    )
    assert save_synced_metrics(root, payload)['imported_count'] == 2
    saved = load_metrics(root)
    assert all(r.platform == 'tiktok' and r.source_account_id == 'actual-user' for r in saved)


def test_no_channel_does_not_connect(monkeypatch, setup):
    root, _ = setup
    state = begin(root)['state'][0]
    monkeypatch.setattr(c, '_http', lambda method, url, **kwargs:
                        {'access_token': 'TOKEN', 'expires_in': 3600}
                        if url == c.TOKEN_URL['youtube'] else {'items': []})
    with pytest.raises(c.ConnectionError, match='No YouTube channel'):
        c.complete_connection(root, 'youtube', {'state': state, 'code': 'CODE'})
    assert not c.connection_status(root)['youtube']['connected']


def test_authorized_account_snapshot(monkeypatch, setup):
    root, store = setup
    connect(monkeypatch, root)
    account = c.authorized_account(root, 'youtube', (c.SCOPES['youtube'][1],))
    assert account == {'account_id': 'channel123', 'account_title': 'Verified',
                       'access_token': 'TOKEN'}
    store.data['youtube']['account_id'] = 'replacement'
    assert account['account_id'] == 'channel123'
