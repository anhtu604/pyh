"""Bounded visual selection on derived assets; never edit medically approved recipes."""

import json
import math
import shutil
import subprocess
from pathlib import Path

from healthvideo.domain.asset_manifest import AssetKind, AssetManifest
from healthvideo.domain.format_profile import FORMAT_SPECS
from healthvideo.domain.storyboard import SceneAnatomy, SceneBeat, Storyboard
from healthvideo.process import run_with_deadline, timeout_diagnostic
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.visuals.flux import generate_candidates, illustration_recipe_hash

CANDIDATES = 'reviews/visual/candidates.yaml'
REPORT = 'reviews/visual-review.yaml'
MAX_REGENERATIONS = 2
CONTACT_SHEET_TIMEOUT = 15 * 60  # Decode the full video and sample every scene/beat.
STYLE_ERROR_CODES: dict[str, str] = {
    'style_palette': 'Sai bảng màu PYH (off_white/navy/teal/yellow/night, >3 màu nổi hoặc đỏ báo động)',
    'style_typography': 'Sai font Be Vietnam Pro, cỡ chữ nhỏ dưới ngưỡng hoặc tương phản < 4.5:1',
    'style_mascot_pose': 'Tư thế mascot không khớp ý lời đọc hoặc sai bảng 9 tư thế mục 2',
    'style_stroke': 'Sai nét 2D phẳng matte (gradient, bóng đổ, grain, ảnh stock hoặc lệch nét navy)',
    'style_medical_art': 'Dùng FLUX/tự vẽ thay hình y khoa chuẩn khoa học hoặc sai màu giải phẫu thực tế',
    'style_caption': 'Phụ đề đè hình/nhãn/mascot, vượt dòng/ký tự hoặc có tô sáng từng chữ',
    'style_zoom': 'Phóng to y khoa dùng cross-fade chồng mờ thay vì kính lúp hoặc lệch vùng nguồn',
}
MASCOT_POSES: frozenset[str] = frozenset({
    'welcome', 'explain', 'point_up', 'thinking', 'surprised',
    'caution', 'myth_bust', 'blank_board', 'thumbs_up',
})


def _extract_style_code(raw: str) -> str:
    return raw.split(':', 1)[0].strip()


def validate_style_issues(row: dict) -> list[str]:
    """Validate optional style_issues/mascot_pose fields and any style_* codes in layout_issues."""
    codes: list[str] = []
    pose = row.get('mascot_pose')
    if pose is not None and (not isinstance(pose, str) or pose not in MASCOT_POSES):
        raise ValueError(f'Unknown mascot_pose: {pose!r}')
    raw_style = row.get('style_issues')
    if raw_style is not None:
        if not isinstance(raw_style, list):
            raise TypeError('Visual review style_issues must be a list')
        for item in raw_style:
            if isinstance(item, str):
                code = _extract_style_code(item)
            elif isinstance(item, dict):
                code = item.get('code', '')
                if not isinstance(code, str):
                    raise TypeError('Visual review style_issues entry code must be a string')
                for note_key in ('detail', 'note'):
                    if note_key in item and item[note_key] is not None and not isinstance(item[note_key], str):
                        raise TypeError(f'Visual review style_issues {note_key} must be a string')
            else:
                raise TypeError('Visual review style_issues items must be strings or mappings')
            if code not in STYLE_ERROR_CODES:
                raise ValueError(f'Unknown style error code: {code!r}')
            if code not in codes:
                codes.append(code)
    for issue in row.get('layout_issues', []):
        if isinstance(issue, str) and issue.lstrip().startswith('style_'):
            code = _extract_style_code(issue.lstrip())
            if code not in STYLE_ERROR_CODES:
                raise ValueError(f'Unknown style error code: {code!r}')
            if code not in codes:
                codes.append(code)
    return codes


def review_pending(project: Path) -> bool:
    if not (project / 'project.yaml').is_file():
        return False
    root = resolve_project_layout(project).artifact_root
    return (root / CANDIDATES).is_file() and not review_complete(root)


