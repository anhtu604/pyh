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
from tests.workflows.test_visual_review import submit


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


@pytest.fixture(autouse=True)
def fake_contact_sheet(monkeypatch):
    def prepare(root, *, final=False):
        from healthvideo.workflows.visual_review import CANDIDATES

        index = read_yaml(root / CANDIDATES)
        contact = root / 'reviews/visual/contact-sheet.jpg'
        Image.new('RGB', (32, 32)).save(contact)
        sheet = {'path': contact.relative_to(root).as_posix(), 'sha256': sha256_file(contact)}
        if final:
            write_yaml_atomic(root / 'reviews/visual/final-contact-sheets.yaml', {
                'render_sha256': sha256_file(root / 'renders/video.mp4'), 'sheets': [sheet],
            })
            return
        index['contact_sheet'] = sheet
        write_yaml_atomic(root / CANDIDATES, index)
    monkeypatch.setattr(produce, 'prepare_contact_sheet', prepare)


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
    submit(root)
    produce.produce_project(illustrated_project, SilentTTS(), renderer, music=music)
    final_sheets = read_yaml(root / 'reviews/visual/final-contact-sheets.yaml')
    assert final_sheets['render_sha256'] == sha256_file(root / 'renders/video.mp4')
    # Both generated provenance and staged PNG bytes must be verified on reuse.
    produce.produce_project(illustrated_project, SilentTTS(), lambda _: pytest.fail('cache missed'), music=music)
    from tests.helpers import submit_video_fixture

    submit_video_fixture(illustrated_project)
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
            assert len(calls) == 3, 'All three FLUX candidates must finish before TTS'
            return super().synthesize(request, out)

    produce.produce_project(illustrated_project, Voice(), renderer)
    produce.produce_project(illustrated_project, Voice(), lambda _: pytest.fail('render repeated'))
    assert calls == [('A park without lettering', 1080, 1920, seed) for seed in (42, 43, 44)]
    assert read_yaml(illustrated_project / 'project.yaml')['state'] == 'production_in_progress'
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
        'visual': 'whiteboard', "on_screen_text": "Synthetic illustration.", 'visual_assets': [
            {'path': 'assets/illustrations/./park.png', 'role': 'whiteboard'}],
    }]})
    manifest = AssetManifest.model_validate({'assets': [recipe]})
    rights = produce._prepare_illustrations(tmp_path, board, manifest, generate=True)
    assert len(rights) == 1
    assert Image.open(tmp_path / recipe['path']).getpixel((0, 0)) == (0, 128, 0)
    produce._prepare_illustrations(tmp_path, board, manifest, generate=True)
    assert calls == ['A park without lettering'] * 3
    recipe['prompt'] = 'A different park'
    changed = AssetManifest.model_validate({'assets': [recipe]})
    produce._prepare_illustrations(tmp_path, board, changed, generate=True)
    assert calls == ['A park without lettering'] * 3 + ['A different park'] * 3
    assert Image.open(tmp_path / recipe['path']).getpixel((0, 0)) == (0, 0, 255)


def test_produce_restores_locked_illustrations_and_fails_closed_before_flux(tmp_path, monkeypatch):
    """Produce recovers locked candidate/imported PNG before FLUX, or aborts 0s GPU without touching approvals."""
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    root = project / 'revisions/001'
    cand2 = root / 'reviews/visual/asset-00/round-0/candidate-2.png'
    cand2.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (1080, 1920), 'green').save(cand2)
    locked_sha = sha256_file(cand2)

    # Start medically approved with valid green image on disk, then simulate buggy overwrite before produce.
    wrong = root / 'assets/illustrations/park.png'
    wrong.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (1080, 1920), 'green').save(wrong)

    manifest_data = read_yaml(root / 'assets/asset-manifest.yaml')
    manifest_data['assets'].append({**illustration_record(), 'sha256': locked_sha})
    write_yaml_atomic(root / 'assets/asset-manifest.yaml', manifest_data)
    board = read_yaml(root / 'storyboard/storyboard.yaml')
    board['scenes'][0]['visual_assets'] = [{'path': 'assets/illustrations/park.png', 'role': 'whiteboard'}]
    write_yaml_atomic(root / 'storyboard/storyboard.yaml', board)
    approve_gate(project, GateKind.MEDICAL, reviewer='doctor', now=datetime(2026, 10, 23, tzinfo=UTC))
    Image.new('RGB', (1080, 1920), 'red').save(wrong)

    monkeypatch.setattr(
        produce,
        'generate_illustration',
        lambda *a, **k: pytest.fail('FLUX must not run for locked assets'),
        raising=False,
    )
    out = produce.produce_project(project, SilentTTS(), renderer, music=False)
    assert out.is_file()
    assert sha256_file(wrong) == locked_sha

    # Corrupt working copy AND remove candidate-2 under valid medical approval -> fails BEFORE FLUX/TTS.
    proj_meta = read_yaml(project / 'project.yaml')
    proj_meta['state'] = WorkflowState.MEDICALLY_APPROVED.value
    write_yaml_atomic(project / 'project.yaml', proj_meta)
    Image.new('RGB', (1080, 1920), 'red').save(wrong)
    cand2.unlink()
    approval_before = (root / 'reviews/medical-approval.yaml').read_bytes()
    manifest_before = (root / 'assets/asset-manifest.yaml').read_bytes()

    with pytest.raises(ValueError, match='Generated illustration sha256 mismatch: assets/illustrations/park.png'):
        produce.produce_project(project, SilentTTS(), renderer, music=False)
    assert (root / 'reviews/medical-approval.yaml').read_bytes() == approval_before
    assert (root / 'assets/asset-manifest.yaml').read_bytes() == manifest_before
