import json
import shutil
import subprocess
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from PIL import Image

from healthvideo.domain.asset_manifest import AssetManifest
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from tests.test_flux import illustration_record


def test_contact_sheet_deadline_reports_partial_diagnostic(tmp_path):
    from healthvideo.workflows.visual_review import CANDIDATES, prepare_contact_sheet

    (tmp_path / 'renders').mkdir()
    (tmp_path / 'renders/render-input.json').write_text(json.dumps({'fps': 30, 'scenes': []}))
    (tmp_path / 'reviews/visual').mkdir(parents=True)
    write_yaml_atomic(tmp_path / CANDIDATES, {'assets': []})

    def hang(argv, **kwargs):
        assert kwargs['timeout'] > 0
        raise subprocess.TimeoutExpired(argv, kwargs['timeout'], stderr=b'partial FFmpeg')

    with pytest.raises(RuntimeError, match='contact sheet.*timed out.*partial FFmpeg'):
        prepare_contact_sheet(tmp_path, runner=hang)


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
    assert not review_complete(tmp_path)


@pytest.mark.parametrize('change', ['omit', 'reopen', 'safety'])
def test_followup_visual_review_preserves_accepted_scene(tmp_path, change):
    from healthvideo.workflows.visual_review import (
        CANDIDATES,
        REPORT,
        ensure_candidates,
    )

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    submit(tmp_path)
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    selected = read_yaml(tmp_path / CANDIDATES)['assets'][0]['selected']
    submit(tmp_path)
    report = read_yaml(tmp_path / REPORT)
    if change == 'omit':
        report['scenes'] = []
    elif change == 'reopen':
        report['scenes'][0].update(decision='reject', selected=None, new_prompt='different')
    else:
        report['scenes'][0]['blocking_safety'] = True
    write_yaml_atomic(tmp_path / REPORT, report)
    if change == 'safety':
        with pytest.raises(ValueError, match='blocking_safety'):
            ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    else:
        ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
        assert read_yaml(tmp_path / CANDIDATES)['assets'][0]['selected'] == selected
        if change == 'reopen':
            saved = read_yaml(tmp_path / REPORT)
            assert saved['scenes'][0]['selected'] == selected
            assert saved['dropped_issues'][0]['issue']['decision'] == 'reject'
            assert saved['dropped_issues'][0]['reason']


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


@pytest.mark.skipif(shutil.which('ffmpeg') is None, reason='needs ffmpeg')
def test_contact_sheet_survives_more_than_100_sampled_frames(tmp_path):
    """Regression 2026-11-13: gout's beats produced >100 select terms and FFmpeg refused them."""
    import subprocess

    from healthvideo.workflows.visual_review import CANDIDATES, prepare_contact_sheet

    (tmp_path / 'renders').mkdir()
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                    '-i', 'testsrc=size=160x90:rate=30', '-t', '20', str(tmp_path / 'renders/video.mp4')],
                   check=True)
    beats = [{'start_frame': frame} for frame in range(0, 560, 4)]
    (tmp_path / 'renders/render-input.json').write_text(json.dumps({'fps': 30, 'scenes': [
        {'start_frame': 0, 'duration_frames': 600, 'beats': beats}]}))
    write_yaml_atomic(tmp_path / CANDIDATES, {'assets': []})

    prepare_contact_sheet(tmp_path)

    assert len(list((tmp_path / 'reviews/visual').glob('contact-sheet-*.jpg'))) == 6


def test_visual_review_accepts_valid_style_codes_and_mascot_pose(tmp_path):
    from healthvideo.workflows.visual_review import (
        REPORT,
        STYLE_ERROR_CODES,
        ensure_candidates,
        review_complete,
        validate_style_issues,
    )

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    submit(tmp_path)
    report = read_yaml(tmp_path / REPORT)
    report['scenes'][0].update(
        mascot_pose='explain',
        style_issues=[
            'style_palette: có màu đỏ báo động',
            {'code': 'style_stroke', 'detail': 'có bóng đổ 3D'},
        ],
        layout_issues=['style_caption: phụ đề chạm nhãn'],
    )
    write_yaml_atomic(tmp_path / REPORT, report)
    assert validate_style_issues(report['scenes'][0]) == [
        'style_palette', 'style_stroke', 'style_caption',
    ]
    assert {'style_palette', 'style_typography', 'style_mascot_pose', 'style_stroke',
            'style_medical_art', 'style_caption', 'style_zoom', 'style_hands', 'style_rights'} <= set(STYLE_ERROR_CODES)
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    assert review_complete(tmp_path)


