import json
import os
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
    assert data['factory'] == {'running': False, 'pid': None}
    assert data['agents'] == ['codex']
    assert data['waiting'] == 1
    item = data['projects'][0]
    assert item['slug'] == project.name
    assert item['gate'] == 'medical'
    assert data['stages'][item['stage']] == 'Duyệt y khoa'


def test_project_code_is_consistent_in_status_overview_and_detail(server):
    srv, project, _ = server
    before = (project / 'project.yaml').read_bytes()
    codes = []
    for route, collection in [('/api/status', 'projects'), ('/api/overview', 'projects'),
                              (f'/api/project/{project.name}/bundle', None)]:
        status, body = request(srv, 'GET', route)
        assert status == 200
        payload = json.loads(body)
        item = next(p for p in payload[collection] if p['slug'] == project.name) if collection else payload
        codes.append(item['code'])
        assert item['slug'] == project.name
    assert codes == ['PYH-001'] * 3
    assert (project / 'project.yaml').read_bytes() == before


def test_index_embeds_token(server):
    srv, _, _ = server
    status, body = request(srv, 'GET', '/')
    assert status == 200
    assert "const TOKEN = 'tok'" in body
    assert '__TOKEN__' not in body
    reopen_form = body.split('<form id="ops-reopen"', 1)[1].split('</form>', 1)[0]
    assert 'name="pin" type="password"' in reopen_form
    assert "pin:f.get('pin')" in body


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


def test_card_decide_wrong_pin_changes_nothing(gate):
    from tests.workflows.test_decision_card import decision, report
    root, project, _ = gate
    report(project, decisions=[decision()])
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    limiter = dashboard.PinLimiter()
    with pytest.raises(PermissionError):
        _decide(gate, limiter, action='card', choices={'D1': 'b'}, other='', pin='000000')
    assert limiter.failures == 1
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('kind', ['medical', 'video'])
def test_card_send_fix_rejects_to_draft(gate, kind):
    from healthvideo.storage.files import write_yaml_atomic
    from healthvideo.workflows.decision_card import card
    from tests.workflows.test_decision_card import decision, report
    _, project, rev = gate
    data = read_yaml(project / 'project.yaml')
    data['state'] = f'awaiting_{kind}_review'
    write_yaml_atomic(project / 'project.yaml', data)
    report(project, gate=kind, decisions=[decision()])
    _decide(gate, action='card', choices={'D1': 'b'}, pin='918273')
    data = read_yaml(project / 'project.yaml')
    assert data['state'] == ('needs_medical_revision' if kind == 'medical' else 'needs_production_revision')
    assert data['side_state']['resume_state'] == ('draft_ready' if kind == 'medical' else 'production_in_progress')
    rejection = next((project / 'revisions' / rev / 'reviews' / kind).glob('*-rejected.yaml'))
    assert read_yaml(rejection)['reason'] == 'D1 (N14) → b: Nói rõ hơn'
    assert not (project / 'revisions' / rev / f'reviews/{kind}-approval.yaml').exists()
    # A fresh critic pass, rather than the old round, supplies the follow-up card.
    data['state'] = f'awaiting_{kind}_review'
    data['side_state'] = None
    write_yaml_atomic(project / 'project.yaml', data)
    assert card(project)['followup'] is None
    report(project, gate=kind)
    assert 'Đã sửa theo D1=b' in card(project)['followup']


def test_card_all_keep_records_choices_in_approval(gate):
    from tests.workflows.test_decision_card import decision, report
    line_id = read_yaml(gate[1] / 'revisions/001/script/script.yaml')['lines'][0]['id']
    report(gate[1], decisions=[decision(line_id)], preserve_script=True)
    _decide(gate, action='card', choices={'D1': 'a'}, pin='918273')
    approval = read_yaml(gate[1] / 'revisions/001/reviews/medical-approval.yaml')
    assert approval['note'] == f'D1 ({line_id}) → a: Giữ nguyên'


@pytest.mark.parametrize('other', ['', 'Sửa cách diễn đạt'])
def test_card_preserves_existing_draft_comments(gate, other):
    root, project, _ = gate
    dashboard.save_comment(root, project.name, 'chung', 'Góp ý cần giữ lại')
    _decide(gate, action='card', choices={}, other=other, pin='918273')
    rev = project / 'revisions/001'
    if other:
        record = read_yaml(next((rev / 'reviews/medical').glob('*-rejected.yaml')))
        assert 'Góp ý cần giữ lại' in record['reason']
    else:
        assert 'Góp ý cần giữ lại' in read_yaml(rev / 'reviews/medical-approval.yaml')['note']


def test_card_get_route(server):
    srv, project, _ = server
    status, body = request(srv, 'GET', f'/api/projects/{project.name}/card')
    assert status == 200
    assert json.loads(body)['decisions'] == []
    assert request(srv, 'GET', '/api/projects/missing/card')[0] == 404


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


def test_decide_restarts_stopped_factory_without_acceptance_standards(gate, monkeypatch):
    monkeypatch.setattr(factory, 'running_pid', lambda _: None)
    calls = []
    monkeypatch.setattr(factory, 'start_background', lambda root: calls.append(root))
    message = _decide(gate, action='approve', pin='918273')
    assert 'Đã duyệt' in message
    assert 'Đã bật xưởng' in message
    assert len(calls) == 1


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


def test_running_agents_reads_verified_marker_and_allows_live_chat_when_stopped(tmp_path, monkeypatch):
    from healthvideo.process import process_token

    gout_marker = tmp_path / 'topics' / 'logs' / 'gout' / dashboard.RUNNING_MARKER
    gout_marker.parent.mkdir(parents=True)
    # Legacy 2-line marker without identity must not be trusted as busy forever.
    gout_marker.write_text('codex\n2026-10-24T00:00:00\n', encoding='utf-8')
    monkeypatch.setattr(factory, 'running_pid', lambda _: 42)
    assert dashboard.running_agents(tmp_path) == []

    # Recycled PID (same PID, wrong creation token) must also be rejected.
    bad_ident = json.dumps({'job_id': 'j0', 'pid': os.getpid(), 'process_token': 'win:recycled',
                            'started_at': '2026-11-14T00:00:00+00:00'})
    gout_marker.write_text(f'codex\n2026-11-14T00:00:00+00:00\n{bad_ident}\n', encoding='utf-8')
    assert dashboard.running_agents(tmp_path) == []

    # Verified live chat marker works even when the factory daemon is stopped.
    monkeypatch.setattr(factory, 'running_pid', lambda _: None)
    chat_marker = tmp_path / 'topics' / 'logs' / 'chat' / dashboard.RUNNING_MARKER
    chat_marker.parent.mkdir(parents=True)
    live_ident = json.dumps({'job_id': 'j1', 'pid': os.getpid(), 'process_token': process_token(os.getpid()),
                             'started_at': '2026-11-14T00:00:00+00:00'})
    chat_marker.write_text(f'agy\n2026-11-14T00:00:00+00:00\n{live_ident}\n', encoding='utf-8')
    assert dashboard.running_agents(tmp_path) == ['agy']


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


@pytest.mark.parametrize('path', ['/api/topics/add', '/api/library/select', '/api/library/import',
                                  '/api/project/offline-topic/retry', '/api/project/offline-topic/reopen'])
def test_operations_routes_require_token_and_local_host(server, path):
    srv, _, _ = server
    assert request(srv, 'POST', path)[0] == 403
    assert request(srv, 'POST', path, headers={'Host': 'evil.test', 'X-Dashboard-Token': 'tok'})[0] == 403


def test_topics_and_operations_routes(live):
    srv, project = live
    status, data = post_json(srv, '/api/topics/add', {'slug': 'offline-topic', 'title': 'Offline', 'question': 'Fixture'})
    assert status == 200, data
    assert json.loads(request(srv, 'GET', '/api/topics')[1])['entries'][0]['slug'] == 'offline-topic'
    status, body = request(srv, 'GET', f'/api/project/{project.name}/operations')
    assert status == 200 and json.loads(body)['revision'] == '001'
    assert post_json(srv, f'/api/project/{project.name}/retry', {'expected_revision': '002'})[0] == 400
    assert post_json(srv, f'/api/project/{project.name}/reopen', {'confirmed': False})[0] == 400