def review_complete(root: Path) -> bool:
    if not (root / CANDIDATES).is_file():
        return True
    data = read_yaml(root / CANDIDATES)
    _check_candidates(root, data)
    complete = bool(data.get('assets')) and all(
        asset.get('selected') or asset.get('fallback') for asset in data['assets']
    ) and (root / REPORT).is_file() and data.get('review_sha256') == sha256_file(root / REPORT)
    if complete:
        report = read_yaml(root / REPORT)
        rows = {row['scene']: row for row in report.get('scenes', [])}
        for asset in data['assets']:
            for scene in asset['scenes']:
                row = rows.get(scene, {})
                validate_style_issues(row)
                if asset.get('selected'):
                    if row.get('decision') != 'select' or row.get('selected') != asset['selected']:
                        raise ValueError('Visual review selection changed after agent decision')
                    if asset['selected'] not in {c['path'] for c in asset['candidates']}:
                        raise ValueError('Visual review selection is not a reviewed candidate')
                elif row.get('decision') != 'reject' or asset['round'] != MAX_REGENERATIONS:
                    raise ValueError('Visual fallback requires exhausted reviewed candidates')
    return complete


def _safe_path(root: Path, relative: str) -> Path:
    path = root / relative
    if not isinstance(relative, str) or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Visual review path must remain within the active revision')
    return path


def _check_candidates(root: Path, data: dict) -> None:
    for asset in data['assets']:
        for candidate in asset['candidates']:
            path = _safe_path(root, candidate['path'])
            if not path.is_file() or sha256_file(path) != candidate['sha256']:
                raise ValueError(f"Visual review candidate changed: {candidate['path']}")


def _fallback_subject(board: Storyboard, scenes: list[str]) -> str:
    narrated = ' '.join(scene.narration for scene in board.scenes if scene.id in scenes).casefold()
    if not any(term in (board.title + ' ' + narrated).casefold() for term in ('gout', 'gút', 'urat')):
        raise ValueError('Visual review exhausted: topic-specific SVG overview is required')
    return ('gout_foot_overview' if any(term in narrated for term in
                                     ('bàn chân', 'ngón chân', 'toe', 'foot'))
            else 'joint_fluid_urate_to_inflammation')


def _consume_report(root: Path, data: dict, board: Storyboard) -> None:
    report_path = root / REPORT
    if not report_path.is_file() or data.get('review_sha256') == sha256_file(report_path):
        return
    report = read_yaml(report_path)
    if report.get('candidate_index_sha256') != sha256_file(root / CANDIDATES):
        raise ValueError('Visual review does not match current candidate index')
    sheets = data.get('contact_sheets') or [data.get('contact_sheet')]
    for sheet in sheets:
        if not sheet or not _safe_path(root, sheet['path']).is_file() or (
            sha256_file(root / sheet['path']) != sheet['sha256']
        ):
            raise ValueError('Visual review requires current rendered contact sheet')
    pending = [a for a in data['assets'] if not a.get('selected') and not a.get('fallback')]
    required = {c['path'] for a in pending for c in a['candidates']} | {s['path'] for s in sheets}
    if not required.issubset(set(report.get('inspected_images', []))):
        raise ValueError('Agent must inspect all candidates and the rendered contact sheet')
    decisions = list(report.get('scenes', []))
    scene_ids = [scene for asset in data['assets'] for scene in asset['scenes']]
    reported_ids = [row.get('scene', '') for row in decisions]
    if len(reported_ids) != len(set(reported_ids)) or not set(reported_ids).issubset(scene_ids):
        raise ValueError('Visual review has duplicate or nonexistent scene')
    by_scene = {row['scene']: row for row in decisions}
    previous_path = root / 'reviews/visual' / f"review-{data.get('review_count', 0) - 1:02d}.yaml"
    previous_rows = ({row['scene']: row for row in read_yaml(previous_path).get('scenes', [])}
                     if previous_path.is_file() else {})
    for asset in data['assets']:
        if not asset.get('selected') and not asset.get('fallback'):
            continue
        for scene in asset['scenes']:
            row = by_scene.get(scene)
            if row and row.get('blocking_safety'):
                raise ValueError(f'blocking_safety: {scene}; cần bác sĩ kiểm tra hình đã chọn')
            expected = 'select' if asset.get('selected') else 'reject'
            accepted = previous_rows.get(scene) or {
                'scene': scene, 'decision': expected, 'selected': asset.get('selected'),
                'reason': 'Giữ nguyên quyết định đã duyệt.', 'layout_issues': []}
            if row and row != accepted:
                report.setdefault('dropped_issues', []).append({
                    'issue': row, 'reason': 'Cannot reopen an accepted scene; kept previous selection'})
                decisions.remove(row)
                row = None
            if not row:
                decisions.append(accepted)
    if sorted(row.get('scene', '') for row in decisions) != sorted(scene_ids):
        raise ValueError('Visual review needs exactly one decision for each illustrated scene')
    by_scene = {row['scene']: row for row in decisions}
    for asset in data['assets']:
        if asset.get('selected') or asset.get('fallback'):
            continue
        rows = [by_scene[scene] for scene in asset['scenes']]
        if any(not str(row.get('reason', '')).strip() or
               not isinstance(row.get('layout_issues'), list) for row in rows):
            raise ValueError('Visual review requires a reason and layout_issues list')
        for row in rows:
            validate_style_issues(row)
        selections = {row.get('selected') for row in rows}
        kinds = {row.get('decision') for row in rows}
        if kinds == {'select'} and len(selections) == 1:
            selected = selections.pop()
            if selected not in {c['path'] for c in asset['candidates']}:
                raise ValueError('Visual review must select an existing candidate')
            asset['selected'] = selected
        elif kinds == {'reject'}:
            prompts = {row.get('new_prompt') for row in rows}
            if len(prompts) != 1 or not str(next(iter(prompts)) or '').strip():
                raise ValueError('Rejected illustrations require one concrete new_prompt')
            if asset['round'] < MAX_REGENERATIONS:
                asset.update(round=asset['round'] + 1, prompt=prompts.pop(), candidates=[], selected=None)
            else:
                asset['fallback'] = _fallback_subject(board, asset['scenes'])
                asset['fallback_reason'] = ('Normal qualitative overview only; no new disease state, '
                                            'labels or unsupported foot localization added.')
        else:
            raise ValueError('Scenes sharing one asset must agree on select/reject and candidate')
    if decisions != report.get('scenes', []) or report.get('dropped_issues'):
        write_yaml_atomic(report_path, {**report, 'scenes': decisions})
    data['review_sha256'] = sha256_file(report_path)
    # Keep every round and its reasons available to the physician.
    archive = root / 'reviews/visual' / f"review-{data.get('review_count', 0):02d}.yaml"
    shutil.copyfile(report_path, archive)
    data['review_count'] = data.get('review_count', 0) + 1