def test_visual_review_accepts_style_hands_on_reject(tmp_path):
    from healthvideo.workflows.visual_review import (
        REPORT,
        STYLE_ERROR_CODES,
        ensure_candidates,
        review_complete,
        validate_style_issues,
    )

    assert 'style_hands' in STYLE_ERROR_CODES
    assert STYLE_ERROR_CODES['style_hands']
    assert validate_style_issues({
        'decision': 'reject',
        'style_issues': [
            'style_hands: bàn tay 6 ngón',
            {'code': 'style_hands', 'detail': 'ngón dính vào tờ giấy'},
        ],
    }) == ['style_hands']

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    board = _board()
    ensure_candidates(tmp_path, board, manifest, generate=_generate)
    submit(tmp_path, reject=True)
    report = read_yaml(tmp_path / REPORT)
    report['scenes'][0].update(
        style_issues=['style_hands: cả ba ứng viên đều có 6 ngón dính tờ giấy'],
        new_prompt='Lab report resting flat on wooden desk, no hands in frame, no text',
    )
    write_yaml_atomic(tmp_path / REPORT, report)
    index = ensure_candidates(tmp_path, board, manifest, generate=_generate)
    assert index['assets'][0]['round'] == 1
    assert index['assets'][0]['prompt'] == (
        'Lab report resting flat on wooden desk, no hands in frame, no text'
    )
    assert not review_complete(tmp_path)


@pytest.mark.parametrize('patch', [
    {'style_issues': ['style_hands: bàn tay 4 ngón']},
    {'style_issues': [{'code': 'style_hands', 'detail': 'ngón quá dài, dính nhau'}]},
    {'layout_issues': ['style_hands: cổ tay không liền mạch']},
])
def test_visual_review_rejects_select_with_style_hands(tmp_path, patch):
    from healthvideo.workflows.visual_review import (
        REPORT,
        ensure_candidates,
        review_complete,
    )

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    board = _board()
    ensure_candidates(tmp_path, board, manifest, generate=_generate)
    submit(tmp_path)
    report = read_yaml(tmp_path / REPORT)
    report['scenes'][0].update(patch)
    write_yaml_atomic(tmp_path / REPORT, report)
    with pytest.raises(ValueError, match='style_hands'):
        ensure_candidates(tmp_path, board, manifest, generate=_generate)
    assert not review_complete(tmp_path)


def test_visual_review_prompt_requires_hand_anatomy_check():
    repo_root = Path(__file__).resolve().parents[2]
    vr_prompt = (repo_root / 'src/healthvideo/prompts/visual_review.md').read_text(encoding='utf-8')
    sb_prompt = (repo_root / 'src/healthvideo/prompts/storyboard_design.md').read_text(encoding='utf-8')
    for token in ('style_hands', '5 ngón', 'ngón cái', 'cổ tay', 'reject', 'new_prompt'):
        assert token in vr_prompt
    assert 'hands partially out of frame / hidden' in sb_prompt