def test_library_select_import_preview_and_no_client_paths(live, monkeypatch, tmp_path):
    from PIL import Image

    from healthvideo.workflows import asset_library

    srv, project = live
    source = tmp_path / 'picker.png'
    Image.new('RGB', (32, 24), 'green').save(source)
    monkeypatch.setattr(asset_library, 'choose_image', lambda: source)
    # The browser cannot use either import or the picker to read arbitrary paths.
    for route in ('import', 'select'):
        assert post_json(srv, f'/api/library/{route}', {'slug': project.name, 'source': str(source)})[0] == 400
    status, body = post_json(srv, '/api/library/select', {'slug': project.name, 'expected_revision': '001'})
    assert status == 200, body
    selection = body['message']['selection_id']
    payload = {'slug': project.name, 'expected_revision': '001', 'selection_id': selection,
                   'origin': 'Muse AI', 'prompt': 'Offline fixture green', 'license': 'Fixture permission',
                   'source_url': 'https://example.test/fixture'}
    assert post_json(srv, '/api/library/import', payload)[0] == 200
    assert post_json(srv, '/api/library/import', payload)[0] == 400
    status, data = request(srv, 'GET', '/api/library?kind=imported&query=green')
    assert status == 200
    asset = json.loads(data)['items'][0]
    assert asset['slug'] == project.name
    conn = HTTPConnection('127.0.0.1', srv.server_address[1])
    conn.request('GET', f"/media/{project.name}/library/{asset['id']}")
    response = conn.getresponse()
    assert response.status == 200
    assert response.read().startswith(b'\x89PNG')
    conn.close()
    assert request(srv, 'GET', f'/media/{project.name}/library/..%2F..%2Fpicker.png')[0] == 404


def test_media_rejects_escaped_render_directory(tmp_path):
    project = create_v2_project_fixture(tmp_path / 'projects')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret.png').write_bytes(b'secret')
    renders = project / 'revisions/001/renders'
    try:
        renders.symlink_to(outside, target_is_directory=True)
    except OSError:
        import _winapi

        _winapi.CreateJunction(str(outside), str(renders))
    from healthvideo.domain.project_v2 import ProjectManifestV2
    with pytest.raises(LookupError):
        dashboard.media_file(project, ProjectManifestV2.model_validate(read_yaml(project / 'project.yaml')), 'secret.png')


@pytest.mark.parametrize('mode', ['unconfigured', 'missing', 'wrong', 'locked', 'shared_lock', 'valid'])
def test_reopen_pin_and_feedback(server, monkeypatch, mode):
    from datetime import UTC, datetime

    from healthvideo.approver_pin import set_pin
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.workflows import standards
    from healthvideo.workflows.gate_review import approve_gate

    srv, project, _ = server
    monkeypatch.setattr(dashboard, 'reviewer_name', lambda: 'Configured doctor')
    pin_file = srv.root / 'config/approver-pin.json'
    if mode != 'unconfigured':
        set_pin('918273', path=pin_file)
    if mode == 'shared_lock':
        for _ in range(4):
            with pytest.raises(PermissionError):
                dashboard.decide(srv.root, project,
                                 {'revision': '001', 'action': 'approve', 'pin': 'bad'}, limiter=srv.limiter)
    approve_gate(project, GateKind.MEDICAL, reviewer='Fixture', now=datetime.now(UTC))
    standards.record(srv.root, slug='prior', gate='medical', revision='001', kind='comment', text='Keep prior')
    prior = standards.load(srv.root)
    before = {p.relative_to(project): p.read_bytes() for p in project.rglob('*') if p.is_file()}
    body = {'expected_revision': '001', 'confirmed': True, 'reviewer': 'Body doctor',
            'reason': 'Replace the fixture image', 'changed': ['storyboard/storyboard.yaml']}
    url = f'/api/project/{project.name}/reopen'
    if mode in {'locked', 'shared_lock'}:
        for _ in range(5 if mode == 'locked' else 1):
            assert post_json(srv, url, {**body, 'pin': 'bad'})[0] == 403
        assert srv.limiter.locked_until > srv.limiter.clock()
    if mode != 'missing':
        body['pin'] = 'bad' if mode == 'wrong' else '918273'
    status, payload = post_json(srv, url, body)
    if mode != 'valid':
        assert status == (400 if mode == 'unconfigured' else 403), payload
        assert {p.relative_to(project): p.read_bytes() for p in project.rglob('*') if p.is_file()} == before
        assert standards.load(srv.root) == prior
    else:
        assert status == 200, payload
        assert read_yaml(project / 'project.yaml')['state'] == 'needs_medical_revision'
        entries = standards.load(srv.root)
        assert entries[:-1] == prior
        assert entries[-1]['text'] == body['reason']
        assert entries[-1]['reviewer'] == 'Configured doctor'
        assert entries[-1]['kind'] == 'reopen'
        assert '918273' not in (srv.root / 'profiles/doctor-feedback.yaml').read_text(encoding='utf-8')


def _with_server(tmp_path, fn):
    srv = dashboard.DashboardServer(tmp_path, 0, token='tok', agents=list)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        return fn(srv)
    finally:
        srv.shutdown()
        srv.server_close()


def test_overview_shape(tmp_path):
    from datetime import datetime, timedelta

    from healthvideo.agents import QUOTA_FILE, QuotaBook
    from healthvideo.company import ModelSlot

    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    now = datetime.now().astimezone()
    QuotaBook(tmp_path / QUOTA_FILE).rest(
        ModelSlot(cli='codex', model='gpt-6-astra'), now + timedelta(hours=2), 'usage limit'
    )

    def check(srv):
        status, body = request(srv, 'GET', '/api/overview')
        assert status == 200
        data = json.loads(body)
        assert {'tiles', 'decisions', 'projects', 'resting', 'channel'} <= set(data)
        assert set(data['tiles']) == {
            'running', 'waiting_doctor', 'done_7d', 'done_30d',
            'avg_days_topic_to_video', 'models_resting',
        }
        assert data['tiles']['waiting_doctor'] == 1
        assert data['tiles']['models_resting'] == 1
        assert data['channel']['connected'] is False
        assert len(data['decisions']) == 1
        assert {'slug', 'title', 'gate', 'count'} <= set(data['decisions'][0])
        assert data['decisions'][0]['slug'] == project.name
        assert data['decisions'][0]['gate'] == 'medical'
        assert len(data['projects']) == 1
        assert {'slug', 'title', 'stage_index', 'state', 'preview_url', 'status_line'} <= set(data['projects'][0])
        assert len(data['resting']) == 1

    _with_server(tmp_path, check)


def test_activity_drops_job_whose_process_died(tmp_path, monkeypatch):
    from healthvideo.process import process_token
    from healthvideo.workflows.dashboard import activity
    monkeypatch.setattr(factory, 'running_pid', lambda _: 42)
    log = tmp_path / 'topics/logs/activity.jsonl'
    log.parent.mkdir(parents=True, exist_ok=True)
    live_tok = process_token(os.getpid())
    rows = [
        {'at': '2026-11-13T22:08:56+07:00', 'role': 'coordinator', 'cli': 'agy', 'model': 'm',
         'slug': 'chung', 'step': 'coordinator', 'event': 'start', 'ok': None,
         'pid': 2 ** 30, 'process_token': 'win:dead', 'job_id': 'dead-job'},
        {'at': '2026-11-13T22:09:00+07:00', 'role': 'writer', 'cli': 'agy', 'model': 'm',
         'slug': 'gout', 'step': 'draft', 'event': 'start', 'ok': None,
         'pid': os.getpid(), 'process_token': live_tok, 'job_id': 'live-job'},
    ]
    log.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')
    data = activity(tmp_path)
    assert [item['step'] for item in data['running']] == ['draft']
    assert data['recent'][0]['interrupted'] is True


def test_activity_running_job_listed(tmp_path, monkeypatch):
    from healthvideo.process import process_token

    monkeypatch.setattr(factory, 'running_pid', lambda _: 42)
    log = tmp_path / 'topics/logs/activity.jsonl'
    log.parent.mkdir(parents=True, exist_ok=True)
    live_tok = process_token(os.getpid())
    rows = [
        {'at': '2026-11-08T10:00:00+07:00', 'role': 'medical_expert', 'cli': 'claude',
         'model': 'claude-opus-5-5', 'slug': 'gout', 'step': 'research', 'event': 'start', 'ok': None},
        {'at': '2026-11-08T10:02:00+07:00', 'role': 'medical_expert', 'cli': 'claude',
         'model': 'claude-opus-5-5', 'slug': 'gout', 'step': 'research', 'event': 'end', 'ok': True},
        {'at': '2026-11-08T10:05:00+07:00', 'role': 'writer', 'cli': 'agy',
         'model': 'claude-opus-5-5-high', 'slug': 'gout', 'step': 'draft', 'event': 'start', 'ok': None,
         'pid': os.getpid(), 'process_token': live_tok, 'job_id': 'job-draft-1'},
    ]
    log.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')

    def check(srv):
        status, body = request(srv, 'GET', '/api/activity?limit=10')
        assert status == 200
        data = json.loads(body)
        assert len(data['running']) == 1
        assert data['running'][0]['step'] == 'draft'
        assert data['running'][0]['model'] == 'claude-opus-5-5-high'
        assert data['running'][0]['running'] is True
        assert any(item['step'] == 'research' and item['ok'] is True for item in data['recent'])
        assert any(item['step'] == 'draft' and item['running'] is True for item in data['items'])

    _with_server(tmp_path, check)