def ensure_candidates(root: Path, board: Storyboard, manifest: AssetManifest, *, generate) -> dict:
    spec = FORMAT_SPECS[board.format_profile]
    referenced = {Path(ref.path).as_posix() for scene in board.scenes for ref in scene.visual_assets}
    assets = [a for a in manifest.assets if a.kind is AssetKind.ILLUSTRATION and a.path in referenced]
    if not assets:
        return {}
    recipes = canonical_json_hash({
        'storyboard': board.model_dump(mode='json'),
        'assets': [[a.path, illustration_recipe_hash(a.prompt, spec.width, spec.height, a.seed)] for a in assets],
    })
    path = root / CANDIDATES
    data = read_yaml(path) if path.is_file() else {}
    if data.get('recipes_sha256') != recipes:
        if (root / REPORT).is_file():
            old = root / REPORT
            old.rename(root / 'reviews/visual' / f'stale-review-{sha256_file(old)}.yaml')
        data = {'recipes_sha256': recipes, 'assets': [{
            'path': a.path, 'prompt': a.prompt, 'seed': a.seed, 'round': 0,
            'scenes': [s.id for s in board.scenes if any(Path(r.path).as_posix() == a.path for r in s.visual_assets)],
            'candidates': [], 'selected': None, 'fallback': None,
        } for a in assets]}
    else:
        _check_candidates(root, data)
        review_complete(root)
        _consume_report(root, data, board)
    for number, asset in enumerate(data['assets']):
        if not asset['candidates']:
            paths = generate_candidates(
                asset['prompt'], out_dir=root / 'reviews/visual' / f"asset-{number:02d}" / f"round-{asset['round']}",
                width=spec.width, height=spec.height, seed=(asset['seed'] + asset['round'] * 3) % 2**63,
                generate=generate,
            )
            asset['candidates'] = [{
                'path': p.relative_to(root).as_posix(), 'sha256': sha256_file(p),
                'seed': (asset['seed'] + asset['round'] * 3 + i) % 2**63,
            } for i, p in enumerate(paths)]
        if not asset.get('fallback'):
            source = root / (asset.get('selected') or asset['candidates'][0]['path'])
            destination = root / asset['path']
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    if not path.is_file() or read_yaml(path) != data:
        write_yaml_atomic(path, data)
    return data