def test_visual_review_accepts_style_rights_on_reject(tmp_path):
    from healthvideo.workflows.visual_review import (
        REPORT,
        STYLE_ERROR_CODES,
        ensure_candidates,
        review_complete,
        validate_style_issues,
    )

    assert 'style_rights' in STYLE_ERROR_CODES
    assert STYLE_ERROR_CODES['style_rights']
    assert validate_style_issues({
        'decision': 'reject',
        'style_issues': [
            'style_rights: chai thuốc có logo và nhãn thương hiệu',
            {'code': 'style_rights', 'detail': 'khuôn mặt người thật dễ nhận ra'},
        ],
    }) == ['style_rights']

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    board = _board()
    ensure_candidates(tmp_path, board, manifest, generate=_generate)
    submit(tmp_path, reject=True)
    report = read_yaml(tmp_path / REPORT)
    report['scenes'][0].update(
        style_issues=['style_rights: lọ thuốc in nhãn thương hiệu rõ nét'],
        new_prompt='Plain medicine bottle with blank unbranded label on wooden desk, no text',
    )
    write_yaml_atomic(tmp_path / REPORT, report)
    index = ensure_candidates(tmp_path, board, manifest, generate=_generate)
    assert index['assets'][0]['round'] == 1
    assert index['assets'][0]['prompt'] == (
        'Plain medicine bottle with blank unbranded label on wooden desk, no text'
    )
    assert not review_complete(tmp_path)


@pytest.mark.parametrize('patch', [
    {'style_issues': ['style_rights: có logo thương hiệu trên hộp thuốc']},
    {'style_issues': [{'code': 'style_rights', 'detail': 'nhân vật hoạt hình có bản quyền'}]},
    {'layout_issues': ['style_rights: khuôn mặt người thật dễ nhận ra']},
])
def test_visual_review_rejects_select_with_style_rights(tmp_path, patch):
    from healthvideo.workflows.visual_review import (
        REPORT,
        ensure_candidates,
        review_complete,
    )

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    board = _board()
    ensure_candidates(tmp_path, board, manifest, generate=_generate)
    submit(tmp_path)
    report = read_yaml(tmp_path / REPORT)
    report['scenes'][0].update(patch)
    write_yaml_atomic(tmp_path / REPORT, report)
    with pytest.raises(ValueError, match='style_rights'):
        ensure_candidates(tmp_path, board, manifest, generate=_generate)
    assert not review_complete(tmp_path)


def test_visual_review_prompt_requires_rights_and_brand_check():
    repo_root = Path(__file__).resolve().parents[2]
    vr_prompt = (repo_root / 'src/healthvideo/prompts/visual_review.md').read_text(encoding='utf-8')
    for token in (
        'style_rights',
        'logo',
        'nhãn hiệu',
        'thương hiệu',
        'khuôn mặt người thật',
        'bản quyền',
        'reject',
        'new_prompt',
    ):
        assert token in vr_prompt


def test_image_prompting_guide_follows_style_a_and_affirmative_flux_rules():
    repo_root = Path(__file__).resolve().parents[2]
    guide = (repo_root / 'docs/reference/image-prompting.md').read_text(encoding='utf-8')
    lowered = guide.lower()
    for forbidden in ('directional shading', 'cel-shading', 'warm cream', 'two-tone shading'):
        assert forbidden not in lowered
    assert '#F7F4EC' in guide
    assert '#12304A' in guide


@pytest.mark.parametrize(('patch', 'match'), [
    ({'style_issues': ['style_unknown_code']}, 'Unknown style error code'),
    ({'style_issues': [{'code': 'not_a_style_code'}]}, 'Unknown style error code'),
    ({'layout_issues': ['style_bogus: sai']}, 'Unknown style error code'),
    ({'mascot_pose': 'dancing_wildly'}, 'Unknown mascot_pose'),
])
def test_visual_review_rejects_invalid_style_code_or_pose(tmp_path, patch, match):
    from healthvideo.workflows.visual_review import REPORT, ensure_candidates

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    submit(tmp_path)
    report = read_yaml(tmp_path / REPORT)
    report['scenes'][0].update(patch)
    write_yaml_atomic(tmp_path / REPORT, report)
    with pytest.raises(ValueError, match=match):
        ensure_candidates(tmp_path, _board(), manifest, generate=_generate)


