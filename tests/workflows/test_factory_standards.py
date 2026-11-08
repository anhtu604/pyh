import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import factory_trials as trials
from healthvideo.workflows import standards
from tests.helpers import create_v2_project_fixture, write_passing_script_review


@pytest.fixture(autouse=True)
def offline_renderer(monkeypatch):
    # Storage/gate tests inject the render boundary; media integration is exercised separately.
    def render(directory):
        path = directory / 'injected-render.txt'
        path.write_text('TEST renderer boundary', encoding='utf-8')
        return [path]
    from healthvideo.agents import AgentResult
    def fake_invoke(agents, prompt, *, cwd, log_dir, **_):
        rev = log_dir.parent / 'project/revisions/001'
        write_passing_script_review(rev)
        write_yaml_atomic(rev / 'script/script.yaml', {'lines': [{'id': 'L01', 'text': 'Synthetic trial line.'}]})
        log_path = log_dir / 'fake.log'
        log_path.write_text('ok', encoding='utf-8')
        return AgentResult(agent='fake', ok=True, quota_exhausted=False, log_path=log_path)
    monkeypatch.setattr(trials, '_render_samples', render)
    monkeypatch.setattr(trials, 'invoke_with_failover', fake_invoke)


def module():
    return importlib.import_module('healthvideo.workflows.factory_standards')


def ready(root, stage=1, text='Clear TEST standard'):
    trial = trials.create_trial(root, stage)
    trials.run_trial(root, trial['id'])
    bundle = trials.wait_trial(root, trial['id'])
    module().save_standard_draft(root, stage, text, trial['id'])
    return bundle


def accept(root, bundle, version=0):
    return module().accept_standard(root, bundle['stage'], trial_id=bundle['id'],
                                   expected_input_hash=bundle['input_hash'], expected_version=version,
                                   reviewer='Fixture reviewer', now=datetime.now(UTC))


def test_draft_is_not_acceptance_and_replay_rejected(tmp_path):
    bundle = ready(tmp_path)
    assert module().accepted_standards(tmp_path) == {}
    result = accept(tmp_path, bundle)
    assert result['version'] == 1
    assert result['scope'] == 'channel'
    with pytest.raises(ValueError):
        accept(tmp_path, bundle)
    assert len(read_yaml(tmp_path / 'profiles/factory-standards.yaml')['entries']) == 1


def test_order_failed_stale_and_empty_drafts(tmp_path):
    bundle = ready(tmp_path, 2)
    with pytest.raises(ValueError):
        accept(tmp_path, bundle)
    bundle = ready(tmp_path)
    with pytest.raises(ValueError):
        module().save_standard_draft(tmp_path, 1, ' ', bundle['id'])
    path = trials.trial_dir(tmp_path, bundle['id']) / 'trial.yaml'
    data = read_yaml(path)
    data['status'] = 'failed'
    write_yaml_atomic(path, data)
    with pytest.raises(ValueError):
        accept(tmp_path, bundle)
    data['status'] = 'ready'
    write_yaml_atomic(path, data)
    (path.parent / bundle['outputs'][0]['path']).write_text('tampered', encoding='utf-8')
    with pytest.raises(ValueError):
        accept(tmp_path, bundle)


def test_concurrent_tabs_only_accept_once(tmp_path):
    bundle = ready(tmp_path)
    def submit(_):
        try:
            return accept(tmp_path, bundle)['version']
        except ValueError:
            return 'stale'
    with ThreadPoolExecutor(2) as pool:
        assert sorted(map(str, pool.map(submit, range(2)))) == ['1', 'stale']


def test_snapshot_immutable_and_new_version_does_not_rewrite(tmp_path):
    project = create_v2_project_fixture(tmp_path / 'projects')
    for stage in range(1, 5):
        accept(tmp_path, ready(tmp_path, stage))
    path = module().pin_standards(tmp_path, project)
    before = path.read_bytes()
    assert accept(tmp_path, ready(tmp_path, 1, 'Improved standard'), 1)['version'] == 2
    assert module().pin_standards(tmp_path, project).read_bytes() == before
    block = standards.prompt_block(tmp_path, slug=project.name)
    assert 'Improved standard' not in block
    assert 'Clear TEST standard' in block