def test_timeline_from_render_input(tmp_path):
    from healthvideo.storage.files import write_yaml_atomic

    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    rev = project / 'revisions/001'
    renders = rev / 'renders'
    renders.mkdir(parents=True, exist_ok=True)
    (renders / 'render-input.json').write_text(json.dumps({
        'fps': 30,
        'scenes': [
            {'id': 'S01', 'start_frame': 0, 'duration_frames': 90},
            {'id': 'S07', 'start_frame': 90, 'duration_frames': 150},
        ],
    }), encoding='utf-8')
    write_yaml_atomic(rev / 'reviews/changes/20261108-requested.yaml', {
        'at': '2026-11-08T10:00:00+07:00',
        'by': 'doctor-chat',
        'kind': 'edit_production',
        'brief': 'Đổi hình S07 sang dạng kim',
        'context': {'scene': 'S07', 'time_s': 4},
        'applied': False,
    })

    def check(srv):
        status, body = request(srv, 'GET', f'/api/projects/{project.name}/timeline')
        assert status == 200
        data = json.loads(body)
        assert data == [
            {'scene': 'S01', 'start_s': 0.0, 'end_s': 3.0, 'open_change': False},
            {'scene': 'S07', 'start_s': 3.0, 'end_s': 8.0, 'open_change': True},
        ]

    _with_server(tmp_path, check)


def test_timeline_missing_render_is_empty(tmp_path):
    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')

    def check(srv):
        status, body = request(srv, 'GET', f'/api/projects/{project.name}/timeline')
        assert status == 200
        assert json.loads(body) == []

    _with_server(tmp_path, check)


def test_html_has_sections_in_order():
    html = dashboard.HTML_PATH.read_text(encoding='utf-8')
    positions = [html.index(f'id="{sec}"') for sec in ('tiles', 'decisions', 'projects', 'activity', 'channel')]
    assert positions == sorted(positions)


def test_feedback_tab_removed():
    html = dashboard.HTML_PATH.read_text(encoding='utf-8')
    assert 'data-ops-tab="feedback"' not in html
    assert 'id="ops-feedback"' not in html


def test_general_feedback_routes_to_chat_input():
    html = dashboard.HTML_PATH.read_text(encoding='utf-8')
    marker = "$('pv-general').onclick="
    snippet = html.split(marker, 1)[1].splitlines()[0]
    assert "$('chat-input')" in snippet
    assert "$('chat-panel')" in snippet
    assert "$('gen-row')" not in snippet


def test_studio_route_launches_once_and_logs(tmp_path, monkeypatch):
    calls = []
    checks = []

    def ready(url, **kwargs):
        from contextlib import nullcontext
        from types import SimpleNamespace

        checks.append(url)
        if len(checks) == 1:
            raise OSError('Connection refused during startup')
        return nullcontext(SimpleNamespace(status=200))

    monkeypatch.setattr(dashboard, 'urlopen', ready)

    class FakeProc:
        def poll(self):
            return None

    monkeypatch.setattr(dashboard, 'resolve_pnpm_argv', lambda args: ['pnpm', *args])
    monkeypatch.setattr(
        dashboard.subprocess, 'Popen',
        lambda argv, **kw: calls.append((argv, kw)) or FakeProc(),
    )

    def check(srv):
        status, data = post_json(srv, '/api/studio', {})
        assert status == 200
        assert 'http' in data['url']
        assert calls[0][0] == ['pnpm', '--dir', 'video', 'exec', 'remotion', 'studio']
        assert (tmp_path / 'cache/studio.log').is_file()
        status2, data2 = post_json(srv, '/api/studio', {})
        assert status2 == 200
        assert data2['url'] == data['url']
        assert len(calls) == 1
        assert len(checks) >= 3

    _with_server(tmp_path, check)


def test_progress_counts_tasks_and_lists_work_in_progress(tmp_path):
    assert dashboard.progress(tmp_path)["total"] == 0
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "progress.yaml").write_text(
        "updated: '2026-11-11'\n"
        "phases:\n"
        "- id: P0\n"
        "  title: An toan\n"
        "  tasks:\n"
        "  - {id: '0.1', title: a, status: done, owner: claude}\n"
        "  - {id: '0.2', title: b, status: doing, owner: agy, note: n}\n"
        "  - {id: '0.3', title: c, status: bogus}\n",
        encoding="utf-8",
    )
    result = dashboard.progress(tmp_path)
    assert (result["done"], result["total"], result["updated"]) == (1, 3, "2026-11-11")
    assert [task["id"] for task in result["doing"]] == ["0.2"]
    assert result["phases"][0]["done"] == 1
    assert result["phases"][0]["tasks"][2]["status"] == "todo"


def test_company_route_returns_all_roles_recent_five_and_drops_dead_pid(tmp_path, monkeypatch):
    from healthvideo.process import process_token

    monkeypatch.setattr(factory, 'running_pid', lambda _: 42)
    live_tok = process_token(os.getpid())
    log = tmp_path / 'topics/logs/activity.jsonl'
    log.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        # Dead-pid orphaned start for writer on gout at 09:00; 10:05 end is newer & ok=True.
        {'at': '2026-11-12T09:00:00+07:00', 'role': 'writer', 'cli': 'codex',
         'model': 'gpt-6.1-sol', 'slug': 'gout', 'step': 'draft', 'event': 'start',
         'ok': None, 'pid': 2 ** 30, 'process_token': 'win:dead', 'job_id': 'dead-w'},
        {'at': '2026-11-12T10:00:00+07:00', 'role': 'writer', 'cli': 'agy',
         'model': 'gemini-4-carbon-high', 'slug': 'gout', 'step': 'draft', 'event': 'start', 'ok': None},
        {'at': '2026-11-12T10:05:00+07:00', 'role': 'writer', 'cli': 'agy',
         'model': 'gemini-4-carbon-high', 'slug': 'gout', 'step': 'draft', 'event': 'end', 'ok': True},
    ]
    for i in range(6):
        t_start = f'2026-11-12T10:{10 + i * 2:02d}:00+07:00'
        t_end = f'2026-11-12T10:{11 + i * 2:02d}:00+07:00'
        rows.append({'at': t_start, 'role': 'medical_expert', 'cli': 'claude',
                     'model': 'claude-sonnet-5-5', 'slug': f'topic-{i}', 'step': 'research',
                     'event': 'start', 'ok': None})
        rows.append({'at': t_end, 'role': 'medical_expert', 'cli': 'claude',
                     'model': 'claude-sonnet-5-5', 'slug': f'topic-{i}', 'step': 'research',
                     'event': 'end', 'ok': i != 5})
    rows.append({'at': '2026-11-12T11:00:00+07:00', 'role': 'copywriter', 'cli': 'agy',
                 'model': 'gemini-pro-orchestrator', 'slug': 'gout', 'step': 'posts',
                 'event': 'start', 'ok': None, 'pid': os.getpid(),
                 'process_token': live_tok, 'job_id': 'copy-live'})
    log.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')

    def check(srv):
        status, body = request(srv, 'GET', '/api/company')
        assert status == 200
        data = json.loads(body)
        by_id = {role['id']: role for role in data['roles']}
        expected_roles = {
            'scout', 'medical_expert', 'writer', 'script_critic', 'art_director',
            'editor', 'product_critic', 'copywriter', 'coordinator',
            'coordinator_senior', 'feedback_analyst', 'repair_engineer',
        }
        assert expected_roles <= set(by_id)
        assert len(by_id) == 16
        assert by_id['writer']['running'] == []
        assert by_id['writer']['last_error'] is False
        assert len(by_id['copywriter']['running']) == 1
        assert by_id['copywriter']['running'][0]['step'] == 'posts'
        assert len(by_id['medical_expert']['recent']) == 5
        assert by_id['medical_expert']['recent'][0]['slug'] == 'topic-5'
        assert by_id['medical_expert']['last_error'] is True
        assert by_id['medical_expert']['models_used'] == [
            {'cli': 'claude', 'model': 'claude-sonnet-5-5', 'count': 6}
        ]
        assert by_id['scout']['name']
        assert by_id['scout']['configured_models']
        assert by_id['scout']['recent'] == []
        assert by_id['scout']['models_used'] == []
        assert by_id['scout']['last_error'] is False

    _with_server(tmp_path, check)


def test_company_route_keeps_both_roles_running_on_same_topic(tmp_path, monkeypatch):
    from healthvideo.process import process_token

    monkeypatch.setattr(factory, 'running_pid', lambda _: 42)
    live_tok = process_token(os.getpid())
    log = tmp_path / 'topics/logs/activity.jsonl'
    log.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {'at': '2026-11-12T10:00:00+07:00', 'role': 'writer', 'cli': 'agy',
         'model': 'gemini-4-carbon-high', 'slug': 'gout', 'step': 'draft',
         'event': 'start', 'ok': None, 'pid': os.getpid(), 'process_token': live_tok, 'job_id': 'w-1'},
        {'at': '2026-11-12T10:01:00+07:00', 'role': 'copywriter', 'cli': 'agy',
         'model': 'gemini-pro-orchestrator', 'slug': 'gout', 'step': 'posts',
         'event': 'start', 'ok': None, 'pid': os.getpid(), 'process_token': live_tok, 'job_id': 'c-1'},
    ]
    log.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')

    def check(srv):
        status, body = request(srv, 'GET', '/api/company')
        assert status == 200
        by_id = {role['id']: role for role in json.loads(body)['roles']}
        assert len(by_id['writer']['running']) == 1
        assert by_id['writer']['running'][0]['running'] is True
        assert by_id['writer']['running'][0]['slug'] == 'gout'
        assert len(by_id['copywriter']['running']) == 1
        assert by_id['copywriter']['running'][0]['running'] is True
        assert by_id['copywriter']['running'][0]['slug'] == 'gout'

    _with_server(tmp_path, check)