def test_ensure_candidates_restores_locked_across_renumbering_and_narrow_hash(tmp_path):
    """Reproduce thay-men-gan regression: slot shift preserves locked candidates & narrows recipes hash."""
    import hashlib

    from healthvideo.workflows.visual_review import (
        CANDIDATES,
        ensure_candidates,
        prepare_contact_sheet,
        review_complete,
    )

    def solid_png(path: Path, color: str) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (1080, 1920), color).save(path)
        return sha256_file(path)

    # Prior layout: asset-00 = lab-slip (selected candidate-2), asset-01 = product-choice (removed),
    # asset-02 = prescription-review (round-1 candidate-3 locked!).
    lab_cand2 = tmp_path / 'reviews/visual/asset-00/round-0/candidate-2.png'
    lab_cand1 = tmp_path / 'reviews/visual/asset-00/round-0/candidate-1.png'
    lab_sha = solid_png(lab_cand2, 'green')
    solid_png(lab_cand1, 'red')

    pr_cand3 = tmp_path / 'reviews/visual/asset-02/round-1/candidate-3.png'
    pr_cand1 = tmp_path / 'reviews/visual/asset-02/round-1/candidate-1.png'
    pr_sha = solid_png(pr_cand3, 'blue')
    solid_png(pr_cand1, 'yellow')

    # Corrupt working copies on disk (as observed on thay-men-gan 2026-11-19 15:50:58).
    solid_png(tmp_path / 'assets/illustrations/lab-slip.png', 'red')
    solid_png(tmp_path / 'assets/illustrations/prescription-review.png', 'yellow')

    board = Storyboard.model_validate({
        'title': 'Men gan',
        'scenes': [
            {
                'id': 'S01', 'start_frame': 0, 'duration_frames': 90,
                'narration': 'Xét nghiệm', 'visual': 'whiteboard', 'on_screen_text': 'Lab slip',
                'visual_assets': [{'path': 'assets/illustrations/lab-slip.png', 'role': 'whiteboard'}],
            },
            {
                'id': 'S02', 'start_frame': 90, 'duration_frames': 90,
                'narration': 'Không dùng minh họa', 'visual': 'whiteboard', 'on_screen_text': 'Text only',
            },
            {
                'id': 'S03', 'start_frame': 180, 'duration_frames': 90,
                'narration': 'Đơn thuốc', 'visual': 'whiteboard', 'on_screen_text': 'Rx',
                'visual_assets': [{'path': 'assets/illustrations/prescription-review.png', 'role': 'whiteboard'}],
            },
            {
                'id': 'S04', 'start_frame': 270, 'duration_frames': 90,
                'narration': 'Đi khám', 'visual': 'whiteboard', 'on_screen_text': 'Clinic',
                'visual_assets': [{'path': 'assets/illustrations/clinic-preparation.png', 'role': 'whiteboard'}],
            },
        ],
    })
    manifest = AssetManifest.model_validate({
        'assets': [
            {**illustration_record(), 'path': 'assets/illustrations/lab-slip.png', 'sha256': lab_sha, 'seed': 10},
            {
                **illustration_record(),
                'path': 'assets/illustrations/prescription-review.png',
                'sha256': pr_sha,
                'seed': 20,
            },
            {
                **illustration_record(),
                'path': 'assets/illustrations/clinic-preparation.png',
                'prompt': 'Clinic desk',
                'seed': 30,
            },
        ],
    })
    write_yaml_atomic(tmp_path / CANDIDATES, {
        'recipes_sha256': 'older-revision-hash',
        'review_count': 2,
        'assets': [
            {
                'path': 'assets/illustrations/lab-slip.png',
                'candidates': [
                    {'path': 'reviews/visual/asset-00/round-0/candidate-1.png', 'sha256': sha256_file(lab_cand1), 'seed': 10},
                    {'path': 'reviews/visual/asset-00/round-0/candidate-2.png', 'sha256': lab_sha, 'seed': 11},
                ],
                'selected': 'reviews/visual/asset-00/round-0/candidate-2.png',
            },
            {
                'path': 'assets/illustrations/prescription-review.png',
                'candidates': [
                    {'path': 'reviews/visual/asset-02/round-1/candidate-1.png', 'sha256': sha256_file(pr_cand1), 'seed': 23},
                    {'path': 'reviews/visual/asset-02/round-1/candidate-3.png', 'sha256': pr_sha, 'seed': 25},
                ],
                'selected': 'reviews/visual/asset-02/round-1/candidate-3.png',
            },
        ],
    })

    flux_calls = []

    def gen(prompt, *, out, width, height, seed):
        flux_calls.append((prompt, seed))
        solid_png(out, 'purple')
        return out

    data = ensure_candidates(tmp_path, board, manifest, generate=gen)
    # Only the new unlocked clinic-preparation triggers FLUX (3 candidates), never locked assets!
    assert [p for p, _ in flux_calls] == ['Clinic desk'] * 3
    assert sha256_file(tmp_path / 'assets/illustrations/lab-slip.png') == lab_sha
    assert sha256_file(tmp_path / 'assets/illustrations/prescription-review.png') == pr_sha
    assert sha256_file(pr_cand3) == pr_sha
    assert hashlib.sha256(pr_cand3.read_bytes()).hexdigest() == pr_sha
    assert data['assets'][0]['selected'] == 'reviews/visual/asset-00/round-0/candidate-2.png'
    assert data['assets'][1]['selected'] == 'reviews/visual/asset-02/round-1/candidate-3.png'
    assert data['assets'][2]['selected'] is None
    assert not review_complete(tmp_path)

    # Approve clinic-preparation once; later changing non-illustrated S02 keeps recipes_sha256 intact.
    from healthvideo.workflows.visual_review import REPORT

    contact = tmp_path / 'reviews/visual/contact-sheet.jpg'
    contact.write_bytes(b'synthetic contact sheet')
    data['contact_sheet'] = {'path': 'reviews/visual/contact-sheet.jpg', 'sha256': sha256_file(contact)}
    write_yaml_atomic(tmp_path / CANDIDATES, data)
    clinic_cands = data['assets'][2]['candidates']
    write_yaml_atomic(tmp_path / REPORT, {
        'candidate_index_sha256': sha256_file(tmp_path / CANDIDATES),
        'inspected_images': [c['path'] for c in clinic_cands] + ['reviews/visual/contact-sheet.jpg'],
        'scenes': [{
            'scene': 'S04',
            'decision': 'select',
            'selected': clinic_cands[0]['path'],
            'reason': 'clinic preparation scene clear',
            'layout_issues': [],
            'new_prompt': None,
        }],
    })
    ensure_candidates(tmp_path, board, manifest, generate=lambda *a, **k: pytest.fail('unexpected regen'))
    assert review_complete(tmp_path)

    changed_s02 = board.model_copy(update={'scenes': (
        board.scenes[0],
        board.scenes[1].model_copy(update={'narration': 'Chỉnh lời cảnh không minh họa', 'duration_frames': 120}),
        board.scenes[2],
        board.scenes[3],
    )})
    ensure_candidates(tmp_path, changed_s02, manifest, generate=lambda *a, **k: pytest.fail('S02 drift regen'))
    assert review_complete(tmp_path)

    # Also verify prepare_contact_sheet filters stay batched <= 50 frames per FFmpeg invocation.
    sheet_batches: list[int] = []

    def fake_ffmpeg(argv, **kwargs):
        del kwargs
        import re

        vf_expr = argv[argv.index('-vf') + 1]
        sheet_batches.append(len(re.findall(r'eq\(n\\,\d+\)', vf_expr)))
        expected_count = int(argv[argv.index('-frames:v') + 1])
        for idx in range(expected_count):
            Image.new('RGB', (160, 90), 'white').save(argv[-1] % (idx + 1))
        return CompletedProcess(argv, 0, '', '')

    (tmp_path / 'renders').mkdir(exist_ok=True)
    (tmp_path / 'renders/video.mp4').write_bytes(b'fake-mp4')
    (tmp_path / 'renders/render-input.json').write_text(json.dumps({
        'fps': 30,
        'scenes': [{'start_frame': 0, 'duration_frames': 600, 'beats': [{'start_frame': f} for f in range(0, 560, 4)]}],
    }))
    prepare_contact_sheet(tmp_path, runner=fake_ffmpeg)
    assert sheet_batches == [50, 50, 42]
    assert all(1 <= count <= 50 for count in sheet_batches)


