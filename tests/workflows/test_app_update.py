"""Tests for version reporting and detached app self-update (no real relaunches)."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from http.client import HTTPConnection
from types import SimpleNamespace

import pytest

from healthvideo.process import process_token
from healthvideo.workflows import app_update, dashboard, factory, telegram_bot


def _completed(stdout: str = '', returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(['git'], returncode, stdout=stdout, stderr='')


def _request(srv, method: str, path: str, *, headers: dict[str, str] | None = None):
    port = srv.server_address[1]
    conn = HTTPConnection('127.0.0.1', port, timeout=5)
    conn.request(method, path, headers={'Host': f'127.0.0.1:{port}', **(headers or {})})
    response = conn.getresponse()
    body = response.read().decode('utf-8')
    conn.close()
    return response.status, body


def test_read_git_head_and_version_payload_with_short_cache(tmp_path):
    app_update.clear_latest_cache()
    calls: list[list[str]] = []
    commits = [
        ('abc1234', '2026-11-24T10:00:00+07:00\x00feat: first'),
        ('def5678', '2026-11-24T11:30:00+07:00\x00fix: second'),
    ]
    idx = {'n': 0}

    def fake_runner(argv, **_kwargs):
        calls.append(list(argv))
        short_hash, log_line = commits[idx['n']]
        if 'rev-parse' in argv:
            return _completed(stdout=f'{short_hash}\n')
        return _completed(stdout=f'{log_line}\n')

    clock = {'t': 100.0}
    running = app_update.read_running_version(tmp_path, runner=fake_runner)
    assert running == {'hash': 'abc1234', 'date': '2026-11-24T10:00:00+07:00'}

    # First latest read hits git
    p1 = app_update.version_payload(
        running,
        repo_dir=tmp_path,
        ttl_seconds=20.0,
        monotonic=lambda: clock['t'],
        runner=fake_runner,
    )
    assert p1['running'] == running
    assert p1['latest'] == {
        'hash': 'abc1234',
        'date': '2026-11-24T10:00:00+07:00',
        'subject': 'feat: first',
    }
    assert p1['update_available'] is False

    # Move repo HEAD forward; within TTL it still returns cached latest
    idx['n'] = 1
    calls_before = len(calls)
    clock['t'] = 110.0
    p2 = app_update.version_payload(
        running,
        repo_dir=tmp_path,
        ttl_seconds=20.0,
        monotonic=lambda: clock['t'],
        runner=fake_runner,
    )
    assert len(calls) == calls_before
    assert p2['update_available'] is False

    # After TTL expires (<= 30s), latest refreshes and detects update_available
    clock['t'] = 121.0
    p3 = app_update.version_payload(
        running,
        repo_dir=tmp_path,
        ttl_seconds=20.0,
        monotonic=lambda: clock['t'],
        runner=fake_runner,
    )
    assert p3['latest'] == {
        'hash': 'def5678',
        'date': '2026-11-24T11:30:00+07:00',
        'subject': 'fix: second',
    }
    assert p3['update_available'] is True


def test_read_git_head_handles_missing_git(tmp_path):
    def missing_git(*_args, **_kwargs):
        raise FileNotFoundError('git')

    running = app_update.read_running_version(tmp_path, runner=missing_git)
    assert running == {'hash': None, 'date': None}
    app_update.clear_latest_cache()
    payload = app_update.version_payload(running, repo_dir=tmp_path, runner=missing_git)
    assert payload == {
        'running': {'hash': None, 'date': None},
        'latest': {'hash': None, 'date': None, 'subject': None},
        'update_available': False,
    }


def test_build_relaunch_argv_preserves_dash_c_via_orig_argv():
    argv = app_update.build_relaunch_argv(
        argv=['-c', 'app', '--root', 'E:\\pyh-ui1\\.sandbox', '--port', '8793', '--no-browser'],
        orig_argv=[
            'E:\\venv\\Scripts\\python.exe',
            '-c',
            'from healthvideo.cli import app; app()',
            'app',
            '--root',
            'E:\\pyh-ui1\\.sandbox',
            '--port',
            '8793',
            '--no-browser',
        ],
        python_exe='E:\\venv\\Scripts\\pythonw.exe',
    )
    assert argv == [
        'E:\\venv\\Scripts\\pythonw.exe',
        '-c',
        'from healthvideo.cli import app; app()',
        'app',
        '--root',
        'E:\\pyh-ui1\\.sandbox',
        '--port',
        '8793',
        '--no-browser',
    ]


def test_trigger_app_update_rejects_when_job_running(tmp_path):
    events: list[str] = []
    with pytest.raises(ValueError, match='Không thể cập nhật: đang có agent chạy dở'):
        app_update.trigger_app_update(
            root=tmp_path,
            port=8793,
            check_active_jobs=lambda: 'Không thể cập nhật: đang có agent chạy dở (Biên kịch).',
            is_factory_running=lambda: True,
            stop_factory=lambda: events.append('stop_factory'),
            stop_telegram=lambda: events.append('stop_telegram'),
            quit_app=lambda: events.append('quit_app'),
            spawn_helper=lambda **_kw: events.append('spawn_helper') or tmp_path / 'job.json',
        )
    assert events == []


@pytest.mark.parametrize('factory_on', [False, True])
def test_trigger_app_update_order_when_idle(tmp_path, factory_on):
    events: list[tuple] = []

    def fake_spawn(**kwargs):
        events.append(('spawn_helper', kwargs['restart_factory'], kwargs['port']))
        return tmp_path / 'cache/app-update-job.json'

    result = app_update.trigger_app_update(
        root=tmp_path,
        port=8793,
        check_active_jobs=lambda: None,
        is_factory_running=lambda: factory_on,
        stop_factory=lambda: events.append(('stop_factory',)),
        stop_telegram=lambda: events.append(('stop_telegram',)),
        quit_app=lambda: events.append(('quit_app',)),
        spawn_helper=fake_spawn,
    )
    assert result['updating'] is True
    assert result['restart_factory'] is factory_on
    expected = []
    if factory_on:
        expected.append(('stop_factory',))
    expected.extend([
        ('spawn_helper', factory_on, 8793),
        ('stop_telegram',),
        ('quit_app',),
    ])
    assert events == expected


def test_run_update_job_restarts_factory_and_never_logs_token(tmp_path):
    secret_token = 'super-secret-dashboard-token-XYZ123'
    token_file = tmp_path / app_update.TOKEN_FILE
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(secret_token, encoding='utf-8')

    job_path = tmp_path / app_update.UPDATE_JOB_FILE
    job_path.write_text(
        json.dumps({
            'old_pid': 42424,
            'old_process_token': 'old-token',
            'relaunch_argv': ['pythonw.exe', '-c', 'from healthvideo.cli import app; app()', 'app', '--port', '8793'],
            'cwd': str(tmp_path),
            'root': str(tmp_path),
            'port': 8793,
            'restart_factory': True,
            'wait_timeout_s': 10,
        }),
        encoding='utf-8',
    )

    alive_checks = iter([True, True, False, False])
    popen_calls: list[tuple[list[str], dict]] = []
    http_calls: list[tuple[str, str | None, dict[str, str]]] = []

    def fake_popen(argv, **kwargs):
        popen_calls.append((list(argv), kwargs))
        return SimpleNamespace(pid=99999)

    class _FakeResp:
        def __init__(self, status: int, payload: dict):
            self.status = status
            self._raw = json.dumps(payload).encode('utf-8')

        def read(self):
            return self._raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_fetch(req_or_url, timeout=2):
        if isinstance(req_or_url, str):
            http_calls.append(('GET', req_or_url, {}))
            return _FakeResp(200, {'running': {'hash': 'new9999', 'date': '2026-11-24T19:40:00+07:00'}})
        headers = {k.lower(): v for k, v in req_or_url.header_items()}
        http_calls.append((req_or_url.get_method(), req_or_url.full_url, headers))
        # Even if a buggy response somehow echoed the token, the log must redact it.
        return _FakeResp(200, {'ok': True, 'message': f'started ({secret_token})'})

    clock = {'t': 0.0}

    def fake_sleep(dt: float):
        clock['t'] += dt

    ok = app_update.run_update_job(
        job_path,
        popen=fake_popen,
        pid_alive=lambda _pid, _tok: next(alive_checks, False),
        sleep=fake_sleep,
        monotonic=lambda: clock['t'],
        fetch=fake_fetch,
    )
    assert ok is True
    assert len(popen_calls) == 1
    assert popen_calls[0][0] == ['pythonw.exe', '-c', 'from healthvideo.cli import app; app()', 'app', '--port', '8793']
    assert popen_calls[0][1]['cwd'] == str(tmp_path)
    assert http_calls[0][0] == 'GET'
    assert http_calls[0][1] == 'http://127.0.0.1:8793/api/version'
    assert http_calls[1][0] == 'POST'
    assert http_calls[1][1] == 'http://127.0.0.1:8793/api/factory/start'
    assert http_calls[1][2]['x-dashboard-token'] == secret_token

    log_text = (tmp_path / app_update.UPDATE_LOG_FILE).read_text(encoding='utf-8')
    assert 'new app ready on port 8793, version=new9999' in log_text
    assert 'restart factory ok=True' in log_text
    assert secret_token not in log_text
    assert not job_path.exists()


def test_http_version_and_update_endpoints(tmp_path, monkeypatch):
    app_update.clear_latest_cache()
    monkeypatch.setattr(factory, 'running_pid', lambda _: None)
    monkeypatch.setattr(
        app_update,
        'read_running_version',
        lambda _repo: {'hash': 'aaa1111', 'date': '2026-11-24T12:00:00+07:00'},
    )
    monkeypatch.setattr(
        app_update,
        'read_latest_version',
        lambda _repo, **_kw: {
            'hash': 'bbb2222',
            'date': '2026-11-24T19:00:00+07:00',
            'subject': 'feat: version button',
        },
    )

    srv = dashboard.DashboardServer(tmp_path, 0, token='tok-ver', repo_dir=tmp_path)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        # GET /api/version
        status, body = _request(srv, 'GET', '/api/version')
        assert status == 200
        data = json.loads(body)
        assert data == {
            'running': {'hash': 'aaa1111', 'date': '2026-11-24T12:00:00+07:00'},
            'latest': {
                'hash': 'bbb2222',
                'date': '2026-11-24T19:00:00+07:00',
                'subject': 'feat: version button',
            },
            'update_available': True,
        }

        # POST /api/app/update without token -> 403
        status, _ = _request(srv, 'POST', '/api/app/update')
        assert status == 403

        # Simulate a live agent job -> POST /api/app/update returns 400
        logs_dir = tmp_path / 'topics' / 'logs' / 'demo-slug'
        logs_dir.mkdir(parents=True, exist_ok=True)
        my_pid = os.getpid()
        my_tok = process_token(my_pid)
        (logs_dir / '.job-live123.json').write_text(
            json.dumps({
                'job_id': 'live123',
                'role': 'writer',
                'slug': 'demo-slug',
                'step': 'draft',
                'child_pid': my_pid,
                'child_process_token': my_tok,
            }),
            encoding='utf-8',
        )
        status, body = _request(srv, 'POST', '/api/app/update', headers={'X-Dashboard-Token': 'tok-ver'})
        assert status == 400
        assert 'Không thể cập nhật' in json.loads(body)['error']

        # Remove live job; mock spawn/telegram/shutdown -> POST /api/app/update succeeds
        (logs_dir / '.job-live123.json').unlink()
        events: list[str] = []
        monkeypatch.setattr(
            app_update,
            'spawn_relaunch_helper',
            lambda **kw: events.append(f'spawn:{kw["restart_factory"]}') or tmp_path / 'job.json',
        )
        monkeypatch.setattr(telegram_bot, 'stop_background', lambda _root: events.append('stop_tg'))
        monkeypatch.setattr(srv, 'shutdown', lambda: events.append('shutdown'))

        status, body = _request(srv, 'POST', '/api/app/update', headers={'X-Dashboard-Token': 'tok-ver'})
        assert status == 200
        payload = json.loads(body)
        assert payload['ok'] is True
        assert payload['updating'] is True
        assert 'spawn:False' in events
        assert 'stop_tg' in events
    finally:
        # Restore real shutdown on the class so the test server thread exits cleanly
        dashboard.DashboardServer.shutdown(srv)
        srv.server_close()