def test_stopped_pipeline_stays_idle_while_live_chat_works(tmp_path, monkeypatch):
    from healthvideo.process import process_token
    from healthvideo.storage.files import write_yaml_atomic

    monkeypatch.setattr(factory, 'running_pid', lambda _: None)
    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    manifest = read_yaml(project / 'project.yaml')
    manifest['state'] = 'production_in_progress'
    write_yaml_atomic(project / 'project.yaml', manifest)

    live_tok = process_token(os.getpid())
    log = tmp_path / 'topics/logs/activity.jsonl'
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({
        'at': '2026-11-14T15:00:00+07:00', 'role': 'coordinator', 'cli': 'agy',
        'model': 'gemini-4-hydrogen-medium', 'slug': 'chung', 'step': 'chat',
        'event': 'start', 'ok': None, 'pid': os.getpid(),
        'process_token': live_tok, 'job_id': 'chat-live-1',
    }) + '\n', encoding='utf-8')

    def check(srv):
        ov = json.loads(request(srv, 'GET', '/api/overview')[1])
        assert ov['tiles']['running'] == 0
        comp = json.loads(request(srv, 'GET', '/api/company')[1])
        by_id = {r['id']: r for r in comp['roles']}
        assert by_id['coordinator']['work_state'] == 'working'
        assert 'trả lời chat' in by_id['coordinator']['work_label'].lower()
        assert by_id['writer']['work_state'] == 'idle'
        assert by_id['editor']['work_state'] == 'idle'
        assert comp['production_running'] == []
        assert comp['production']['work_state'] == 'idle'

    _with_server(tmp_path, check)


def test_missing_dead_and_recycled_pid_are_never_busy(tmp_path):
    log = tmp_path / 'topics/logs/activity.jsonl'
    log.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        # Legacy orphan start missing pid/process_token/job_id
        {'at': '2026-11-14T10:00:00+07:00', 'role': 'scout', 'cli': 'agy',
         'model': 'gemini-4-hydrogen-medium', 'slug': 'q', 'step': 'scout',
         'event': 'start', 'ok': None},
        # Dead PID with token
        {'at': '2026-11-14T10:01:00+07:00', 'role': 'medical_expert', 'cli': 'agy',
         'model': 'gemini-4-carbon-high', 'slug': 'gout', 'step': 'research',
         'event': 'start', 'ok': None, 'pid': 2 ** 30,
         'process_token': 'win:dead', 'job_id': 'dead-1'},
        # Recycled PID: PID is alive (current process) but creation token does not match
        {'at': '2026-11-14T10:02:00+07:00', 'role': 'writer', 'cli': 'codex',
         'model': 'gpt-6.1-sol', 'slug': 'gout', 'step': 'draft',
         'event': 'start', 'ok': None, 'pid': os.getpid(),
         'process_token': 'win:recycled-token', 'job_id': 'recycled-1'},
    ]
    log.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')

    act = dashboard.activity(tmp_path)
    assert act['running'] == []
    comp = dashboard.company_roster(tmp_path)
    by_id = {r['id']: r for r in comp['roles']}
    assert by_id['scout']['running'] == []
    assert by_id['scout']['work_state'] in {'idle', 'unknown'}
    assert by_id['medical_expert']['running'] == []
    assert by_id['medical_expert']['work_state'] == 'idle'
    assert by_id['medical_expert']['last_error'] is False
    assert by_id['writer']['running'] == []
    assert by_id['writer']['work_state'] == 'idle'
    assert by_id['writer']['last_error'] is False


def test_same_role_concurrent_jobs_match_by_job_id(tmp_path):
    from healthvideo.process import process_token

    live_tok = process_token(os.getpid())
    log = tmp_path / 'topics/logs/activity.jsonl'
    log.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {'at': '2026-11-14T12:00:00+07:00', 'role': 'coordinator', 'cli': 'agy',
         'model': 'gemini-4-hydrogen-medium', 'slug': 'chung', 'step': 'chat',
         'event': 'start', 'ok': None, 'pid': os.getpid(),
         'process_token': live_tok, 'job_id': 'job-first'},
        {'at': '2026-11-14T12:00:05+07:00', 'role': 'coordinator', 'cli': 'agy',
         'model': 'gemini-4-hydrogen-medium', 'slug': 'chung', 'step': 'chat',
         'event': 'start', 'ok': None, 'pid': os.getpid(),
         'process_token': live_tok, 'job_id': 'job-second'},
        {'at': '2026-11-14T12:00:12+07:00', 'role': 'coordinator', 'cli': 'agy',
         'model': 'gemini-4-hydrogen-medium', 'slug': 'chung', 'step': 'chat',
         'event': 'end', 'ok': True, 'pid': os.getpid(),
         'process_token': live_tok, 'job_id': 'job-first'},
    ]
    log.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')

    act = dashboard.activity(tmp_path)
    assert [r['job_id'] for r in act['running']] == ['job-second']
    assert act['running'][0]['started_at'] == '2026-11-14T12:00:05+07:00'
    assert act['recent'][0]['job_id'] == 'job-first'
    assert act['recent'][0]['duration_s'] == 12.0


def test_production_running_requires_verified_marker_not_project_state(tmp_path, monkeypatch):
    from healthvideo.process import process_token
    from healthvideo.storage.files import write_yaml_atomic

    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    manifest = read_yaml(project / 'project.yaml')
    manifest['state'] = 'medically_approved'
    write_yaml_atomic(project / 'project.yaml', manifest)

    # Merely being in medically_approved or production_in_progress is not execution.
    comp = dashboard.company_roster(tmp_path)
    assert comp['production_running'] == []
    assert comp['production']['work_state'] == 'idle'

    marker = tmp_path / 'topics/logs' / project.name / '.production-running'
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text('{corrupt-json', encoding='utf-8')
    comp = dashboard.company_roster(tmp_path)
    assert comp['production_running'] == []
    assert comp['production']['work_state'] == 'unknown'

    marker.write_text(json.dumps({
        'pid': os.getpid(), 'process_token': 'win:recycled', 'started_at': '2026-11-14T08:00:00+00:00',
    }), encoding='utf-8')
    comp = dashboard.company_roster(tmp_path)
    assert comp['production_running'] == []
    assert comp['production']['work_state'] == 'idle'

    monkeypatch.setattr(factory, 'running_pid', lambda _: 42)
    marker.write_text(json.dumps({
        'pid': os.getpid(), 'process_token': process_token(os.getpid()),
        'started_at': '2026-11-14T08:00:00+00:00',
    }), encoding='utf-8')
    comp = dashboard.company_roster(tmp_path)
    assert len(comp['production_running']) == 1
    assert comp['production_running'][0]['slug'] == project.name
    assert comp['production']['work_state'] == 'working'


def _create_named_v2_project(
    projects_dir,
    slug: str,
    state: str,
    *,
    resume_state: str | None = None,
):
    from healthvideo.storage.files import write_yaml_atomic

    project = create_v2_project_fixture(projects_dir, state='awaiting_medical_review')
    target = projects_dir / slug
    project.rename(target)
    manifest = read_yaml(target / 'project.yaml')
    manifest['slug'] = slug
    manifest['state'] = state
    if state in {'needs_medical_revision', 'needs_production_revision', 'blocked'}:
        manifest['side_state'] = {
            'type': state,
            'resume_state': resume_state or 'draft_ready',
            'reason_code': 'test_side_state',
            'entered_at': '2026-11-14T10:00:00+00:00',
        }
    elif state == 'topic_rejected':
        manifest['side_state'] = {
            'type': state,
            'reason_code': 'test_rejected',
            'entered_at': '2026-11-14T10:00:00+00:00',
        }
    else:
        manifest['side_state'] = None
    write_yaml_atomic(target / 'project.yaml', manifest)
    return target


