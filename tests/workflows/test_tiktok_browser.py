import copy
import json
import subprocess
from types import SimpleNamespace

import pytest

from healthvideo.workflows import channel_connections as connections
from healthvideo.workflows import tiktok_browser as browser
from healthvideo.workflows import tiktok_browser_bridge as helper


@pytest.fixture
def memory(tmp_path, monkeypatch):
    data = {'tiktok': {'client_id': 'client', 'account_id': 'oauth-id',
                       'token': {'access_token': 'SECRET', 'expires_at': 99999999999,
                                 'scopes': ['video.publish']}}}
    store = SimpleNamespace(read=lambda: copy.deepcopy(data), write=lambda value: (data.clear(), data.update(value)))
    monkeypatch.setattr(connections, '_store', lambda root: store)
    monkeypatch.setattr(browser, '_JOBS', {})
    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self):
            self.target()
    monkeypatch.setattr(browser.threading, 'Thread', ImmediateThread)
    return tmp_path, data


def cookies(uid='123'):
    return [{'name': 'uid_tt', 'value': uid, 'domain': '.tiktok.com'},
            {'name': 'sessionid', 'value': 'SECRET', 'domain': '.tiktok.com'}]


def test_verified_uid_requires_real_cookie():
    assert helper.verified_uid(cookies()) == '123'
    opaque_identity = 'abc123ff' * 4
    assert len(helper.verified_uid(cookies(opaque_identity))) == 64
    assert helper.verified_uid(cookies(opaque_identity)) != opaque_identity
    for invalid in ([], [{'name': 'uid_tt', 'value': '123', 'domain': 'evil.com'}], cookies('alias')):
        with pytest.raises(ValueError):
            helper.verified_uid(invalid)


def test_failed_or_missing_uid_login_preserves_oauth(memory, monkeypatch):
    root, data = memory
    for response in ({'session': {'cookies': []}}, {'uid': '123', 'session': {'cookies': cookies('456')}}):
        monkeypatch.setattr(browser, 'bridge', lambda *a, response=response, **k: response)
        result = browser._start(root, 'login')
        assert result['status'] == 'failed'
        assert data['tiktok']['account_id'] == 'oauth-id'
        assert 'browser_session' not in data['tiktok']
        assert connections.connection_status(root)['tiktok']['connection_method'] == 'oauth'


def test_success_session_has_no_analytics_or_public_secrets(memory, monkeypatch):
    root, data = memory
    monkeypatch.setattr(browser, 'bridge', lambda *a, **k: {
        'ok': True, 'uid': '123', 'session': {'cookies': cookies(), 'user_agent': 'agent'}})
    assert browser._start(root, 'login')['status'] == 'connected'
    status = connections.connection_status(root)['tiktok']
    assert status['can_publish'] and not status['can_sync']
    assert status['account_id'] == '123' and status['identity_source'] == 'session_cookie'
    assert 'SECRET' not in json.dumps(status)
    with pytest.raises(connections.ConnectionError, match='analytics'):
        connections.access_token(root, 'tiktok')
    assert connections.authorized_account(root, 'tiktok', ('video.publish',))['session']['cookies']
    browser.disconnect(root)
    assert 'browser_session' not in data['tiktok']
    assert connections.connection_status(root)['tiktok']['account_id'] == 'oauth-id'


def test_bridge_credentials_stdin_only(tmp_path, monkeypatch):
    python = tmp_path / 'python.exe'
    python.touch()
    monkeypatch.setattr(browser, '_python', lambda: python)
    monkeypatch.setattr(browser, '_chrome', lambda: python)
    def run(argv, **kwargs):
        assert 'SECRET' not in str(argv) + str(kwargs.get('env'))
        assert kwargs['body']['session'] == 'SECRET'
        assert kwargs['env']['AUTOTOK_BROWSER'] == 'local'
        return b'{"ok":true}'
    monkeypatch.setattr(browser, '_run', run)
    browser.bridge({'action': 'upload', 'session': 'SECRET'})


def test_bounded_helper_redacts_timeout(monkeypatch):
    def fail(*a, **k):
        raise subprocess.TimeoutExpired('SECRET', 1, output=b'SECRET')
    monkeypatch.setattr(browser, 'run_bounded', fail)
    with pytest.raises(ValueError) as error:
        browser._run(['python'], body={'session': 'SECRET'}, timeout=1)
    assert 'SECRET' not in str(error.value)


def test_root_scoped_session_store(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'outside'))
    one = connections.SecretStore(tmp_path / 'project-one').path
    two = connections.SecretStore(tmp_path / 'project-two').path
    assert one != two and one.is_relative_to(tmp_path / 'outside')


def test_helper_never_persists_upstream_account_store():
    source = helper.Path(helper.__file__).read_text(encoding='utf-8')
    assert 'AccountStore' not in source
    assert 'login_interactive' not in source
