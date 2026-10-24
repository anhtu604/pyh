
import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from PIL import Image

from healthvideo.domain.asset_manifest import AssetManifest
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from tests.test_flux import illustration_record


def _board():
    return Storyboard.model_validate({'title': 'Gout', 'scenes': [{
        'id': 'S01', 'start_frame': 0, 'duration_frames': 90,
        'narration': 'Tinh thể urat trong khớp gây gout.', 'visual': 'whiteboard',
        'on_screen_text': 'Gout', 'visual_assets': [
            {'path': 'assets/illustrations/park.png', 'role': 'whiteboard'}],
    }]})


def _generate(prompt, *, out, width, height, seed):
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (width, height), (seed % 255, 1, 2)).save(out)
    return out


def submit(root, *, reject=False):
    from healthvideo.workflows.visual_review import CANDIDATES, REPORT

    index = read_yaml(root / CANDIDATES)
    contact = root / 'reviews/visual/contact-sheet.jpg'
    contact.parent.mkdir(parents=True, exist_ok=True)
    contact.write_bytes(b'synthetic contact sheet')
    index['contact_sheet'] = {
        'path': contact.relative_to(root).as_posix(), 'sha256': sha256_file(contact),
    }
    write_yaml_atomic(root / CANDIDATES, index)
    candidates = index['assets'][0]['candidates']
    write_yaml_atomic(root / REPORT, {
        'candidate_index_sha256': sha256_file(root / CANDIDATES),
        'inspected_images': [c['path'] for c in candidates] + [index['contact_sheet']['path']],
        'scenes': [{'scene': 'S01', 'decision': 'reject' if reject else 'select',
                    'selected': None if reject else candidates[1]['path'],
                    'reason': 'wrong subject' if reject else 'big toe matches narration',
                    'layout_issues': [], 'new_prompt': 'red swollen big toe, no text' if reject else None}],
    })


def test_visual_review_reject_regenerates_then_falls_back(tmp_path):
    from healthvideo.workflows.visual_review import (
        apply_visual_fallbacks,
        ensure_candidates,
        review_complete,
    )

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    board = _board()
    for round_number in range(3):
        index = ensure_candidates(tmp_path, board, manifest, generate=_generate)
        assert index['assets'][0]['round'] == round_number
        assert not review_complete(tmp_path)
        submit(tmp_path, reject=True)
    index = ensure_candidates(tmp_path, board, manifest, generate=_generate)
    assert index['assets'][0]['round'] == 2
    assert index['assets'][0]['fallback'] == 'joint_fluid_urate_to_inflammation'
    assert review_complete(tmp_path)
    derived = apply_visual_fallbacks(tmp_path, board)
    assert derived.scenes[0].anatomy.subject == 'joint_fluid_urate_to_inflammation'
    assert not derived.scenes[0].visual_assets
    assert board.scenes[0].visual == 'whiteboard'


def test_visual_review_binds_inspected_candidate_bytes_and_selection(tmp_path):
    from healthvideo.workflows.visual_review import ensure_candidates, review_complete

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    submit(tmp_path)
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    assert review_complete(tmp_path)
    index = read_yaml(tmp_path / 'reviews/visual/candidates.yaml')
    candidate = tmp_path / index['assets'][0]['selected']
    candidate.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='changed'):
        ensure_candidates(tmp_path, _board(), manifest, generate=_generate)


def test_visual_review_requires_all_images_and_contact_sheet(tmp_path):
    from healthvideo.workflows.visual_review import REPORT, ensure_candidates

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    submit(tmp_path)
    report = read_yaml(tmp_path / REPORT)
    report['inspected_images'] = []
    write_yaml_atomic(tmp_path / REPORT, report)
    with pytest.raises(ValueError, match='inspect'):
        ensure_candidates(tmp_path, _board(), manifest, generate=_generate)


def test_visual_review_selection_cannot_change_after_consumption(tmp_path):
    from healthvideo.workflows.visual_review import (
        CANDIDATES,
        ensure_candidates,
        review_complete,
    )

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    submit(tmp_path)
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    index = read_yaml(tmp_path / CANDIDATES)
    index['assets'][0]['selected'] = index['assets'][0]['candidates'][0]['path']
    write_yaml_atomic(tmp_path / CANDIDATES, index)
    with pytest.raises(ValueError, match='selection changed'):
        review_complete(tmp_path)


def test_reapproved_narration_invalidates_visual_review(tmp_path):
    from healthvideo.workflows.visual_review import (
        REPORT,
        ensure_candidates,
        review_complete,
    )

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    board = _board()
    ensure_candidates(tmp_path, board, manifest, generate=_generate)
    submit(tmp_path)
    ensure_candidates(tmp_path, board, manifest, generate=_generate)
    changed = board.model_copy(update={'scenes': (board.scenes[0].model_copy(update={
        'narration': 'Gout cần giải thích lại bằng ngữ cảnh đã duyệt mới.',
    }),)})
    ensure_candidates(tmp_path, changed, manifest, generate=_generate)
    assert not review_complete(tmp_path)
    assert not (tmp_path / REPORT).exists()
    assert list((tmp_path / 'reviews/visual').glob('stale-review-*.yaml'))


def test_contact_sheets_sample_each_scene_and_beat_and_bind_final_render(tmp_path):
    from healthvideo.workflows.visual_review import CANDIDATES, prepare_contact_sheet

    (tmp_path / 'renders').mkdir()
    (tmp_path / 'renders/video.mp4').write_bytes(b'final selected candidate render')
    (tmp_path / 'renders/render-manifest.json').write_text('{}')
    (tmp_path / 'renders/render-input.json').write_text(json.dumps({'fps': 30, 'scenes': [
        {'start_frame': 0, 'duration_frames': 30, 'beats': []},
        {'start_frame': 30, 'duration_frames': 17000, 'beats': [{'start_frame': 90}]},
    ]}))
    write_yaml_atomic(tmp_path / CANDIDATES, {'assets': []})
    index_bytes = (tmp_path / CANDIDATES).read_bytes()

    def ffmpeg(argv, **kwargs):
        assert 'eq(n\\,15)' in argv[argv.index('-vf') + 1]
        assert 'eq(n\\,129)' in argv[argv.index('-vf') + 1]
        assert 'eq(n\\,8530)' in argv[argv.index('-vf') + 1]
        Path(argv[-1].replace('%03d', '001')).write_bytes(b'contact sheet')
        return CompletedProcess(argv, 0, '', '')

    prepare_contact_sheet(tmp_path, runner=ffmpeg, final=True)
    final = read_yaml(tmp_path / 'reviews/visual/final-contact-sheets.yaml')
    assert final['render_sha256'] == sha256_file(tmp_path / 'renders/video.mp4')
    assert final['render_manifest_sha256'] == sha256_file(tmp_path / 'renders/render-manifest.json')
    assert (tmp_path / CANDIDATES).read_bytes() == index_bytes