def test_quota_retry_error_and_malformed_sidecar_states(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from healthvideo.agents import QUOTA_FILE, QuotaBook
    from healthvideo.company import load_company
    from healthvideo.storage.files import write_yaml_atomic

    monkeypatch.setattr(factory, 'running_pid', lambda _: None)
    fixed_now = datetime(2026, 11, 14, 15, 0, 0, tzinfo=UTC)
    company = load_company()
    quota = QuotaBook(tmp_path / QUOTA_FILE)

    # 1. Resting just one model in writer's chain does not mark writer waiting_model.
    _create_named_v2_project(
        tmp_path / 'projects', 'bai-viet', 'needs_medical_revision',
        resume_state='awaiting_medical_review',
    )
    quota.rest(company.chain('writer')[0], fixed_now + timedelta(hours=2), '429')

    # 2. Resting ALL models of bulk chain marks copywriter waiting_model when topic waits,
    #    while scout (no topic waiting) remains idle.
    for slot in company.chain('scout'):
        quota.rest(slot, fixed_now + timedelta(hours=1), 'quota')
    p_posts = _create_named_v2_project(tmp_path / 'projects', 'bai-dang', 'production_in_progress')
    posts_log = tmp_path / 'topics/logs/bai-dang'
    posts_log.mkdir(parents=True, exist_ok=True)
    (posts_log / 'waiting-model.txt').write_text((fixed_now + timedelta(minutes=45)).isoformat(), encoding='utf-8')
    # Remove posts.yaml if present so posts is the pending step on bai-dang.
    posts_yaml = p_posts / 'revisions/001/posts/posts.yaml'
    if posts_yaml.exists():
        posts_yaml.unlink()

    # 3. Valid transient agent-retry.yaml with future retry_after -> waiting_retry.
    _create_named_v2_project(tmp_path / 'projects', 'nghien-cuu', 'research_in_progress')
    write_yaml_atomic(tmp_path / 'topics/logs/nghien-cuu/agent-retry.yaml', {
        'version': 1,
        'steps': {
            'research': {
                'fingerprint': 'fp1',
                'kind': 'transient',
                'attempts': 1,
                'reason': 'TimeoutExpired: network slow',
                'retry_after': (fixed_now + timedelta(minutes=2)).isoformat(),
            },
        },
    })

    # 4. Malformed agent-retry.yaml -> handled safely without faking retry or busy.
    _create_named_v2_project(tmp_path / 'projects', 'cham-bai', 'draft_ready')
    bad_sidecar = tmp_path / 'topics/logs/cham-bai/agent-retry.yaml'
    bad_sidecar.parent.mkdir(parents=True, exist_ok=True)
    bad_sidecar.write_text('version: 1\nsteps: [not-a-dict\n', encoding='utf-8')

    # 5. Blocked project at editor -> error.
    _create_named_v2_project(
        tmp_path / 'projects', 'sua-hinh', 'needs_production_revision',
        resume_state='production_in_progress',
    )
    ed_log = tmp_path / 'topics/logs/sua-hinh'
    ed_log.mkdir(parents=True, exist_ok=True)
    (ed_log / 'blocked.txt').write_text('bước revise_production lỗi: invalid svg\n', encoding='utf-8')

    comp = dashboard.company_roster(tmp_path, now=lambda: fixed_now)
    by_id = {r['id']: r for r in comp['roles']}
    assert by_id['writer']['work_state'] == 'idle'
    assert by_id['scout']['work_state'] == 'idle'
    assert by_id['copywriter']['work_state'] == 'waiting_model'
    assert 'Chờ model' in by_id['copywriter']['work_label']
    assert by_id['medical_expert']['work_state'] == 'waiting_retry'
    assert 'Chờ thử lại' in by_id['medical_expert']['work_label']
    assert by_id['script_critic']['work_state'] in {'unknown', 'error'}
    assert by_id['editor']['work_state'] == 'error'


def test_html_includes_workshop_3d_and_preserves_section_order():
    html = dashboard.HTML_PATH.read_text(encoding='utf-8')
    positions = [
        html.index(f'id="{sec}"')
        for sec in ('tiles', 'decisions', 'projects', 'workshop', 'activity', 'channel')
    ]
    assert positions == sorted(positions)
    assert 'prefers-reduced-motion: reduce' in html
    assert 'id="btn-ws-motion"' in html
    assert 'pyh-ws-motion' in html
    assert 'visibilitychange' in html
    assert 'IntersectionObserver' in html
    assert 'Chưa xác minh' in html
    assert 'Chờ model' in html
    assert 'Chờ thử lại' in html
    assert 'Máy dựng (xưởng tự chạy)' in html
    assert 'medically_approved' in html
    assert 'production_in_progress' in html
    # Render machine working state must come from verified production execution, not project.state.
    assert "p => (p.state === 'medically_approved' || p.state === 'production_in_progress') && !p.blocked" not in html
    for action_cls in (
        'ws-act-researcher', 'ws-act-scout', 'ws-act-medical', 'ws-act-writer',
        'ws-act-storyboard', 'ws-act-voice', 'ws-act-critic',
        'ws-act-art', 'ws-act-editor', 'ws-act-copywriter', 'ws-act-shorts',
        'ws-act-coordinator', 'ws-act-analyst',
    ):
        assert action_cls in html
    assert html.count('https://fonts.googleapis.com') <= 2
    assert 'cdn.' not in html.lower() and 'unpkg' not in html.lower() and 'jsdelivr' not in html.lower()


def test_html_workshop_places_all_16_roles_including_repair_engineer():
    import re

    from healthvideo.company import load_company

    html = dashboard.HTML_PATH.read_text(encoding='utf-8')
    counter_match = re.search(r"const WS_COUNTER_BASE = \[([^\]]+)\];", html)
    assert counter_match is not None
    counter_ids = re.findall(r"'([^']+)'", counter_match.group(1))
    assert counter_ids == ['coordinator', 'coordinator_senior', 'feedback_analyst', 'repair_engineer']

    workshop_slice = html[html.index('const WS_LINE_1 ='):html.index('const WS_SHIRTS =')]
    company = load_company()
    assert len(company.roles) == 16
    for role_id in company.roles:
        assert f"'{role_id}'" in workshop_slice, role_id


def test_marker_non_string_job_id_is_rejected(tmp_path, monkeypatch):
    from healthvideo.agents import RUNNING_MARKER
    from healthvideo.process import process_token

    monkeypatch.setattr(factory, 'running_pid', lambda _: 42)
    live_tok = process_token(os.getpid())

    _create_named_v2_project(tmp_path / 'projects', 'bool-job', 'evidence_ready')
    _create_named_v2_project(tmp_path / 'projects', 'int-job', 'research_in_progress')

    bool_marker = tmp_path / 'topics/logs/bool-job' / RUNNING_MARKER
    bool_marker.parent.mkdir(parents=True, exist_ok=True)
    bool_meta = json.dumps({
        'pid': os.getpid(), 'process_token': live_tok,
        'job_id': True, 'step': 'draft', 'started_at': '2026-11-14T10:00:00+00:00',
    })
    bool_marker.write_text(f'agy\n2026-11-14T10:00:00+00:00\n{bool_meta}\n', encoding='utf-8')

    int_marker = tmp_path / 'topics/logs/int-job' / RUNNING_MARKER
    int_marker.parent.mkdir(parents=True, exist_ok=True)
    int_meta = json.dumps({
        'pid': os.getpid(), 'process_token': live_tok,
        'job_id': 123, 'step': 'research', 'started_at': '2026-11-14T10:00:00+00:00',
    })
    int_marker.write_text(f'agy\n2026-11-14T10:00:00+00:00\n{int_meta}\n', encoding='utf-8')

    assert dashboard._read_agent_marker(bool_marker)['state'] == 'unverified'
    assert dashboard._read_agent_marker(int_marker)['state'] == 'unverified'
    assert dashboard.activity(tmp_path)['running'] == []

    by_id = {r['id']: r for r in dashboard.company_roster(tmp_path)['roles']}
    assert by_id['writer']['work_state'] == 'unknown'
    assert by_id['medical_expert']['work_state'] == 'unknown'

    valid_meta = json.dumps({
        'pid': os.getpid(), 'process_token': live_tok,
        'job_id': 'real-job-1', 'step': 'draft', 'started_at': '2026-11-14T10:00:00+00:00',
    })
    bool_marker.write_text(f'agy\n2026-11-14T10:00:00+00:00\n{valid_meta}\n', encoding='utf-8')
    assert dashboard._read_agent_marker(bool_marker)['state'] == 'running'


def test_waiting_model_step_precedence_staleness_terminal_and_corrupt(tmp_path, monkeypatch):
    from datetime import UTC, date, datetime, timedelta

    from healthvideo.agents import QUOTA_FILE, RUNNING_MARKER, QuotaBook
    from healthvideo.company import load_company
    from healthvideo.domain.queue import QueueEntry
    from healthvideo.storage.files import write_yaml_atomic
    from healthvideo.storage.queue import add_to_queue, queue_path
    from healthvideo.workflows import production_retry

    monkeypatch.setattr(factory, 'running_pid', lambda _: None)
    fixed_now = datetime(2026, 11, 14, 15, 0, 0, tzinfo=UTC)

    # 1. Non-dict YAML in waiting-model-step.yaml does not raise AttributeError.
    _create_named_v2_project(tmp_path / 'projects', 'bad-list-resume', 'draft_ready')
    bad_list_path = tmp_path / 'topics/logs/bad-list-resume/waiting-model-step.yaml'
    bad_list_path.parent.mkdir(parents=True, exist_ok=True)
    bad_list_path.write_text('- not-a-mapping\n', encoding='utf-8')

    # 2. Terminal projects are ignored even when waiting-model-step.yaml / waiting-model.txt exist.
    for idx, t_state in enumerate(('video_approved', 'packaged', 'published_manual', 'topic_rejected')):
        t_slug = f'done-{idx}'
        t_proj = _create_named_v2_project(tmp_path / 'projects', t_slug, t_state)
        production_retry.record_model_resume(tmp_path, t_proj, 'scout', '')
        (tmp_path / 'topics/logs' / t_slug / 'waiting-model.txt').write_text(
            (fixed_now + timedelta(hours=1)).isoformat(), encoding='utf-8',
        )

    # 3. agent-retry.yaml overrides waiting-model-step.yaml, and unverified_scopes uses final role.
    entry_a = QueueEntry(
        slug='prio-case', title='Tieu de', question='Cau hoi?', doctor_note=None, added=date(2026, 11, 10),
    )
    add_to_queue(tmp_path, entry_a)
    brief_a = json.dumps({'title': entry_a.title, 'question': entry_a.question, 'doctor_note': entry_a.doctor_note}, sort_keys=True)
    p_prio = _create_named_v2_project(tmp_path / 'projects', 'prio-case', 'awaiting_medical_review')
    production_retry.record_model_resume(tmp_path, p_prio, 'draft', brief_a)
    write_yaml_atomic(tmp_path / 'topics/logs/prio-case/agent-retry.yaml', {
        'version': 1,
        'steps': {
            'research': {
                'fingerprint': 'fp-res',
                'kind': 'transient',
                'attempts': 1,
                'reason': 'Timeout',
                'retry_after': (fixed_now + timedelta(minutes=5)).isoformat(),
            },
        },
    })
    (tmp_path / 'topics/logs/prio-case' / RUNNING_MARKER).write_text('{bad-json', encoding='utf-8')

    # 4. Stale waiting-model-step.yaml after brief change is ignored (not unknown).
    entry_s = QueueEntry(
        slug='stale-brief', title='Tieu de cu', question='Cau hoi?', doctor_note='Ghi chu A', added=date(2026, 11, 10),
    )
    add_to_queue(tmp_path, entry_s)
    brief_s = json.dumps({'title': entry_s.title, 'question': entry_s.question, 'doctor_note': entry_s.doctor_note}, sort_keys=True)
    p_stale = _create_named_v2_project(tmp_path / 'projects', 'stale-brief', 'awaiting_medical_review')
    production_retry.record_model_resume(tmp_path, p_stale, 'draft', brief_s)
    q_data = read_yaml(queue_path(tmp_path))
    for item in q_data['entries']:
        if item['slug'] == 'stale-brief':
            item['doctor_note'] = 'Ghi chu B'
    write_yaml_atomic(queue_path(tmp_path), q_data)

    by_id = {r['id']: r for r in dashboard.company_roster(tmp_path, now=lambda: fixed_now)['roles']}
    assert by_id['script_critic']['work_state'] == 'unknown'
    assert by_id['scout']['work_state'] == 'idle'
    assert by_id['medical_expert']['work_state'] == 'unknown'
    assert 'Marker thiếu định danh' in by_id['medical_expert']['work_detail']
    assert by_id['writer']['work_state'] == 'idle'

    # 5. Valid forced step at gate marks role_pending_work -> waiting_model when writer chain rests.
    entry_g = QueueEntry(
        slug='gate-forced', title='Gate', question='Hoi?', doctor_note=None, added=date(2026, 11, 10),
    )
    add_to_queue(tmp_path, entry_g)
    brief_g = json.dumps({'title': entry_g.title, 'question': entry_g.question, 'doctor_note': entry_g.doctor_note}, sort_keys=True)
    p_gate = _create_named_v2_project(tmp_path / 'projects', 'gate-forced', 'awaiting_medical_review')
    production_retry.record_model_resume(tmp_path, p_gate, 'draft', brief_g)
    quota = QuotaBook(tmp_path / QUOTA_FILE)
    for slot in load_company().chain('writer'):
        quota.rest(slot, fixed_now + timedelta(minutes=30), '429')
    by_id_gate = {r['id']: r for r in dashboard.company_roster(tmp_path, now=lambda: fixed_now)['roles']}
    assert by_id_gate['writer']['work_state'] == 'waiting_model'

    # 6. Corrupt waiting-model-step.yaml at gate (owner_role=None) maps saved_step to role or avoids crash.
    _create_named_v2_project(tmp_path / 'projects', 'corrupt-raw', 'awaiting_medical_review')
    raw_bad = tmp_path / 'topics/logs/corrupt-raw/waiting-model-step.yaml'
    raw_bad.parent.mkdir(parents=True, exist_ok=True)
    raw_bad.write_text('not: [valid\n', encoding='utf-8')
    dashboard.company_roster(tmp_path, now=lambda: fixed_now)

    _create_named_v2_project(tmp_path / 'projects', 'corrupt-step', 'awaiting_video_review')
    write_yaml_atomic(
        tmp_path / 'topics/logs/corrupt-step/waiting-model-step.yaml',
        {'version': 2, 'step': 'posts', 'fingerprint': 'abc'},
    )
    by_id_corrupt = {r['id']: r for r in dashboard.company_roster(tmp_path, now=lambda: fixed_now)['roles']}
    assert by_id_corrupt['copywriter']['work_state'] == 'unknown'


def test_extreme_boundary_timestamps_do_not_crash_on_windows(tmp_path, monkeypatch):
    from datetime import UTC, date, datetime

    from healthvideo.domain.project_v2 import WorkflowState
    from healthvideo.domain.queue import QueueEntry
    from healthvideo.storage.files import write_yaml_atomic
    from healthvideo.storage.queue import add_to_queue
    from healthvideo.workflows import production_retry

    monkeypatch.setattr(factory, 'running_pid', lambda _: None)
    min_now = datetime(1, 1, 1, 0, 0, 0, tzinfo=UTC)
    max_now = datetime(9999, 12, 31, 23, 59, 0, tzinfo=UTC)
    max_iso = '9999-12-31T23:59:59+00:00'
    min_iso = '0001-01-01T00:00:00+00:00'

    add_to_queue(
        tmp_path,
        QueueEntry(slug='min-done', title='Min', question='Q?', doctor_note=None, added=date(1, 1, 1)),
    )
    p_done = _create_named_v2_project(tmp_path / 'projects', 'min-done', 'video_approved')
    write_yaml_atomic(p_done / 'revisions/001/reviews/video-approval.yaml', {'reviewed_at': min_iso})

    _create_named_v2_project(tmp_path / 'projects', 'max-retry', 'production_in_progress')
    max_log = tmp_path / 'topics/logs/max-retry'
    max_log.mkdir(parents=True, exist_ok=True)
    (max_log / 'waiting-model.txt').write_text(max_iso, encoding='utf-8')
    posts_yaml = tmp_path / 'projects/max-retry/revisions/001/posts/posts.yaml'
    if posts_yaml.exists():
        posts_yaml.unlink()

    _create_named_v2_project(tmp_path / 'projects', 'max-agent', 'research_in_progress')
    write_yaml_atomic(tmp_path / 'topics/logs/max-agent/agent-retry.yaml', {
        'version': 1,
        'steps': {
            'research': {
                'fingerprint': 'fp-max',
                'kind': 'transient',
                'attempts': 1,
                'reason': 'Max deadline',
                'retry_after': max_iso,
            },
        },
    })

    p_prod = _create_named_v2_project(tmp_path / 'projects', 'max-prod', 'medically_approved')
    (p_prod / 'revisions/001/posts').mkdir(parents=True, exist_ok=True)
    write_yaml_atomic(p_prod / 'revisions/001/posts/posts.yaml', {'title': 'ok'})
    prod_fp = production_retry.production_fingerprint(tmp_path, p_prod, WorkflowState.MEDICALLY_APPROVED)
    write_yaml_atomic(tmp_path / 'topics/logs/max-prod/production-retry.yaml', {
        'fingerprint': prod_fp,
        'kind': 'transient',
        'attempts': 1,
        'reason': 'Render backoff',
        'retry_after': max_iso,
    })

    comp = dashboard.company_roster(tmp_path, now=lambda: min_now)
    by_id = {r['id']: r for r in comp['roles']}
    assert by_id['copywriter']['work_state'] == 'waiting_model'
    assert by_id['medical_expert']['work_state'] == 'waiting_retry'
    assert comp['production']['work_state'] == 'waiting_retry'

    ov_min = dashboard.overview(tmp_path, now=lambda: min_now)
    ov_max = dashboard.overview(tmp_path, now=lambda: max_now)
    snap = dashboard.snapshot(tmp_path)
    assert len(ov_min['projects']) == 4
    assert len(ov_max['projects']) == 4
    assert len(snap['projects']) == 4


def test_historical_activity_error_keeps_last_error_without_error_work_state(tmp_path, monkeypatch):
    monkeypatch.setattr(factory, 'running_pid', lambda _: None)
    log = tmp_path / 'topics/logs/activity.jsonl'
    log.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {'at': '2026-11-12T10:00:00+07:00', 'role': 'medical_expert', 'cli': 'claude',
         'model': 'claude-sonnet-5-5', 'slug': 'deleted-topic', 'step': 'research',
         'event': 'start', 'ok': None},
        {'at': '2026-11-12T10:01:00+07:00', 'role': 'medical_expert', 'cli': 'claude',
         'model': 'claude-sonnet-5-5', 'slug': 'deleted-topic', 'step': 'research',
         'event': 'end', 'ok': False},
    ]
    log.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')

    by_id = {r['id']: r for r in dashboard.company_roster(tmp_path)['roles']}
    assert by_id['medical_expert']['last_error'] is True
    assert by_id['medical_expert']['work_state'] == 'idle'


