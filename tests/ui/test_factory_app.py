"""HTTP dashboard contract; no Playwright dependency is present in the lockfile."""
import json
import threading
from http.client import HTTPConnection

import pytest

from healthvideo.approver_pin import set_pin
from healthvideo.workflows import dashboard, factory
from tests.helpers import create_v2_project_fixture


@pytest.fixture
def app(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Unexpected background factory start')

    monkeypatch.setattr(factory, 'start_background', forbidden)
    pin = tmp_path / 'config/approver-pin.json'
    set_pin('918273', path=pin)
    monkeypatch.setattr(dashboard, 'pin_path', lambda: pin)
    server = dashboard.DashboardServer(tmp_path, 0, token='fixture-token', agents=list)
    create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    queue = tmp_path / 'topics/queue.yaml'
    queue.parent.mkdir(parents=True)
    queue.write_text('version: 1\nentries: []\n', encoding='utf-8')
    server.protected_bytes = {p: p.read_bytes() for folder in ('projects', 'topics')
                              for p in (tmp_path / folder).rglob('*') if p.is_file()}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    assert all(path.read_bytes() == before for path, before in server.protected_bytes.items())
    assert {p for folder in ('projects', 'topics') for p in (tmp_path / folder).rglob('*') if p.is_file()} == set(server.protected_bytes)


def request(app, path, body=None, *, token='fixture-token', host=None):
    conn = HTTPConnection('127.0.0.1', app.server_address[1], timeout=20)
    headers = {'X-Dashboard-Token': token, 'Content-Type': 'application/json'}
    if host:
        headers['Host'] = host
    conn.request('GET' if body is None else 'POST', path,
                 body=None if body is None else json.dumps(body), headers=headers)
    response = conn.getresponse()
    raw = response.read()
    conn.close()
    if response.getheader('Content-Type', '').startswith('application/json'):
        return response.status, json.loads(raw)
    return response.status, raw


def test_status_and_start_button_have_no_acceptance_gate(app):
    status, page = request(app, '/')
    assert status == 200
    assert b'id="factory-acceptance"' not in page
    status, data = request(app, '/api/status')
    assert status == 200, data
    assert 'can_start' not in data['factory']
    assert 'id="btn-start" type="button" title="Bật xưởng sản xuất"'.encode() in page


def test_gate_decide_five_attempt_lockout(app):
    path, project = next(iter(dashboard.factory.projects(app.root)))
    gate_url = f'/api/project/{path.name}/decide'
    gate = {'revision': project.active_revision, 'action': 'approve', 'reviewer': 'Fixture', 'pin': '000000'}
    for _ in range(5):
        assert request(app, gate_url, gate)[0] == 403
    assert app.limiter.locked_until > 0
    assert request(app, gate_url, {**gate, 'pin': '918273'})[0] == 403
