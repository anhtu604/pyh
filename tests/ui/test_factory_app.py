"""HTTP acceptance contract; no Playwright dependency is present in the lockfile."""
import json
import threading
from http.client import HTTPConnection

import pytest

from healthvideo.approver_pin import set_pin
from healthvideo.workflows import dashboard, factory, factory_standards, factory_trials
from tests.helpers import create_v2_project_fixture, write_passing_script_review


@pytest.fixture
def app(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Trial called production')
    from healthvideo.agents import AgentResult
    from healthvideo.storage.files import write_yaml_atomic
    def fake_invoke(agents, prompt, *, cwd, log_dir):
        rev = log_dir.parent / 'project/revisions/001'
        write_passing_script_review(rev)
        write_yaml_atomic(rev / 'script/script.yaml', {
            'lines': [{'id': 'T01', 'text': 'Một hình tròn đi ngang qua màn hình.', 'claim_id': 'C01', 'source_marker': '[R01]'}],
        })
        write_yaml_atomic(rev / 'evidence/ledger.yaml', {
            'claims': [{'id': 'C01', 'text_public': 'Khẳng định mẫu.', 'sources': ['R01'],
                        'support': [{'source_id': 'R01', 'locator': 'Abstract', 'quote': 'Trích dẫn ngắn.'}]}],
            'records': [{'id': 'R01', 'title': 'Nguồn mẫu', 'year': 2024}],
        })
        log_path = log_dir / 'fake.log'
        log_path.write_text('ok', encoding='utf-8')
        return AgentResult(agent='fake', ok=True, quota_exhausted=False, log_path=log_path)
    monkeypatch.setattr(factory, 'start_background', forbidden)
    monkeypatch.setattr(factory_trials, 'invoke_with_failover', fake_invoke)
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


def post(app, action, body):
    if action == 'accept':
        body = {'pin': '918273', **body}
    status, data = request(app, '/api/trials/' + action, body)
    assert status == 200, data
    if action == 'run' and data['message'].get('status') == 'running':
        return factory_trials.wait_trial(app.root, body['trial_id'])
    return data['message']


def test_trial_review_reload_and_stale_two_tabs(app):
    trial = post(app, 'create', {'stage': 1, 'topic': 'TEST — bouncing ball'})
    trial = post(app, 'run', {'trial_id': trial['id']})
    draft = {'trial_id': trial['id'], 'stage': 1, 'text': 'Readable TEST motion'}
    post(app, 'standard-draft', draft)
    status, bundle = request(app, f"/api/trials/{trial['id']}/bundle")
    assert status == 200
    assert bundle['draft']['text'] == draft['text']
    decision = {**draft, 'expected_input_hash': bundle['input_hash'], 'expected_version': 0,
                'pin': '918273', 'reviewer': 'Fixture reviewer', 'expected_standards_hash': bundle['standards_hash']}
    assert post(app, 'accept', decision)['version'] == 1
    assert request(app, '/api/trials/accept', decision)[0] == 400
    assert request(app, '/api/standards/accepted')[1]['accepted']['1']['version'] == 1
    assert len(request(app, '/api/trials')[1]['trials']) == 1
    assert all(path.read_bytes() == before for path, before in app.protected_bytes.items())


def test_wrong_stage_failed_sample_and_changed_draft_rejected(app):
    trial = post(app, 'create', {'stage': 2})
    trial = post(app, 'run', {'trial_id': trial['id']})
    draft = {'trial_id': trial['id'], 'stage': 2, 'text': 'TEST standard'}
    post(app, 'standard-draft', draft)
    decision = {**draft, 'expected_input_hash': trial['input_hash'], 'expected_version': 0,
                'pin': '918273', 'reviewer': 'Fixture reviewer', 'expected_standards_hash': factory_standards.standards_hash(app.root)}
    status, error = request(app, '/api/trials/accept', decision)
    assert status == 400
    assert 'thứ tự' in error['error']
    trial = post(app, 'create', {'stage': 1})
    trial = post(app, 'run', {'trial_id': trial['id']})
    draft.update(trial_id=trial['id'], stage=1)
    post(app, 'standard-draft', draft)
    decision.update(draft, expected_input_hash=trial['input_hash'])
    post(app, 'standard-draft', {**draft, 'text': 'Another tab changed this'})
    status, error = request(app, '/api/trials/accept', decision)
    assert status == 400
    assert 'Nháp đã thay đổi' in error['error']
    assert factory_standards.accepted_standards(app.root) == {}
    (factory_trials.trial_dir(app.root, trial['id']) / trial['outputs'][0]['path']).write_bytes(b'bad')
    decision['text'] = 'Another tab changed this'
    status, error = request(app, '/api/trials/accept', decision)
    assert status == 400
    assert 'stale' in error['error']


def test_rerun_invalidates_previously_viewed_sample(app):
    trial = post(app, 'create', {'stage': 1})
    trial = post(app, 'run', {'trial_id': trial['id']})
    draft = {'trial_id': trial['id'], 'stage': 1, 'text': 'Same draft text'}
    post(app, 'standard-draft', draft)
    old = {**draft, 'expected_input_hash': trial['input_hash'], 'expected_version': 0,
           'pin': '918273', 'reviewer': 'Fixture reviewer', 'expected_standards_hash': factory_standards.standards_hash(app.root)}
    post(app, 'run', {'trial_id': trial['id']})
    post(app, 'standard-draft', draft)
    assert request(app, '/api/trials/accept', old)[0] == 400
    assert factory_standards.accepted_standards(app.root) == {}


def test_trial_auth_and_media_containment(app):
    assert request(app, '/api/trials/create', {'stage': 1}, token='')[0] == 403
    assert request(app, '/api/trials/create', {'stage': 1}, host='foreign.example')[0] == 403
    assert request(app, '/api/trials/create', {'stage': 1, 'pin': 'not allowed'})[0] == 400
    trial = post(app, 'create', {'stage': 1})
    trial = post(app, 'run', {'trial_id': trial['id']})
    url = f"/api/trials/{trial['id']}/media/{trial['outputs'][0]['path']}"
    assert request(app, url)[0] == 200
    assert request(app, f"/api/trials/{trial['id']}/media/../../secret.txt")[0] in (400, 404, 500)
    assert request(app, '/api/factory/start', {})[0] == 400


def test_acceptance_section_and_button_gate(app):
    status, page = request(app, '/')
    assert status == 200
    assert 'Nghiệm thu xưởng'.encode() in page
    assert b'id="factory-acceptance"' in page
    for snippet in (
        'Bước 1 · Tạo mẫu',
        'Bước 2 · Xem mẫu',
        'Bước 3 · Góp ý &amp; chấp nhận',
        'Tạo và chạy mẫu',
        'Chi tiết kỹ thuật',
        'Xưởng đã nghiệm thu đủ 4 chuẩn',
        'Cần nghiệm thu đủ 4 giai đoạn trước',
        'friendlyError(',
        'Xem nhật ký đầy đủ',
        'Agent sẽ tìm nguồn và viết kịch bản thật cho chủ đề này (khoảng 5–15 phút). Mẫu chỉ để nghiệm thu, không xuất bản.',
        'Mẫu ngoại tuyến cố định, chỉ kiểm khung.',
        'Mẫu đang chạy',
        'Chạy lại',
    ):
        assert snippet.encode('utf-8') in page
    status, data = request(app, '/api/status')
    assert status == 200, data
    assert data['factory']['can_start'] is False


def acceptance_decision(app):
    trial = post(app, 'create', {'stage': 1})
    trial = post(app, 'run', {'trial_id': trial['id']})
    draft = {'trial_id': trial['id'], 'stage': 1, 'text': 'Chuyển động rõ ràng.'}
    post(app, 'standard-draft', draft)
    return {**draft, 'expected_input_hash': trial['input_hash'], 'expected_version': 0,
            'expected_standards_hash': factory_standards.standards_hash(app.root),
            'reviewer': 'Tên từ biểu mẫu'}


def test_accept_requires_configured_pin(app):
    decision = acceptance_decision(app)
    dashboard.pin_path().unlink()
    status, error = request(app, '/api/trials/accept', {**decision, 'pin': '918273'})
    assert status == 400
    assert 'Chưa đặt PIN' in error['error']
    assert factory_standards.accepted_standards(app.root) == {}


@pytest.mark.parametrize('pin', [None, '000000'])
def test_missing_wrong_pin_preserves_versions(app, pin):
    decision = acceptance_decision(app)
    body = decision if pin is None else {**decision, 'pin': pin}
    assert request(app, '/api/trials/accept', body)[0] == 403
    assert factory_standards.accepted_standards(app.root) == {}
    accepted = post(app, 'accept', decision)
    assert accepted['version'] == 1
    before = (app.root / factory_standards.STANDARDS_FILE).read_bytes()
    decision.update(expected_version=1, expected_standards_hash=factory_standards.standards_hash(app.root))
    body = decision if pin is None else {**decision, 'pin': pin}
    assert request(app, '/api/trials/accept', body)[0] == 403
    assert (app.root / factory_standards.STANDARDS_FILE).read_bytes() == before


def test_accept_uses_configured_reviewer_and_never_persists_pin(app, monkeypatch):
    decision = acceptance_decision(app)
    monkeypatch.setattr(dashboard, 'reviewer_name', lambda: 'Bác sĩ cấu hình')
    decision.pop('reviewer')
    accepted = post(app, 'accept', decision)
    assert accepted['reviewer'] == 'Bác sĩ cấu hình'
    assert accepted['version'] == 1
    assert 'pin' not in accepted
    for folder in ('profiles', 'cache/factory-test'):
        assert all(b'918273' not in p.read_bytes() for p in (app.root / folder).rglob('*') if p.is_file())


@pytest.mark.parametrize('mixed_routes', [False, True])
def test_accept_and_gate_share_five_attempt_lockout(app, mixed_routes):
    decision = acceptance_decision(app)
    path, project = next(iter(dashboard.factory.projects(app.root)))
    gate_url = f'/api/project/{path.name}/decide'
    gate = {'revision': project.active_revision, 'action': 'approve', 'reviewer': 'Fixture', 'pin': '000000'}
    for attempt in range(5):
        url, body = ((gate_url, gate) if mixed_routes and attempt % 2
                     else ('/api/trials/accept', {**decision, 'pin': '000000'}))
        assert request(app, url, body)[0] == 403
    assert request(app, '/api/trials/accept', {**decision, 'pin': '918273'})[0] == 403
    assert app.limiter.locked_until > 0
    assert request(app, gate_url, {**gate, 'pin': '918273'})[0] == 403
    assert factory_standards.accepted_standards(app.root) == {}


def test_bundle_has_readable_vietnamese_script_and_event_times(app):
    trial = post(app, 'create', {'stage': 1})
    post(app, 'run', {'trial_id': trial['id']})
    status, bundle = request(app, f"/api/trials/{trial['id']}/bundle")
    assert status == 200
    assert bundle['previews']['script.yaml']['lines'][0]['text'] == 'Một hình tròn đi ngang qua màn hình.'
    assert bundle['lines'][0]['claim_id'] == 'C01'
    assert bundle['claims'][0]['support'][0]['source_id'] == 'R01'
    assert all(event['at'] for event in bundle['timeline'])
    assert len(bundle['timeline']) >= 2
    output = factory_trials.trial_dir(app.root, trial['id']) / bundle['outputs'][0]['path']
    output.write_text('changed', encoding='utf-8')
    assert request(app, f"/api/trials/{trial['id']}/bundle")[1]['previews'] == {}