def test_corrupt_quota_and_approval_files_keep_overview_and_status_200(tmp_path, monkeypatch):
    from healthvideo.agents import QUOTA_FILE

    monkeypatch.setattr(factory, 'running_pid', lambda _: None)
    quota_path = tmp_path / QUOTA_FILE
    quota_path.parent.mkdir(parents=True, exist_ok=True)
    quota_path.write_text('models: [broken\n', encoding='utf-8')

    proj = _create_named_v2_project(tmp_path / 'projects', 'bad-approval', 'video_approved')
    approval = proj / 'revisions/001/reviews/video-approval.yaml'
    approval.parent.mkdir(parents=True, exist_ok=True)
    approval.write_text('- not-a-dict\n', encoding='utf-8')

    def check(srv):
        status_ov, body_ov = request(srv, 'GET', '/api/overview')
        assert status_ov == 200
        ov = json.loads(body_ov)
        assert ov['resting'] == []
        assert ov['tiles']['models_resting'] == 0
        assert len(ov['projects']) == 1

        status_st, body_st = request(srv, 'GET', '/api/status')
        assert status_st == 200
        assert len(json.loads(body_st)['projects']) == 1

    _with_server(tmp_path, check)


def test_company_20_routes_research_channel_and_cancel_job(tmp_path, monkeypatch):
    import subprocess
    import sys

    from healthvideo.process import process_token
    from healthvideo.storage.queue import load_queue
    from healthvideo.workflows import researcher

    monkeypatch.setattr(factory, 'running_pid', lambda _: None)

    class _FakeResp:
        def __init__(self, payload: bytes):
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req, timeout=20.0):
        url = getattr(req, 'full_url', str(req))
        if 'gid=728612942' in url:
            csv_text = (
                'phát_ngôn,hook_trung_lập,câu_hỏi_kiểm_chứng,PMID_DOI,phán_quyết_sơ_bộ,điểm_cần_bác_sĩ_duyệt\n'
                '"Uống nước chanh sáng chữa bách bệnh","Nước chanh buổi sáng có thật sự giải độc?","Uống nước chanh buổi sáng có tác dụng gì và rủi ro men răng ra sao?","PMID:31234567","Cần phân tách rõ lợi ích bù nước và hại men răng","Kiểm tra chống chỉ định dạ dày"\n'
            )
            return _FakeResp(csv_text.encode('utf-8'))
        return _FakeResp('tiêu_đề_Việt\n'.encode())

    monkeypatch.setattr(researcher, 'urlopen', fake_urlopen)

    proc = subprocess.Popen(
        [sys.executable, '-c', 'import time; time.sleep(30)'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        token = process_token(proc.pid)
        assert token
        job_dir = tmp_path / 'topics/logs/test-hung-slug'
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / '.job-job123.json').write_text(
            json.dumps({
                'job_id': 'job123',
                'slug': 'test-hung-slug',
                'role': 'writer',
                'step': 'draft',
                'child_pid': proc.pid,
                'child_process_token': token,
            }),
            encoding='utf-8',
        )

        def check(srv):
            st_sync, sync_data = post_json(srv, '/api/research/sync-sheet', {})
            assert st_sync == 200
            assert sync_data['synced_count'] == 1
            assert sync_data['total'] == 1

            st_inbox, raw_inbox = request(srv, 'GET', '/api/research/inbox')
            assert st_inbox == 200
            inbox_data = json.loads(raw_inbox)
            assert inbox_data['summary']['total'] == 1
            topic_slug = inbox_data['items'][0]['slug']

            st_prom, prom_data = post_json(
                srv, '/api/research/promote', {'slug': topic_slug, 'doctor_note': 'Ưu tiên'}
            )
            assert st_prom == 200
            assert prom_data['dossier']['status'] == 'selected'
            assert any(e.slug == topic_slug for e in load_queue(tmp_path))

            st_ch0, raw_ch0 = request(srv, 'GET', '/api/channel')
            assert st_ch0 == 200
            assert json.loads(raw_ch0)['videos_count'] == 0

            st_up, up_data = post_json(
                srv,
                '/api/channel/upsert',
                {
                    'slug': topic_slug,
                    'platform': 'youtube',
                    'title_used': 'Nước chanh buổi sáng dưới góc nhìn y khoa',
                    'views': 12500,
                    'ctr_pct': 6.4,
                    'retention_30s_pct': 71.0,
                    'shares_saves': 320,
                    'top_comments': 'Đau dạ dày uống được không?',
                },
            )
            assert st_up == 200
            assert up_data['total_videos'] == 1

            csv_payload = (
                'Video title,Views,Impressions click-through rate (%),Average percentage viewed (%),platform\n'
                'Ngủ đủ giấc phòng tim mạch,8400,5.2,62.5,youtube\n'
            )
            st_imp, imp_data = post_json(
                srv, '/api/channel/import-csv', {'csv_text': csv_payload, 'platform': 'youtube'}
            )
            assert st_imp == 200
            assert imp_data['imported_count'] == 1
            assert imp_data['total_videos'] == 2

            st_ch1, raw_ch1 = request(srv, 'GET', '/api/channel')
            assert st_ch1 == 200
            assert json.loads(raw_ch1)['videos_count'] == 2

            st_cancel, cancel_data = post_json(srv, '/api/jobs/cancel', {'job_id': 'job123'})
            assert st_cancel == 200
            assert len(cancel_data['cancelled']) == 1
            assert cancel_data['cancelled'][0]['job_id'] == 'job123'
            assert cancel_data['cancelled'][0]['terminated'] is True
            assert not (job_dir / '.job-job123.json').exists()

        _with_server(tmp_path, check)
        proc.wait(timeout=5)
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_review_bundle_and_overview_include_rich_inspector_fields(tmp_path):
    from healthvideo.storage.files import write_yaml_atomic

    project = _create_named_v2_project(tmp_path / 'projects', 'rich-topic', 'awaiting_video_review')
    rev = project / 'revisions/001'
    (rev / 'evidence/expert-brief.md').write_text('# Tom tat chuyen gia\nKhong dung thuoc tuy tien.', encoding='utf-8')
    write_yaml_atomic(rev / 'evidence/question.yaml', {
        'patient_population': 'Nguoi truong thanh',
        'intervention': 'Thuoc bo gan',
        'comparison': 'Khong dung',
        'outcome': 'An toan gan',
    })
    write_yaml_atomic(rev / 'script/voice-prep.yaml', {
        'pronunciations': [{'written': 'AST', 'spoken': 'a-es-te', 'note': 'Doc cham'}],
    })
    write_yaml_atomic(rev / 'posts/posts.yaml', {
        'youtube_titles': ['Tieu de thu nghiem'],
        'youtube_description': 'Mo ta ngan',
        'youtube_tags': ['gan', 'suc khoe'],
    })
    write_yaml_atomic(rev / 'posts/shorts-plan.yaml', {
        'clips': [{'id': 'clip-1', 'title': 'Hook ngan', 'start_scene_id': 's1', 'end_scene_id': 's2', 'target_seconds': 45}],
    })
    (rev / 'reviews/pronunciation-qa.json').write_text(json.dumps({
        'status': 'flagged',
        'blocked': True,
        'note': 'Can nghe lai',
        'model_id': 'whisper-test',
        'lines': [{'id': 'L01'}],
        'flags': [{'line': 'L01', 'script_word': 'ALT', 'heard': 'an-te'}],
    }), encoding='utf-8')
    logs_dir = tmp_path / 'topics' / 'logs' / 'rich-topic'
    logs_dir.mkdir(parents=True, exist_ok=True)
    write_yaml_atomic(logs_dir / 'paused.yaml', {'reason': 'Tam dung kiem tra'})
    (logs_dir / 'writer.log').write_text('dong 1\ndong 2\n', encoding='utf-8')

    def check(srv):
        st_ov, raw_ov = request(srv, 'GET', '/api/overview')
        assert st_ov == 200
        ov = json.loads(raw_ov)
        card = next(p for p in ov['projects'] if p['slug'] == 'rich-topic')
        assert card['paused'] is True
        assert card['counts']['has_brief'] is True
        assert card['counts']['has_posts'] is True
        assert card['counts']['claims'] >= 1

        st_b, raw_b = request(srv, 'GET', '/api/project/rich-topic/bundle')
        assert st_b == 200
        bundle = json.loads(raw_b)
        assert bundle['paused'] is True
        assert 'Tom tat chuyen gia' in bundle['expert_brief_md']
        assert bundle['research_meta']['question']['intervention'] == 'Thuoc bo gan'
        assert bundle['voice_prep']['pronunciations'][0]['written'] == 'AST'
        assert bundle['posts']['youtube_titles'] == ['Tieu de thu nghiem']
        assert bundle['shorts_plan']['clips'][0]['id'] == 'clip-1'
        assert bundle['qa_detail']['pronunciation_qa']['blocked'] is True
        assert bundle['qa_detail']['pronunciation_qa']['flagged'][0]['script_word'] == 'ALT'
        assert len(bundle['cli_logs']) == 1
        assert 'dong 2' in bundle['cli_logs'][0]['tail']

    _with_server(tmp_path, check)


def test_project_pause_resume_delete_and_restore_http_lifecycle(tmp_path):
    from datetime import date

    from healthvideo.domain.queue import QueueEntry
    from healthvideo.storage.queue import add_to_queue, load_queue

    add_to_queue(tmp_path, QueueEntry(
        slug='dup-topic',
        title='Chu de trung lap',
        question='Cau hoi thu nghiem trung lap?',
        added=date(2026, 11, 15),
    ))
    project = _create_named_v2_project(tmp_path / 'projects', 'dup-topic', 'draft_ready')

    def check(srv):
        assert request(srv, 'POST', '/api/project/dup-topic/pause')[0] == 403
        assert request(srv, 'POST', '/api/project/dup-topic/delete')[0] == 403
        assert post_json(srv, '/api/project/khong-ton-tai/pause', {})[0] == 404
        assert post_json(srv, '/api/project/khong-ton-tai/delete', {'confirmed': True})[0] == 404
        assert post_json(srv, '/api/project/dup-topic/delete', {'confirmed': False})[0] == 400

        st_pause, res_pause = post_json(srv, '/api/project/dup-topic/pause', {'reason': 'Cho kiem tra'})
        assert st_pause == 200
        assert res_pause['paused'] is True
        paused_file = tmp_path / 'topics/logs/dup-topic/paused.yaml'
        assert paused_file.is_file()

        st_resume, res_resume = post_json(srv, '/api/project/dup-topic/resume', {})
        assert st_resume == 200
        assert res_resume['paused'] is False
        assert not paused_file.exists()

        st_del, res_del = post_json(srv, '/api/project/dup-topic/delete', {
            'confirmed': True,
            'reason': 'Trung chu de',
        })
        assert st_del == 200
        assert res_del['deleted'] is True
        assert res_del['removed_from_queue'] is True
        assert not project.exists()
        assert load_queue(tmp_path) == []

        st_list, raw_list = request(srv, 'GET', '/api/projects/deleted')
        assert st_list == 200
        deleted_items = json.loads(raw_list)['items']
        assert len(deleted_items) == 1
        assert deleted_items[0]['id'] == res_del['archive_id']
        assert deleted_items[0]['slug'] == 'dup-topic'

        st_rest, res_rest = post_json(srv, '/api/projects/restore', {'id': res_del['archive_id']})
        assert st_rest == 200
        assert res_rest['paused'] is True
        assert res_rest['queue_added'] is True
        assert project.is_dir()
        assert paused_file.is_file()
        assert [e.slug for e in load_queue(tmp_path)] == ['dup-topic']

    _with_server(tmp_path, check)


def test_dashboard_html_contains_lifecycle_and_seven_tabs(server):
    srv, _, _ = server
    status, body = request(srv, 'GET', '/')
    assert status == 200
    lowered = body.lower()
    for bad in ('cdn.', 'unpkg', 'jsdelivr'):
        assert bad not in lowered
    for marker in (
        'id="del-dlg"',
        'id="ops-deleted-list"',
        'id="pv-pause"',
        'id="pv-retry"',
        'id="pv-folder"',
        'id="pv-delete"',
        'Tổng quan',
        'Nguồn',
        'Kịch bản',
        'Storyboard',
        'Video',
        'Bài đăng',
        'Nhật ký',
    ):
        assert marker in body

def _handler_of(tmp_path, monkeypatch, state, *, jobs=(), repair=None, blocked=None, paused=False):
    from healthvideo.storage.files import write_yaml_atomic

    project = create_v2_project_fixture(tmp_path / 'projects', state=state)
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True, exist_ok=True)
    if repair is not None:
        write_yaml_atomic(logs / 'leader-repair.yaml', repair)
    if blocked is not None:
        (logs / 'blocked.txt').write_text(blocked, encoding='utf-8')
    if paused:
        write_yaml_atomic(logs / 'paused.yaml', {'reason': 'Bác sĩ muốn xem lại'})
    live = [dict(job, slug=project.name) for job in jobs]
    monkeypatch.setattr(dashboard, '_active_running_jobs', lambda root: live)
    snap = next(p for p in dashboard.snapshot(tmp_path)['projects'] if p['slug'] == project.name)
    card = next(p for p in dashboard.overview(tmp_path)['projects'] if p['slug'] == project.name)
    assert snap['handler'] == card['handler']
    assert set(card['handler']) == {'label', 'kind', 'reason'}
    return card['handler']


