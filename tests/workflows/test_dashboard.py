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
    assert data['factory'] == {'running': False, 'pid': None}
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


def test_activity_running_job_listed(tmp_path):
    log = tmp_path / 'topics/logs/activity.jsonl'
    log.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {'at': '2026-11-08T10:00:00+07:00', 'role': 'medical_expert', 'cli': 'claude',
         'model': 'claude-opus-5-5', 'slug': 'gout', 'step': 'research', 'event': 'start', 'ok': None},
        {'at': '2026-11-08T10:02:00+07:00', 'role': 'medical_expert', 'cli': 'claude',
         'model': 'claude-opus-5-5', 'slug': 'gout', 'step': 'research', 'event': 'end', 'ok': True},
        {'at': '2026-11-08T10:05:00+07:00', 'role': 'writer', 'cli': 'agy',
         'model': 'claude-opus-5-5-high', 'slug': 'gout', 'step': 'draft', 'event': 'start', 'ok': None},
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


def test_studio_route_launches_once_and_logs(tmp_path, monkeypatch):
    calls = []

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
