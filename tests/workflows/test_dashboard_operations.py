from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from healthvideo.domain.gate_review import GateKind
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import dashboard
from healthvideo.workflows import dashboard_operations as ops
from healthvideo.workflows.gate_review import approve_gate
from tests.helpers import create_v2_project_fixture


def test_topic_valid_duplicate_and_invalid(tmp_path):
    body = {'slug': 'offline-topic', 'title': 'Offline topic', 'question': 'Fixture question'}
    assert ops.add_topic(tmp_path, body)['slug'] == body['slug']
    before = (tmp_path / 'topics/queue.yaml').read_bytes()
    for invalid in (body, {**body, 'slug': '../escape'}, {**body, 'title': ' '}):
        with pytest.raises(ValueError):
            ops.add_topic(tmp_path, invalid)
    assert (tmp_path / 'topics/queue.yaml').read_bytes() == before
    assert not (tmp_path / 'projects').exists()


@pytest.fixture
def project(tmp_path, monkeypatch):
    from healthvideo.approver_pin import set_pin

    pin = tmp_path / 'config/pin.json'
    set_pin('918273', path=pin)
    monkeypatch.setattr(dashboard, 'pin_path', lambda: pin)
    monkeypatch.setattr(dashboard, 'reviewer_name', lambda: '')
    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    approve_gate(project, GateKind.MEDICAL, reviewer='Fixture doctor', now=datetime.now(UTC))
    monkeypatch.setattr(ops.factory, 'running_pid', lambda _: None)
    return tmp_path, project


def test_operations_read_only_and_cache_estimate(project):
    root, project = project
    before = (project / 'project.yaml').read_bytes()
    info = ops.project_operations(root, project.name)
    assert info['next_step'] == 'produce'
    assert info['revision'] == '001'
    assert info['cache']['verified_hits'] is None
    assert info['cache']['max_requests'] == len(read_yaml(project / 'revisions/001/script/script.yaml')['lines'])
    assert (project / 'project.yaml').read_bytes() == before


def test_retry_stale_busy_and_changed_approval_fail_before_clear(project, monkeypatch):
    root, project = project
    cleared = []
    monkeypatch.setattr(ops, '_retry_api', lambda: SimpleNamespace(
        clear_retry=lambda *args: cleared.append(args),
        retry_status=lambda *args: {'allowed': True},
    ))
    with pytest.raises(ValueError, match='Revision'):
        ops.retry_project(root, project.name, expected_revision='002')
    monkeypatch.setattr(ops.factory, 'running_pid', lambda _: 99)
    with pytest.raises(ValueError, match='dừng'):
        ops.retry_project(root, project.name, expected_revision='001')
    monkeypatch.setattr(ops.factory, 'running_pid', lambda _: None)
    path = project / 'revisions/001/script/script.yaml'
    data = read_yaml(path)
    data['lines'][0]['text'] += ' Fixture edit.'
    write_yaml_atomic(path, data)
    with pytest.raises(ValueError, match='y khoa'):
        ops.retry_project(root, project.name, expected_revision='001')
    assert not cleared
    assert read_yaml(project / 'project.yaml')['state'] == 'medically_approved'


def test_retry_clears_via_api_without_worker_or_approval_change(project, monkeypatch):
    root, project = project
    cleared = []
    monkeypatch.setattr(ops, '_retry_api', lambda: SimpleNamespace(
        clear_retry=lambda *args: cleared.append(args), retry_status=lambda *args: {'allowed': True},
    ))
    before = (project / 'project.yaml').read_bytes()
    result = ops.retry_project(root, project.name, expected_revision='001')
    assert cleared == [(root, project.name)]
    assert result['next_step'] == 'produce'
    assert (project / 'project.yaml').read_bytes() == before


def test_retry_does_not_release_unchanged_validation_failure(project, monkeypatch):
    root, project = project
    cleared = []
    monkeypatch.setattr(ops, '_retry_api', lambda: SimpleNamespace(
        clear_retry=lambda *args: cleared.append(args),
        retry_status=lambda *args: {'allowed': False, 'kind': 'validation', 'reason': 'Repair inputs first'},
    ))
    with pytest.raises(ValueError, match='Repair inputs'):
        ops.retry_project(root, project.name, expected_revision='001')
    assert cleared == []


def test_reopen_requires_explicit_reviewer_and_preserves_history(project):
    root, project = project
    args = {'limiter': dashboard.PinLimiter(), 'pin': '918273', 'expected_revision': '001', 'reviewer': '', 'reason': 'Fixture edit', 'changed': ['storyboard/storyboard.yaml']}
    with pytest.raises(ValueError, match='bác sĩ'):
        ops.reopen_project(root, project.name, **args)
    ops.reopen_project(root, project.name, **{**args, 'reviewer': 'Fixture doctor'})
    data = read_yaml(project / 'project.yaml')
    assert data['state'] == 'needs_medical_revision'
    assert data['side_state']['resume_state'] == 'draft_ready'
    rev = project / 'revisions/001'
    assert not (rev / 'reviews/medical-approval.yaml').exists()
    assert list((rev / 'reviews/medical').glob('*-superseded-approval.yaml'))