def test_restore_locked_illustrations_from_imported_and_fail_closed(tmp_path):
    """Locked asset restores from assets/imported; fails closed on missing match without outside symlink."""
    from healthvideo.workflows.visual_review import (
        ensure_candidates,
        restore_locked_illustrations,
    )

    imported = tmp_path / 'assets/imported/approved-diagram.png'
    imported.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (1080, 1920), 'teal').save(imported)
    imported_sha = sha256_file(imported)

    board = _board()
    manifest = AssetManifest.model_validate({
        'assets': [{**illustration_record(), 'sha256': imported_sha}],
    })
    resolved = restore_locked_illustrations(tmp_path, board, manifest)
    assert resolved['assets/illustrations/park.png'] == imported
    assert sha256_file(tmp_path / 'assets/illustrations/park.png') == imported_sha

    # Unmatched locked hash raises immediately without invoking FLUX.
    missing_manifest = AssetManifest.model_validate({
        'assets': [{**illustration_record(), 'sha256': 'f' * 64}],
    })
    with pytest.raises(ValueError, match='Generated illustration sha256 mismatch: assets/illustrations/park.png'):
        ensure_candidates(
            tmp_path,
            board,
            missing_manifest,
            generate=lambda *a, **k: pytest.fail('FLUX must not run when locked hash is unrecoverable'),
        )


