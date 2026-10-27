import json
import threading
from http.client import HTTPConnection

import pytest

from healthvideo import cli
from healthvideo.storage.files import read_yaml
from healthvideo.workflows import dashboard, factory
from tests.helpers import create_v2_project_fixture


@pytest.fixture
def server(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    monkeypatch.setattr(factory, 'running_pid', lambda _: None)
    monkeypatch.setattr(dashboard, 'pin_path', lambda: tmp_path / 'config' / 'approver-pin.json')
    calls: list[str] = []
    actions = {
        'factory/start': lambda: calls.append('start') or 'started',
        'factory/stop': lambda: calls.append('stop') or 'stopped',
        'review/open': lambda: calls.append('review') or 'opened',
        'project/packet': lambda slug, body: calls.append(f'packet:{slug}') or 'packet',
    }
    srv = dashboard.DashboardServer(tmp_path, 0, token='tok', agents=lambda: ['codex'], actions=actions)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv, project, calls
    srv.shutdown()
    srv.server_close()


def request(srv, method, path, *, headers=None):
    port = srv.server_address[1]
    conn = HTTPConnection('127.0.0.1', port, timeout=5)
    conn.request(method, path, headers={'Host': f'127.0.0.1:{port}', **(headers or {})})
    response = conn.getresponse()
    body = response.read().decode('utf-8')
    conn.close()
    return response.status, body


def test_status_reports_gate_stage_and_agents(server):
    srv, project, _ = server
    status, body = request(srv, 'GET', '/api/status')
    data = json.loads(body)
    assert status == 200
    assert data['factory'] == {'running': False, 'pid': None, 'can_start': False}
    assert data['agents'] == ['codex']
    assert data['waiting'] == 1
    item = data['projects'][0]
    assert item['slug'] == project.name
    assert item['gate'] == 'medical'
    assert data['stages'][item['stage']] == 'Duyệt y khoa'


def test_index_embeds_token(server):
    srv, _, _ = server
    status, body = request(srv, 'GET', '/')
    assert status == 200
    assert "const TOKEN = 'tok'" in body
    assert '__TOKEN__' not in body


def test_post_requires_token(server):
    srv, _, calls = server
    status, _ = request(srv, 'POST', '/api/factory/start')
    assert status == 403
    assert calls == []


def test_foreign_host_rejected(server):
    srv, _, calls = server
    port = srv.server_address[1]
    conn = HTTPConnection('127.0.0.1', port, timeout=5)
    conn.request('POST', '/api/factory/start', headers={'Host': 'evil.example', 'X-Dashboard-Token': 'tok'})
    assert conn.getresponse().status == 403
    conn.close()
    assert calls == []


def test_actions_dispatch_with_token(server):
    srv, project, calls = server
    headers = {'X-Dashboard-Token': 'tok'}
    assert request(srv, 'POST', '/api/factory/start', headers=headers)[0] == 200
    assert request(srv, 'POST', '/api/review/open', headers=headers)[0] == 200
    assert request(srv, 'POST', f'/api/project/{project.name}/packet', headers=headers)[0] == 200
    assert request(srv, 'POST', '/api/review/approve', headers=headers)[0] == 404
    assert calls == ['start', 'review', f'packet:{project.name}']


@pytest.fixture
def gate(tmp_path, monkeypatch):
    from healthvideo.approver_pin import set_pin

    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    pin = tmp_path / 'config' / 'approver-pin.json'
    set_pin('918273', path=pin)
    monkeypatch.setattr(dashboard, 'pin_path', lambda: pin)
    monkeypatch.setattr(factory, 'running_pid', lambda _: 123)
    rev = read_yaml(project / 'project.yaml')['active_revision']
    return tmp_path, project, rev


def _decide(gate, limiter=None, **body):
    root, project, rev = gate
    payload = {'revision': rev, 'reviewer': 'Tu', **body}
    return dashboard.decide(root, project, payload, limiter=limiter or dashboard.PinLimiter())


def test_decide_wrong_pin_never_mutates(gate):
    with pytest.raises(PermissionError):
        _decide(gate, action='approve', pin='000000')
    assert read_yaml(gate[1] / 'project.yaml')['state'] == 'awaiting_medical_review'


def test_decide_locks_after_repeated_wrong_pins(gate):
    limiter = dashboard.PinLimiter(clock=lambda: 1000.0)
    for _ in range(dashboard.MAX_PIN_FAILURES):
        with pytest.raises(PermissionError):
            _decide(gate, limiter, action='approve', pin='000000')
    with pytest.raises(PermissionError, match='quá nhiều'):
        _decide(gate, limiter, action='approve', pin='918273')
    assert read_yaml(gate[1] / 'project.yaml')['state'] == 'awaiting_medical_review'


def test_decide_refuses_stale_revision(gate):
    root, project, _ = gate
    with pytest.raises(ValueError, match='Revision'):
        dashboard.decide(root, project, {'revision': 'old', 'action': 'approve', 'pin': '918273'},
                         limiter=dashboard.PinLimiter())


def test_decide_approve_with_pin(gate):
    message = _decide(gate, action='approve', pin='918273')
    assert 'Đã duyệt' in message
    assert read_yaml(gate[1] / 'project.yaml')['state'] == 'medically_approved'


def test_decide_does_not_auto_start_without_four_standards(gate, monkeypatch):
    monkeypatch.setattr(factory, 'running_pid', lambda _: None)
    def forbidden(*args, **kwargs):
        pytest.fail('Unaccepted factory started after gate decision')
    monkeypatch.setattr(factory, 'start_background', forbidden)
    message = _decide(gate, action='approve', pin='918273')
    assert 'Đã duyệt' in message


def test_decide_reject_requires_reason_and_records_it(gate):
    with pytest.raises(ValueError, match='lý do'):
        _decide(gate, action='reject', pin='918273')
    _decide(gate, action='reject', reason='Cắt đuôi N07', resume=1, pin='918273')
    data = read_yaml(gate[1] / 'project.yaml')
    assert data['state'] == 'needs_medical_revision'
    assert data['side_state']['resume_state'] == 'draft_ready'


def test_decide_pronunciation_only_on_video_gate(gate):
    with pytest.raises(ValueError, match='video'):
        _decide(gate, action='approve_pronunciation', pin='918273')


def test_dashboard_never_changes_gate_state(server):
    srv, project, _ = server
    for path in ('/api/status', '/'):
        request(srv, 'GET', path)
    assert read_yaml(project / 'project.yaml')['state'] == 'awaiting_medical_review'


def test_review_console_runs_duyet_in_new_console(tmp_path):
    captured = {}
    dashboard.open_review_console(tmp_path, popen=lambda argv, **kw: captured.update(argv=argv, kw=kw))
    assert '"duyet"' in captured['argv'][2]
    assert captured['argv'][-1] == str(tmp_path.resolve())
    assert not any('pin' in key.lower() for key in captured['kw']['env'])


def test_running_agents_reads_runner_marker(tmp_path, monkeypatch):
    marker = tmp_path / 'topics' / 'logs' / 'gout' / dashboard.RUNNING_MARKER
    marker.parent.mkdir(parents=True)
    marker.write_text('codex\n2026-10-24T00:00:00\n', encoding='utf-8')
    monkeypatch.setattr(factory, 'running_pid', lambda _: 42)
    assert dashboard.running_agents(tmp_path) == ['codex']
    monkeypatch.setattr(factory, 'running_pid', lambda _: None)
    assert dashboard.running_agents(tmp_path) == []


@pytest.fixture
def live(tmp_path, monkeypatch):
    """Server with the real actions, a project at the medical gate, and one render file."""
    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    monkeypatch.setattr(factory, 'running_pid', lambda _: 1)
    monkeypatch.setattr(dashboard, 'pin_path', lambda: tmp_path / 'config' / 'approver-pin.json')
    rev = read_yaml(project / 'project.yaml')['active_revision']
    renders = project / 'revisions' / rev / 'renders'
    renders.mkdir(parents=True, exist_ok=True)
    (renders / 'video.mp4').write_bytes(bytes(range(100)))
    srv = dashboard.DashboardServer(tmp_path, 0, token='tok', agents=list)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv, project
    srv.shutdown()
    srv.server_close()


def post_json(srv, path, payload):
    port = srv.server_address[1]
    conn = HTTPConnection('127.0.0.1', port, timeout=5)
    conn.request('POST', path, body=json.dumps(payload).encode('utf-8'),
                 headers={'Host': f'127.0.0.1:{port}', 'X-Dashboard-Token': 'tok',
                          'Content-Type': 'application/json'})
    response = conn.getresponse()
    body = json.loads(response.read().decode('utf-8'))
    conn.close()
    return response.status, body


def test_bundle_lists_products_and_media(live):
    srv, project = live
    status, body = request(srv, 'GET', f'/api/project/{project.name}/bundle')
    data = json.loads(body)
    assert status == 200
    assert data['gate'] == 'medical'
    assert data['media'][0]['url'] == f'/media/{project.name}/video.mp4'
    assert request(srv, 'GET', '/api/project/khong-co/bundle')[0] == 404


def test_media_supports_range_and_blocks_traversal(live):
    srv, project = live
    port = srv.server_address[1]
    conn = HTTPConnection('127.0.0.1', port, timeout=5)
    conn.request('GET', f'/media/{project.name}/video.mp4',
                 headers={'Host': f'127.0.0.1:{port}', 'Range': 'bytes=10-19'})
    response = conn.getresponse()
    assert response.status == 206
    assert response.getheader('Content-Range') == 'bytes 10-19/100'
    assert response.read() == bytes(range(10, 20))
    conn.close()
    assert request(srv, 'GET', f'/media/{project.name}/video.mp4')[0] == 200
    assert request(srv, 'GET', f'/media/{project.name}/..%2F..%2F..%2Fproject.yaml')[0] == 404
    with pytest.raises(LookupError):
        _, manifest = srv.project_dir(project.name)
        dashboard.media_file(project, manifest, '../../../project.yaml')


def test_comment_drafts_fold_into_reject_and_are_remembered(live, monkeypatch):
    from healthvideo.approver_pin import set_pin
    from healthvideo.workflows import standards

    srv, project = live
    pin = srv.root / 'config' / 'approver-pin.json'
    set_pin('918273', path=pin)
    assert post_json(srv, f'/api/project/{project.name}/comment', {'target': 'N07', 'text': 'Cắt đuôi'})[0] == 200
    assert json.loads(request(srv, 'GET', '/api/status')[1])['projects'][0]['comments'] == 1
    rev = read_yaml(project / 'project.yaml')['active_revision']
    status, body = post_json(srv, f'/api/project/{project.name}/decide',
                             {'action': 'reject', 'revision': rev, 'reviewer': 'Tu', 'pin': '918273', 'resume': 1})
    assert status == 200, body
    assert 'ghi nhớ' in body['message']
    assert read_yaml(project / 'project.yaml')['state'] == 'needs_medical_revision'
    assert dashboard.load_draft(srv.root, project.name) == []
    assert '- N07: Cắt đuôi' in standards.load(srv.root)[-1]['text']


def test_standards_add_and_list(live):
    srv, _ = live
    assert post_json(srv, '/api/standards/add', {'text': ' '})[0] == 400
    assert post_json(srv, '/api/standards/add', {'text': 'Không dồn thẻ nguồn cuối video'})[0] == 200
    entries = json.loads(request(srv, 'GET', '/api/standards')[1])['entries']
    assert entries[0]['text'] == 'Không dồn thẻ nguồn cuối video'
    assert entries[0]['slug'] == 'chung'


def test_shortcut_spec_targets_app_command(tmp_path):
    spec = dashboard.shortcut_spec(tmp_path, tmp_path / 'Desktop')
    assert spec['path'].endswith('Xưởng video.lnk')
    assert ' app --root ' in spec['arguments']
    assert str(tmp_path.resolve()) in spec['arguments']


def test_cli_app_reuses_running_dashboard(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    monkeypatch.setattr(dashboard, 'existing_dashboard', lambda port: True)
    result = CliRunner().invoke(cli.app, ['app', '--root', str(tmp_path), '--no-browser'])
    assert result.exit_code == 0, result.output
    assert 'App đã mở sẵn' in result.output