def visual_identity(root: Path) -> dict:
    if (root / CANDIDATES).is_file():
        _check_candidates(root, read_yaml(root / CANDIDATES))
    return {relative: sha256_file(root / relative) for relative in (CANDIDATES, REPORT)
            if (root / relative).is_file()}


def apply_visual_fallbacks(root: Path, board: Storyboard) -> Storyboard:
    if not (root / CANDIDATES).is_file():
        return board
    fallback = {scene: _fallback_subject(board, a['scenes']) for a in read_yaml(root / CANDIDATES)['assets']
                if a.get('fallback') for scene in a['scenes']}
    return board.model_copy(update={'scenes': tuple(
        scene.model_copy(update={
            'visual': 'anatomy_animation', 'visual_assets': (),
            'anatomy': SceneAnatomy(subject=fallback[scene.id], state='normal', severity=0,
                                   motion='overview'),
            'beats': tuple(SceneBeat(at=frame / 30, start_frame=frame,
                                    focus=('foot' if fallback[scene.id] == 'gout_foot_overview' else 'fluid')
                                    if i % 2 == 0 else None)
                           for i, frame in enumerate(range(0, scene.duration_frames, 120))),
            'labels': (), 'annotations': (),
        }) if scene.id in fallback else scene for scene in board.scenes
    )})


def prepare_contact_sheet(root: Path, *, runner=None, final: bool = False) -> None:
    """FFmpeg samples each scene and beat; final sheets bind to the selected render."""
    runner = runner or subprocess.run
    index_path = root / CANDIDATES
    if not index_path.is_file():
        return
    rendered = json.loads((root / 'renders/render-input.json').read_text(encoding='utf-8'))
    frames = {0}
    for scene in rendered['scenes']:
        start, duration = scene['start_frame'], scene['duration_frames']
        frames.add(start + duration // 2)
        frames.update(start + min(duration-1, b['start_frame'] + round(.3*rendered['fps']))
                      for b in scene.get('beats', []) if b.get('start_frame') is not None)
    # A short opening illustration always receives its own frame, independent of duration.
    ordered = sorted(frames)
    # FFmpeg's expression parser rejects more than 100 chained terms (gout hit this on
    # 2026-11-13); grouping 50 per parenthesis keeps every level short.
    # ponytail: fine up to 5,000 sampled frames; nest one more level if a video ever needs more.
    expression = '+'.join('(' + '+'.join(f'eq(n\\,{frame})' for frame in ordered[i:i + 50]) + ')'
                          for i in range(0, len(ordered), 50))
    prefix = 'final-contact-sheet' if final else 'contact-sheet'
    pattern = root / 'reviews/visual' / f'{prefix}-%03d.jpg'
    for old in pattern.parent.glob(f'{prefix}-*.jpg'):
        old.unlink()
    try:
        result = run_with_deadline([
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(root / 'renders/video.mp4'),
            '-vf', f'select={expression},scale=384:-1,tile=5x5', '-vsync', 'vfr',
            '-frames:v', str(math.ceil(len(frames) / 25)), str(pattern),
        ], timeout=CONTACT_SHEET_TIMEOUT, runner=runner, capture_output=True, text=True, check=False)
    except subprocess.TimeoutExpired as error:
        for partial in pattern.parent.glob(f'{prefix}-*.jpg'):
            partial.unlink(missing_ok=True)
        raise RuntimeError(f'Visual review contact sheet {timeout_diagnostic(error)}') from error
    paths = sorted(pattern.parent.glob(f'{prefix}-*.jpg'))
    if result.returncode or len(paths) != math.ceil(len(frames) / 25):
        raise RuntimeError(f'Visual review contact sheet failed: {result.stderr}')
    sheets = [{'path': p.relative_to(root).as_posix(), 'sha256': sha256_file(p)} for p in paths]
    if final:
        write_yaml_atomic(root / 'reviews/visual/final-contact-sheets.yaml', {
            'render_sha256': sha256_file(root / 'renders/video.mp4'),
            'render_manifest_sha256': sha256_file(root / 'renders/render-manifest.json'),
            'sheets': sheets, 'sample_frames': sorted(frames),
        })
        return
    data = read_yaml(index_path)
    data['contact_sheet'] = sheets[0]
    data['contact_sheets'] = sheets
    data['sample_frames'] = sorted(frames)
    write_yaml_atomic(index_path, data)