@pytest.mark.parametrize('locked', [False, True])
def test_stale_selection_requires_bounded_fresh_review(tmp_path, locked):
    from healthvideo.workflows.visual_review import (
        CANDIDATES,
        REPORT,
        ensure_candidates,
        review_complete,
    )

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    board = _board()
    ensure_candidates(tmp_path, board, manifest, generate=_generate)
    submit(tmp_path)
    ensure_candidates(tmp_path, board, manifest, generate=_generate)
    index = read_yaml(tmp_path / CANDIDATES)
    selected = index['assets'][0]['selected']
    image_hash = sha256_file(tmp_path / index['assets'][0]['path'])
    if locked:
        index['assets'][0]['locked'] = True
        write_yaml_atomic(tmp_path / CANDIDATES, index)
        manifest = AssetManifest.model_validate({'assets': [{**illustration_record(), 'sha256': image_hash}]})
        # Keep the same recipes so this tests stale reports, rather than a recipe rebuild.
        from healthvideo.workflows.visual_review import _illustrated_recipes_hash
        index['recipes_sha256'] = _illustrated_recipes_hash(board, list(manifest.assets), 1080, 1920)
        write_yaml_atomic(tmp_path / CANDIDATES, index)

    for attempt in range(3):
        report = read_yaml(tmp_path / REPORT) if (tmp_path / REPORT).exists() else {
            'candidate_index_sha256': sha256_file(tmp_path / CANDIDATES),
            'inspected_images': [c['path'] for c in index['assets'][0]['candidates']] +
                                [index['contact_sheet']['path']],
            'scenes': [{'scene': 'S01', 'decision': 'select', 'reason': 'reviewed', 'layout_issues': []}],
        }
        report['scenes'][0]['selected'] = 'reviews/visual/asset-99/round-0/candidate-1.png'
        write_yaml_atomic(tmp_path / REPORT, report)
        if attempt == 0:
            index['review_sha256'] = sha256_file(tmp_path / REPORT)
            write_yaml_atomic(tmp_path / CANDIDATES, index)
            before = (tmp_path / CANDIDATES).read_bytes()
            assert not review_complete(tmp_path)
            assert not review_complete(tmp_path)  # Read-only polling must not spend retries.
            assert (tmp_path / CANDIDATES).read_bytes() == before
        if attempt == 2:
            with pytest.raises(ValueError, match='S01.*asset-99.*' + selected):
                ensure_candidates(tmp_path, board, manifest, generate=_generate)
            break
        index = ensure_candidates(tmp_path, board, manifest, generate=_generate)
        assert not review_complete(tmp_path)
        assert not (tmp_path / REPORT).exists()
        assert index['assets'][0]['selected'] == selected
        assert sha256_file(tmp_path / index['assets'][0]['path']) == image_hash