def test_handler_running_job_is_agent(tmp_path, monkeypatch):
    handler = _handler_of(tmp_path, monkeypatch, 'draft_ready', jobs=[
        {'role': 'writer', 'step': 'revise_medical', 'step_label': 'Đang sửa theo góp ý y khoa'},
    ])
    assert handler['kind'] == 'agent'
    assert handler['label'].endswith('đang sửa theo góp ý y khoa')
    assert handler['label'].split(' đang')[0] == dashboard._role_names()['writer']


def test_handler_leader_repair_needs_attention_is_repair_with_reason(tmp_path, monkeypatch):
    handler = _handler_of(
        tmp_path, monkeypatch, 'draft_ready',
        blocked='Bước draft lỗi: schema sai\nlog_path: x.log',
        repair={'phase': 'needs_attention', 'attempts': 2,
                'incident': {'state': 'draft_ready', 'reason': 'Thiếu claim E06 trong ledger\nchi tiết khác'}},
    )
    assert handler['kind'] == 'repair'
    assert handler['reason'] == 'Thiếu claim E06 trong ledger'
    assert 'Leader' in handler['label']


def test_handler_leader_repair_diagnosing_names_leader(tmp_path, monkeypatch):
    handler = _handler_of(
        tmp_path, monkeypatch, 'draft_ready', blocked='Bước draft lỗi',
        repair={'phase': 'diagnosing', 'incident': {'state': 'draft_ready', 'reason': 'Lỗi tạm thời'}},
    )
    assert handler == {'label': 'Leader đang điều phối sửa lỗi', 'kind': 'repair', 'reason': 'Lỗi tạm thời'}


