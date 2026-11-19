import hashlib
import importlib
import json
from datetime import UTC, datetime

import pytest

from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import standards
from tests.helpers import create_v2_project_fixture


def module():
    return importlib.import_module('healthvideo.workflows.factory_standards')


def _standard_entry(stage: int, version: int = 1, text: str = 'Clear TEST standard') -> dict:
    return {
        'id': f'std-{stage}-v{version}',
        'stage': stage,
        'version': version,
        'text': text,
        'reviewer': 'Fixture reviewer',
        'accepted_at': '2026-10-30T00:00:00+00:00',
        'scope': 'channel',
    }


def _seed_standards(root, entries: list[dict]) -> None:
    write_yaml_atomic(
        root / module().STANDARDS_FILE,
        {
            'version': 1,
            'entries': entries,
            'feedback_scope': 'Only chung and matching project slug; history preserved.',
        },
    )


def test_snapshot_immutable_and_new_version_does_not_rewrite(tmp_path):
    project = create_v2_project_fixture(tmp_path / 'projects')
    entries = [_standard_entry(stage) for stage in range(1, 5)]
    _seed_standards(tmp_path, entries)
    hash_v1 = module().standards_hash(tmp_path)
    path = module().pin_standards(tmp_path, project)
    before = path.read_bytes()
    _seed_standards(tmp_path, [*entries, _standard_entry(1, version=2, text='Improved standard')])
    assert module().accepted_standards(tmp_path)[1]['version'] == 2
    assert module().standards_hash(tmp_path) != hash_v1
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
    _seed_standards(tmp_path, [_standard_entry(stage) for stage in range(1, 5)])
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
    _seed_standards(tmp_path, [_standard_entry(stage) for stage in range(1, 5)])
    project = create_project_v2(tmp_path / 'projects', 'new-test', 'TEST', now=datetime.now(UTC))
    assert (project / 'revisions/001/workflow/standards.yaml').is_file()


def test_new_project_pins_only_the_standards_that_exist(tmp_path):
    from healthvideo.workflows.create_project_v2 import create_project_v2
    create_project_v2(tmp_path / 'projects', 'new-test', 'TEST', now=datetime.now(UTC))
    snapshot = tmp_path / 'projects/new-test/revisions/001/workflow/standards.yaml'
    assert read_yaml(snapshot)['standards'] == []


def test_package_preserves_snapshot_and_rejects_edits(tmp_path):
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.tts.silent import SilentTTS
    from healthvideo.workflows.gate_review import approve_gate
    from healthvideo.workflows.package import package_project
    from healthvideo.workflows.produce import produce_project
    from tests.helpers import submit_video_fixture
    from tests.workflows.test_package import _fake_renderer
    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    _seed_standards(tmp_path, [_standard_entry(stage) for stage in range(1, 5)])
    snapshot = module().pin_standards(tmp_path, project)
    approve_gate(project, GateKind.MEDICAL, reviewer='Fixture reviewer', now=datetime.now(UTC))
    produce_project(project, SilentTTS(), _fake_renderer)
    submit_video_fixture(project)
    approve_gate(project, GateKind.VIDEO, reviewer='Fixture reviewer', now=datetime.now(UTC))
    original = snapshot.read_bytes()
    snapshot.write_bytes(original + b'\nchanged: true\n')
    with pytest.raises(ValueError):
        package_project(project)
    snapshot.write_bytes(original)
    package = package_project(project)
    assert (package / 'workflow/standards.yaml').read_bytes() == original
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['payload_sha256']['workflow/standards.yaml'] == hashlib.sha256(snapshot.read_bytes()).hexdigest()


def test_pin_standards_pins_style_a_spec_and_sha256_immutably(tmp_path):
    from healthvideo.workflows.create_project_v2 import create_project_v2

    spec_file = tmp_path / module().STYLE_SPEC_FILE
    spec_file.parent.mkdir(parents=True, exist_ok=True)
    spec_file.write_text('# Style A spec v1\n', encoding='utf-8')
    expected_sha = hashlib.sha256(spec_file.read_bytes()).hexdigest()

    hash_v1 = module().standards_hash(tmp_path)
    project = create_project_v2(tmp_path / 'projects', 'style-a-test', 'TEST', now=datetime.now(UTC))
    revision = project / 'revisions/001'
    snapshot = revision / 'workflow/standards.yaml'
    assert snapshot.is_file()
    data = read_yaml(snapshot)
    assert data['style_spec'] == {
        'path': module().STYLE_SPEC_FILE.as_posix(),
        'sha256': expected_sha,
    }
    assert module().pinned_style_spec(revision) == data['style_spec']
    assert module().style_a_active(revision) is True

    # Editing the spec later changes standards_hash(root) but does not rewrite pinned snapshot.
    spec_file.write_text('# Style A spec v2\n', encoding='utf-8')
    assert module().standards_hash(tmp_path) != hash_v1
    assert module().pin_standards(tmp_path, project).read_bytes() == snapshot.read_bytes()
    assert module().pinned_style_spec(revision)['sha256'] == expected_sha
    block = standards.prompt_block(tmp_path, slug=project.name)
    assert module().STYLE_SPEC_FILE.as_posix() in block
    assert expected_sha in block


def test_legacy_standards_snapshot_without_style_spec_remains_readable(tmp_path):
    project = create_v2_project_fixture(tmp_path / 'projects')
    revision = project / 'revisions/001'
    snapshot = revision / 'workflow/standards.yaml'
    write_yaml_atomic(snapshot, {'version': 1, 'standards': [_standard_entry(1)]})
    assert module().pinned_style_spec(revision) is None
    assert module().style_a_active(revision) is False
    block = standards.prompt_block(tmp_path, slug=project.name)
    assert 'Clear TEST standard' in block
