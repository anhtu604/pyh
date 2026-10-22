from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from healthvideo.domain.asset_manifest import AssetManifest
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows import produce
from healthvideo.workflows.gate_review import (
    approve_gate,
    hash_reviewed_artifacts,
    medical_reviewed_paths,
)
from tests.helpers import create_v2_project_fixture
from tests.test_flux import illustration_record


@pytest.fixture
def illustrated_project(tmp_path):
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    root = project / 'revisions/001'
    manifest = read_yaml(root / 'assets/asset-manifest.yaml')
    manifest['assets'].append(illustration_record())
    write_yaml_atomic(root / 'assets/asset-manifest.yaml', manifest)
    board = read_yaml(root / 'storyboard/storyboard.yaml')
    board['scenes'][0]['visual_assets'] = [{'path': 'assets/illustrations/park.png', 'role': 'whiteboard'}]
    write_yaml_atomic(root / 'storyboard/storyboard.yaml', board)
    approve_gate(project, GateKind.MEDICAL, reviewer='doctor', now=datetime(2026, 10, 23, tzinfo=UTC))
    return project


def renderer(argv):
    Path(argv[argv.index('--output') + 1]).write_bytes(b'video')
    return 0


@pytest.mark.parametrize('music', [True, False])
def test_illustration_license_recorded(illustrated_project, music, monkeypatch):
    def generate(prompt, *, out, width, height, seed):
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (width, height), 'green').save(out)
        return out

    monkeypatch.setattr(produce, 'generate_illustration', generate, raising=False)
    root = illustrated_project / 'revisions/001'
    before = hash_reviewed_artifacts(medical_reviewed_paths(root))
    produce.produce_project(illustrated_project, SilentTTS(), renderer, music=music)
    entries = read_yaml(root / 'renders/license-ledger.yaml')['entries']
    illustration = next(entry for entry in entries if entry['source'] == 'generated:flux2-klein-4b')
    assert illustration['license'] == 'Apache-2.0'
    assert illustration['sha256'] == sha256_file(root / illustration['path'])
    assert illustration['sha256'] == sha256_file(root / 'renders' / illustration['path'])
    assert len(entries) == (2 if music else 1)
    assert before == hash_reviewed_artifacts(medical_reviewed_paths(root))
    # Both generated provenance and staged PNG bytes must be verified on reuse.
    produce.produce_project(illustrated_project, SilentTTS(), lambda _: pytest.fail('cache missed'), music=music)
    (root / 'renders/license-ledger.yaml').write_text('tampered')
    with pytest.raises(ValueError, match='medically_approved'):
        produce.produce_project(illustrated_project, SilentTTS(), renderer, music=music)


def test_produce_generates_missing_illustration_once(illustrated_project, monkeypatch):
    calls = []

    def generate(prompt, *, out, width, height, seed):
        calls.append((prompt, width, height, seed))
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (width, height), 'green').save(out)
        return out

    monkeypatch.setattr(produce, 'generate_illustration', generate, raising=False)
    class Voice(SilentTTS):
        def synthesize(self, request, out):
            assert len(calls) == 1, 'FLUX must finish before TTS'
            return super().synthesize(request, out)

    produce.produce_project(illustrated_project, Voice(), renderer)
    produce.produce_project(illustrated_project, Voice(), lambda _: pytest.fail('render repeated'))
    assert calls == [('A park without lettering', 1080, 1920, 42)]
    assert Image.open(illustrated_project / 'revisions/001/assets/illustrations/park.png').size == (1080, 1920)


def test_illustration_dry_run_does_not_generate(illustrated_project, monkeypatch):
    monkeypatch.setattr(produce, 'generate_illustration', lambda *a, **k: pytest.fail('dry run used GPU'), raising=False)
    produce.produce_project(illustrated_project, SilentTTS(), renderer, dry_run=True)
    assert not (illustrated_project / 'revisions/001/assets/illustrations/park.png').exists()


def test_illustration_failure_keeps_medical_approval(illustrated_project, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('FLUX generation failed: CUDA out of memory')

    monkeypatch.setattr(produce, 'generate_illustration', fail, raising=False)
    with pytest.raises(RuntimeError, match='FLUX.*CUDA out of memory'):
        produce.produce_project(illustrated_project, SilentTTS(), renderer)
    assert read_yaml(illustrated_project / 'project.yaml')['state'] == 'medically_approved'
    assert not (illustrated_project / 'revisions/001/renders/video.mp4').exists()


def test_illustration_recipe_and_normalized_reference_control_reuse(tmp_path, monkeypatch):
    calls = []

    def generate(prompt, *, out, width, height, seed):
        calls.append(prompt)
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (width, height), 'green' if len(calls) == 1 else 'blue').save(out)
        return out

    monkeypatch.setattr(produce, 'generate_illustration', generate)
    recipe = illustration_record()
    board = Storyboard.model_validate({'title': 'Park', 'scenes': [{
        'id': 'S01', 'start_frame': 0, 'duration_frames': 90, 'narration': 'Park',
        'visual': 'whiteboard', 'visual_assets': [
            {'path': 'assets/illustrations/./park.png', 'role': 'whiteboard'}],
    }]})
    manifest = AssetManifest.model_validate({'assets': [recipe]})
    rights = produce._prepare_illustrations(tmp_path, board, manifest, generate=True)
    assert len(rights) == 1
    assert Image.open(tmp_path / recipe['path']).getpixel((0, 0)) == (0, 128, 0)
    produce._prepare_illustrations(tmp_path, board, manifest, generate=True)
    assert calls == ['A park without lettering']
    recipe['prompt'] = 'A different park'
    changed = AssetManifest.model_validate({'assets': [recipe]})
    produce._prepare_illustrations(tmp_path, board, changed, generate=True)
    assert calls == ['A park without lettering', 'A different park']
    assert Image.open(tmp_path / recipe['path']).getpixel((0, 0)) == (0, 0, 255)