def test_reopen_refuses_reviews_junction_before_any_external_mutation(project):
    import os

    root, project = project
    rev = project / 'revisions/001'
    reviews = rev / 'reviews'
    outside = root / 'outside-reviews'
    reviews.rename(outside)
    if os.name == 'nt':
        import _winapi

        _winapi.CreateJunction(str(outside), str(reviews))
    else:
        reviews.symlink_to(outside, target_is_directory=True)
    before = {p.relative_to(outside): p.read_bytes() for p in outside.rglob('*') if p.is_file()}
    manifest = (project / 'project.yaml').read_bytes()
    with pytest.raises(ValueError, match='ngoài'):
        ops.reopen_project(root, project.name, expected_revision='001', reviewer='Fixture doctor',
                           reason='Fixture edit', changed=['storyboard/storyboard.yaml'],
                           limiter=dashboard.PinLimiter(), pin='918273')
    assert (project / 'project.yaml').read_bytes() == manifest
    assert {p.relative_to(outside): p.read_bytes() for p in outside.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('slug', ['../escape', 'C:/secret', 'a\\b'])
def test_project_traversal(tmp_path, slug):
    with pytest.raises((ValueError, LookupError)):
        ops.project_operations(tmp_path, slug)


def test_real_production_retry_integration_with_app_routes(project, monkeypatch):
    import json
    import threading
    from datetime import timedelta
    from http.client import HTTPConnection

    from healthvideo.domain.project_v2 import WorkflowState
    from healthvideo.workflows import production_retry

    root, project_dir = project
    clock = {'now': datetime(2026, 10, 25, 10, 0, 0, tzinfo=UTC)}
    monkeypatch.setattr(production_retry, '_now', lambda: clock['now'])

    srv = dashboard.DashboardServer(root, 0, token='tok', agents=list)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    port = srv.server_address[1]

    def call(method: str, path: str, payload: dict | None = None) -> tuple[int, dict | str]:
        conn = HTTPConnection('127.0.0.1', port, timeout=5)
        headers = {'Host': f'127.0.0.1:{port}', 'X-Dashboard-Token': 'tok'}
        body = None
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(payload).encode('utf-8')
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode('utf-8')
        ctype = resp.getheader('Content-Type', '')
        conn.close()
        return resp.status, (json.loads(raw) if ctype.startswith('application/json') else raw)

    try:
        retry_file = root / 'topics/logs' / project_dir.name / 'production-retry.yaml'

        # 1. Record real validation hold -> POST retry rejected while inputs unchanged
        production_retry.record_failure(
            root,
            project_dir,
            WorkflowState.MEDICALLY_APPROVED,
            ValueError('visual budget failed: chart_crop'),
        )
        assert retry_file.is_file()
        status, err = call('POST', f'/api/project/{project_dir.name}/retry', {'expected_revision': '001'})
        assert status == 400
        assert 'chart_crop' in err['error']
        assert retry_file.is_file()

        # 2. Repair storyboard (and re-approve medical gate so approval matches) -> fingerprint changes -> retry succeeds & deletes record
        board_path = project_dir / 'revisions/001/storyboard/storyboard.yaml'
        board_data = read_yaml(board_path)
        board_data['scenes'][0]['expected_duration_seconds'] = 14
        write_yaml_atomic(board_path, board_data)
        (project_dir / 'revisions/001/reviews/medical-approval.yaml').unlink()
        manifest_data = read_yaml(project_dir / 'project.yaml')
        manifest_data['state'] = 'awaiting_medical_review'
        write_yaml_atomic(project_dir / 'project.yaml', manifest_data)
        approve_gate(project_dir, GateKind.MEDICAL, reviewer='Fixture doctor', now=clock['now'])

        status, ok = call('POST', f'/api/project/{project_dir.name}/retry', {'expected_revision': '001'})
        assert status == 200, ok
        assert not retry_file.exists()
        assert ok['message']['retry_status']['allowed'] is True
        assert ok['message']['retry_status']['kind'] is None

        # 3. Record transient hold in backoff window -> app operations & UI surface retry_after
        production_retry.record_failure(
            root,
            project_dir,
            WorkflowState.MEDICALLY_APPROVED,
            RuntimeError('temporary provider timeout'),
        )
        assert retry_file.is_file()
        clock['now'] += timedelta(seconds=30)
        status, info = call('GET', f'/api/project/{project_dir.name}/operations')
        assert status == 200
        assert info['retry_status']['kind'] == 'transient'
        assert info['retry_status']['allowed'] is False
        expected_retry_after = (datetime(2026, 10, 25, 10, 0, 0, tzinfo=UTC) + timedelta(seconds=120)).isoformat()
        assert info['retry_status']['retry_after'] == expected_retry_after

        status, html = call('GET', '/')
        assert status == 200
        assert 'd.retry_status.retry_after' in html
    finally:
        srv.shutdown()
        srv.server_close()