def test_handler_awaiting_medical_review_is_doctor(tmp_path, monkeypatch):
    handler = _handler_of(tmp_path, monkeypatch, 'awaiting_medical_review')
    assert handler['kind'] == 'doctor'
    assert handler['label'] == 'Chờ bác sĩ'


def test_handler_paused_is_paused(tmp_path, monkeypatch):
    handler = _handler_of(tmp_path, monkeypatch, 'draft_ready', paused=True)
    assert handler == {'label': 'Tạm dừng', 'kind': 'paused', 'reason': 'Bác sĩ muốn xem lại'}


def test_handler_blocked_without_repair_and_idle(tmp_path, monkeypatch):
    blocked = _handler_of(tmp_path, monkeypatch, 'draft_ready', blocked='Bước posts lỗi: thiếu file')
    assert blocked['kind'] == 'blocked'
    assert blocked['reason'] == 'Bước posts lỗi: thiếu file'
    idle = _handler_of(tmp_path / 'idle', monkeypatch, 'draft_ready')
    assert idle['kind'] == 'idle'


def _guidance_note(stuck='Độ chính xác y khoa 5, Hook 6'):
    from healthvideo.workflows import script_review

    return (f'{script_review.CYCLE_LIMIT_REASON} (9 vòng); tiêu chí kẹt: {stuck}. '
            'Bác sĩ gửi hướng dẫn cho Biên kịch qua chat để mở chu kỳ mới.')


def test_script_guidance_item_in_overview_and_doctor_handler(tmp_path, monkeypatch):
    handler = _handler_of(tmp_path, monkeypatch, 'draft_ready', blocked=_guidance_note())
    assert handler == {'label': 'Chờ bác sĩ hướng dẫn Biên kịch', 'kind': 'doctor',
                       'reason': 'Độ chính xác y khoa 5, Hook 6'}
    items = [d for d in dashboard.overview(tmp_path)['decisions'] if d.get('kind') == 'script_guidance']
    assert len(items) == 1
    item = items[0]
    assert item['stuck'] == 'Độ chính xác y khoa 5, Hook 6'
    assert item['rounds'] == 9
    assert 'Trạm 07 chưa đạt sau 3 chu kỳ' in item['message']
    assert {'slug', 'code', 'title'} <= set(item)


def test_script_guidance_ignores_other_blocked_reasons(tmp_path, monkeypatch):
    handler = _handler_of(tmp_path, monkeypatch, 'draft_ready', blocked='Bước posts lỗi: thiếu file')
    assert handler['kind'] == 'blocked'
    assert not any(d.get('kind') == 'script_guidance' for d in dashboard.overview(tmp_path)['decisions'])