def test_feedback_scope_is_explicit(tmp_path):
    standards.record(tmp_path, slug='gout', gate='medical', revision='001', kind='comment', text='GOUT PRIVATE')
    standards.record(tmp_path, slug='chung', gate='chung', revision='-', kind='comment', text='SHARED NOTE')
    before = standards.feedback_path(tmp_path).read_bytes()
    assert 'GOUT PRIVATE' not in standards.prompt_block(tmp_path, slug='other')
    assert 'GOUT PRIVATE' in standards.prompt_block(tmp_path, slug='gout')
    assert 'SHARED NOTE' in standards.prompt_block(tmp_path, slug='other')
    assert standards.feedback_path(tmp_path).read_bytes() == before


def test_gate_hashes_cover_snapshot_and_deletion(tmp_path):
    from healthvideo.workflows.gate_review import (
        hash_reviewed_artifacts,
        medical_reviewed_paths,
        video_reviewed_paths,
    )
    project = create_v2_project_fixture(tmp_path / 'projects')
    for stage in range(1, 5):
        accept(tmp_path, ready(tmp_path, stage))
    snapshot = module().pin_standards(tmp_path, project)
    revision = snapshot.parents[1]
    for paths in (medical_reviewed_paths, video_reviewed_paths):
        before = hash_reviewed_artifacts(paths(revision))
        assert 'workflow/standards.yaml' in before
        original = snapshot.read_bytes()
        snapshot.write_bytes(original + b'\nextra: tampered\n')
        assert hash_reviewed_artifacts(paths(revision)) != before
        snapshot.write_bytes(original)
        snapshot.unlink()
        assert hash_reviewed_artifacts(paths(revision)) != before
        snapshot.write_bytes(original)


def test_start_needs_no_acceptance_standards(tmp_path, monkeypatch):
    from healthvideo.workflows import dashboard, factory
    calls = []
    monkeypatch.setattr(factory, 'start_background', lambda root: calls.append(root) or 123)
    server = dashboard.DashboardServer(tmp_path, 0)
    try:
        assert '123' in server.dispatch(['api', 'factory', 'start'])
        assert calls == [tmp_path.resolve()]
    finally:
        server.server_close()


def test_new_project_pins_accepted_configuration(tmp_path):
    from healthvideo.workflows.create_project_v2 import create_project_v2
    for stage in range(1, 5):
        accept(tmp_path, ready(tmp_path, stage))
    project = create_project_v2(tmp_path / 'projects', 'new-test', 'TEST', now=datetime.now(UTC))
    assert (project / 'revisions/001/workflow/standards.yaml').is_file()


def test_new_project_pins_only_the_standards_that_exist(tmp_path):
    from healthvideo.storage.files import read_yaml
    from healthvideo.workflows.create_project_v2 import create_project_v2
    create_project_v2(tmp_path / 'projects', 'new-test', 'TEST', now=datetime.now(UTC))
    snapshot = tmp_path / 'projects/new-test/revisions/001/workflow/standards.yaml'
    assert read_yaml(snapshot)['standards'] == []


def test_package_preserves_snapshot_and_rejects_edits(tmp_path):
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.workflows.gate_review import approve_gate
    from healthvideo.workflows.package import package_project
    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    for stage in range(1, 5):
        accept(tmp_path, ready(tmp_path, stage))
    snapshot = module().pin_standards(tmp_path, project)
    from healthvideo.tts.silent import SilentTTS
    from healthvideo.workflows.produce import produce_project
    from tests.workflows.test_package import _fake_renderer
    approve_gate(project, GateKind.MEDICAL, reviewer='Fixture reviewer', now=datetime.now(UTC))
    produce_project(project, SilentTTS(), _fake_renderer)
    approve_gate(project, GateKind.VIDEO, reviewer='Fixture reviewer', now=datetime.now(UTC))
    original = snapshot.read_bytes()
    snapshot.write_bytes(original + b'\nchanged: true\n')
    with pytest.raises(ValueError):
        package_project(project)
    snapshot.write_bytes(original)
    package = package_project(project)
    assert (package / 'workflow/standards.yaml').read_bytes() == original
    import json
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['payload_sha256']['workflow/standards.yaml'] == trials.digest(snapshot)
