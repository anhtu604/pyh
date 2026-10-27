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