@pytest.mark.parametrize('locked', [False, True])
def test_stale_review_recovers_only_after_inspection(tmp_path, locked):
    from healthvideo.workflows.visual_review import (
        CANDIDATES,
        REPORT,
        ensure_candidates,
        review_complete,
    )

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    submit(tmp_path)
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    index = read_yaml(tmp_path / CANDIDATES)
    index['assets'][0]['locked'] = locked
    report = read_yaml(tmp_path / REPORT)
    report['scenes'][0]['selected'] = 'old/path.png'
    write_yaml_atomic(tmp_path / REPORT, report)
    index['review_sha256'] = sha256_file(tmp_path / REPORT)
    write_yaml_atomic(tmp_path / CANDIDATES, index)
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    submit(tmp_path)
    report = read_yaml(tmp_path / REPORT)
    report['inspected_images'] = []
    write_yaml_atomic(tmp_path / REPORT, report)
    with pytest.raises(ValueError, match='inspect'):
        ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    submit(tmp_path)
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    assert review_complete(tmp_path)
    assert not read_yaml(tmp_path / CANDIDATES).get('stale_review_count')


@pytest.mark.parametrize('problem', ['candidate', 'style'])
def test_stale_review_does_not_hide_invalid_selection_or_style(tmp_path, problem):
    from healthvideo.workflows.visual_review import (
        CANDIDATES,
        REPORT,
        ensure_candidates,
        review_complete,
    )

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    submit(tmp_path)
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    index = read_yaml(tmp_path / CANDIDATES)
    report = read_yaml(tmp_path / REPORT)
    report['scenes'][0]['selected'] = 'old/path.png'
    if problem == 'candidate':
        index['assets'][0]['selected'] = 'not/a/candidate.png'
    else:
        report['scenes'][0]['style_issues'] = ['style_hands']
    write_yaml_atomic(tmp_path / REPORT, report)
    index['review_sha256'] = sha256_file(tmp_path / REPORT)
    write_yaml_atomic(tmp_path / CANDIDATES, index)
    with pytest.raises(ValueError, match='reviewed candidate|style_hands'):
        review_complete(tmp_path)


def test_runner_prepares_stale_report_before_agent_prompt(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from healthvideo.workflows import runner
    from healthvideo.workflows.visual_review import (
        CANDIDATES,
        REPORT,
        ensure_candidates,
    )

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    submit(tmp_path)
    ensure_candidates(tmp_path, _board(), manifest, generate=_generate)
    index = read_yaml(tmp_path / CANDIDATES)
    selected = index['assets'][0]['selected']
    report = read_yaml(tmp_path / REPORT)
    report['scenes'][0]['selected'] = 'old/path.png'
    write_yaml_atomic(tmp_path / REPORT, report)
    index['review_sha256'] = sha256_file(tmp_path / REPORT)
    write_yaml_atomic(tmp_path / CANDIDATES, index)
    (tmp_path / 'project.yaml').write_text('synthetic')
    monkeypatch.setattr(runner, 'resolve_project_layout', lambda _: SimpleNamespace(artifact_root=tmp_path))
    monkeypatch.setattr(runner, 'render_prompt', lambda *a, **k: 'normal prompt\n## Quy tắc cứng\nKEEP GATES')
    monkeypatch.setattr(runner, 'prompt_block', lambda *a, **k: '')
    prompt = runner._build_step_prompt(
        tmp_path, SimpleNamespace(company=None),
        SimpleNamespace(slug='test', title='test', question='test', doctor_note=''),
        tmp_path, 'visual_review',
    )
    assert 'Báo cáo cũ lệch chỉ mục' in prompt
    assert selected in prompt
    assert not (tmp_path / REPORT).exists()
    assert read_yaml(tmp_path / CANDIDATES)['stale_review_count'] == 1
    assert 'KEEP GATES' in prompt
