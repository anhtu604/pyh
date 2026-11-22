"""Bounded visual selection on derived assets; never edit medically approved recipes."""

import json
import math
import os
import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from healthvideo.domain.asset_manifest import AssetKind, AssetManifest, AssetRecord
from healthvideo.domain.format_profile import FORMAT_SPECS
from healthvideo.domain.storyboard import SceneAnatomy, SceneBeat, Storyboard
from healthvideo.process import run_with_deadline, timeout_diagnostic
from healthvideo.storage.files import (
    canonical_json_hash,
    read_agent_yaml,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.visuals.flux import (
    generate_candidates,
    illustration_recipe_hash,
    validate_illustration_png,
)

CANDIDATES = 'reviews/visual/candidates.yaml'
REPORT = 'reviews/visual-review.yaml'
MAX_REGENERATIONS = 2
CONTACT_SHEET_TIMEOUT = 15 * 60  # Decode the full video and sample every scene/beat.
_FFMPEG_SELECT_BATCH_SIZE = 50
_WINDOWS_RETRY_ERRORS = frozenset({5, 32})
STYLE_ERROR_CODES: dict[str, str] = {
    'style_palette': 'Sai bảng màu PYH (off_white/navy/teal/yellow/night, >3 màu nổi hoặc đỏ báo động)',
    'style_typography': 'Sai font Be Vietnam Pro, cỡ chữ nhỏ dưới ngưỡng hoặc tương phản < 4.5:1',
    'style_mascot_pose': 'Tư thế mascot không khớp ý lời đọc hoặc sai bảng 9 tư thế mục 2',
    'style_stroke': 'Sai nét 2D phẳng matte (gradient, bóng đổ, grain, ảnh stock hoặc lệch nét navy)',
    'style_medical_art': 'Dùng FLUX/tự vẽ thay hình y khoa chuẩn khoa học hoặc sai màu giải phẫu thực tế',
    'style_caption': 'Phụ đề đè hình/nhãn/mascot, vượt dòng/ký tự hoặc có tô sáng từng chữ',
    'style_zoom': 'Phóng to y khoa dùng cross-fade chồng mờ thay vì kính lúp hoặc lệch vùng nguồn',
    'style_hands': 'Bàn tay sai giải phẫu (sai số ngón, ngón cái lệch chỗ, ngón quá dài/dính/chồng, cổ tay đứt khúc)',
    'style_rights': 'Ảnh có logo, nhãn thương hiệu, chữ thương hiệu, khuôn mặt người thật dễ nhận ra hoặc nhân vật có bản quyền',
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
    for blocking_code in ('style_hands', 'style_rights'):
        if blocking_code in codes and row.get('decision') == 'select':
            raise ValueError(
                f'Visual review cannot select a candidate with {blocking_code}; reject and provide new_prompt'
            )
    return codes


def review_pending(project: Path) -> bool:
    if not (project / 'project.yaml').is_file():
        return False
    root = resolve_project_layout(project).artifact_root
    return (root / CANDIDATES).is_file() and not review_complete(root)


def _report_selection_mismatches(data: dict, report: dict) -> list[str]:
    """Check real validation errors before classifying report/index drift as stale."""
    rows = {row['scene']: row for row in report.get('scenes', [])}
    mismatches = []
    for asset in data.get('assets', []):
        selected = asset.get('selected')
        if selected and selected not in {c['path'] for c in asset['candidates']}:
            raise ValueError('Visual review selection is not a reviewed candidate')
        if asset.get('locked') and not selected:
            raise ValueError('Visual review selection is not a reviewed candidate')
        if asset.get('fallback') and asset['round'] != MAX_REGENERATIONS:
            raise ValueError('Visual fallback requires exhausted reviewed candidates')
        for scene in asset['scenes']:
            row = rows.get(scene, {})
            validate_style_issues(row)
            if row.get('blocking_safety'):
                raise ValueError(f'blocking_safety: {scene}; cần bác sĩ kiểm tra hình đã chọn')
            expected = 'select' if selected else 'reject'
            if (selected or asset.get('fallback')) and (
                row.get('decision') != expected or (selected and row.get('selected') != selected)
            ):
                mismatches.append(
                    f"{scene}: report {row.get('decision')!r} {row.get('selected')!r}; "
                    f"index {expected!r} {selected!r}"
                )
    return mismatches


def _archive_stale_selection(root: Path, data: dict, mismatches: list[str]) -> None:
    """Spend a retry only when retiring a report, never during read-only polling."""
    count = data.get('stale_review_count', 0)
    if count >= 2:
        raise ValueError('Visual review selection changed after 2 re-reviews: ' + '; '.join(mismatches))
    report = root / REPORT
    archive = root / 'reviews/visual' / f'stale-visual-review-{count + 1}-{sha256_file(report)}.yaml'
    _replace_atomic_with_retry(report, archive)
    data['stale_review_count'] = count + 1
    data.pop('review_sha256', None)


def review_complete(root: Path) -> bool:
    if not (root / CANDIDATES).is_file():
        return True
    data = read_yaml(root / CANDIDATES)
    _check_candidates(root, data)
    assets = data.get('assets') or []
    all_locked = bool(assets) and all(asset.get('locked') for asset in assets)
    if all_locked:
        for asset in assets:
            if not asset.get('selected') or asset['selected'] not in {
                c['path'] for c in asset.get('candidates', [])
            }:
                raise ValueError('Visual review selection is not a reviewed candidate')
    consumed = (root / REPORT).is_file() and data.get('review_sha256') == sha256_file(root / REPORT)
    complete = bool(assets) and all(
        asset.get('selected') or asset.get('fallback') for asset in assets
    ) and consumed
    if complete and _report_selection_mismatches(data, read_yaml(root / REPORT)):
        return False
    if data.get('stale_review_count'):
        return False
    return all_locked or complete


def prepare_stale_review(root: Path) -> str:
    """Retire a consumed stale report before the runner asks the agent to review again."""
    if not (root / CANDIDATES).is_file():
        return ''
    data = read_yaml(root / CANDIDATES)
    _check_candidates(root, data)
    if (root / REPORT).is_file() and data.get('review_sha256') == sha256_file(root / REPORT):
        mismatches = _report_selection_mismatches(data, read_yaml(root / REPORT))
        if mismatches:
            _archive_stale_selection(root, data, mismatches)
            write_yaml_atomic(root / CANDIDATES, data)
    if not data.get('stale_review_count'):
        return ''
    selections = [
        {'scenes': asset['scenes'], 'decision': 'select' if asset.get('selected') else 'reject',
         'selected': asset.get('selected'), 'locked': bool(asset.get('locked'))}
        for asset in data['assets']
    ]
    return (
        'Báo cáo cũ lệch chỉ mục: đây là ngoại lệ cho quy tắc bỏ qua cảnh đã chọn. '
        'Phải mở lại mọi candidate và contact sheet hiện tại; báo cáo đủ mọi cảnh, '
        'kể cả cảnh đã có selected/fallback. Đối chiếu đường dẫn trong chỉ mục hiện tại, '
        'không sao chép báo cáo cũ. Giữ nguyên ảnh đã chọn, đặc biệt ảnh locked; '
        'nếu phát hiện lỗi an toàn, ghi blocking_safety và dừng, không chọn cho xong. '
        'Ghi reason, layout_issues và inspected_images trung thực. Quyết định cần đối chiếu:\n'
        + json.dumps(selections, ensure_ascii=False)
    )


def _safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError('Visual review path must remain within the active revision')
    rel = PurePosixPath(relative)
    if (
        rel.is_absolute()
        or '\\' in relative
        or '..' in rel.parts
        or (rel.parts and ':' in rel.parts[0])
    ):
        raise ValueError('Visual review path must remain within the active revision')
    path = root.joinpath(*rel.parts)
    if not path.resolve().is_relative_to(root.resolve()):
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
    report = read_agent_yaml(report_path)
    if report.get('candidate_index_sha256') != sha256_file(root / CANDIDATES):
        raise ValueError('Visual review does not match current candidate index')
    sheets = data.get('contact_sheets') or [data.get('contact_sheet')]
    for sheet in sheets:
        if not sheet or not _safe_path(root, sheet['path']).is_file() or (
            sha256_file(root / sheet['path']) != sheet['sha256']
        ):
            raise ValueError('Visual review requires current rendered contact sheet')
    pending = [a for a in data['assets']
               if data.get('stale_review_count') or (not a.get('selected') and not a.get('fallback'))]
    required = {c['path'] for a in pending for c in a['candidates']} | {s['path'] for s in sheets}
    if not required.issubset(set(report.get('inspected_images', []))):
        raise ValueError('Agent must inspect all candidates and the rendered contact sheet')
    decisions = list(report.get('scenes', []))
    scene_ids = [scene for asset in data['assets'] for scene in asset['scenes']]
    reported_ids = [row.get('scene', '') for row in decisions]
    if len(reported_ids) != len(set(reported_ids)) or not set(reported_ids).issubset(scene_ids):
        raise ValueError('Visual review has duplicate or nonexistent scene')
    if data.get('stale_review_count'):
        mismatches = _report_selection_mismatches(data, report)
        if mismatches:
            _archive_stale_selection(root, data, mismatches)
            return
        for row in decisions:
            if not str(row.get('reason', '')).strip() or not isinstance(row.get('layout_issues'), list):
                raise ValueError('Visual review requires a reason and layout_issues list')
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
            accepted = (row if data.get('stale_review_count') else previous_rows.get(scene)) or {
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
    data.pop('stale_review_count', None)
    data['review_sha256'] = sha256_file(report_path)
    # Keep every round and its reasons available to the physician.
    archive = root / 'reviews/visual' / f"review-{data.get('review_count', 0):02d}.yaml"
    shutil.copyfile(report_path, archive)
    data['review_count'] = data.get('review_count', 0) + 1


def _replace_atomic_with_retry(source: Path, destination: Path) -> None:
    """Replace destination atomically with short backoff for transient Windows file locks."""
    for attempt in range(6):
        try:
            os.replace(source, destination)
            return
        except PermissionError as error:
            if os.name != 'nt' or getattr(error, 'winerror', None) not in _WINDOWS_RETRY_ERRORS or attempt == 5:
                raise
            time.sleep(min(0.005 * (2 ** attempt), 0.15))


def _copy_file_atomic(source: Path, destination: Path) -> None:
    """Copy a file to destination atomically via a sibling temporary file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f'.{destination.name}.', dir=destination.parent) as temp_dir:
        staged = Path(temp_dir) / destination.name
        with source.open('rb') as src, staged.open('wb') as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        _replace_atomic_with_retry(staged, destination)


def _valid_illustration_png(path: Path, width: int, height: int) -> bool:
    if not path.is_file():
        return False
    try:
        validate_illustration_png(path, width, height)
    except (OSError, ValueError):
        return False
    return True


def _internal_png_candidates(root: Path) -> list[Path]:
    """Return sorted revision-internal candidate/imported PNG paths safely inside ``root``."""
    resolved_root = root.resolve()
    candidates: list[Path] = []
    for base, pattern in (
        (root / 'reviews/visual', 'candidate-*.png'),
        (root / 'assets/imported', '*.png'),
    ):
        if not base.is_dir():
            continue
        iterator = base.rglob(pattern) if base.name == 'visual' else base.glob(pattern)
        for path in sorted(iterator):
            if path.is_file() and path.resolve().is_relative_to(resolved_root):
                candidates.append(path)
    return candidates


def _find_locked_illustration_match(
    root: Path,
    locked_sha256: str,
    width: int,
    height: int,
) -> Path | None:
    for candidate in _internal_png_candidates(root):
        if sha256_file(candidate) == locked_sha256 and _valid_illustration_png(candidate, width, height):
            return candidate
    return None


def restore_locked_illustrations(
    root: Path,
    board: Storyboard,
    manifest: AssetManifest,
) -> dict[str, Path]:
    """Verify or atomically restore every sha256-locked illustration; fail closed if unmatched."""
    spec = FORMAT_SPECS[board.format_profile]
    referenced = {PurePosixPath(ref.path).as_posix() for scene in board.scenes for ref in scene.visual_assets}
    resolved: dict[str, Path] = {}
    for record in manifest.assets:
        if record.kind is not AssetKind.ILLUSTRATION or record.path not in referenced or record.sha256 is None:
            continue
        destination = _safe_path(root, record.path)
        if (
            destination.is_file()
            and _valid_illustration_png(destination, spec.width, spec.height)
            and sha256_file(destination) == record.sha256
        ):
            matched = _find_locked_illustration_match(root, record.sha256, spec.width, spec.height)
            resolved[record.path] = matched or destination
            continue
        matched = _find_locked_illustration_match(root, record.sha256, spec.width, spec.height)
        if matched is None:
            raise ValueError(f'Generated illustration sha256 mismatch: {record.path}')
        _copy_file_atomic(matched, destination)
        if not _valid_illustration_png(destination, spec.width, spec.height) or sha256_file(destination) != record.sha256:
            raise ValueError(f'Generated illustration sha256 mismatch: {record.path}')
        resolved[record.path] = matched
    return resolved


def _illustrated_recipes_hash(
    board: Storyboard,
    assets: list[AssetRecord],
    width: int,
    height: int,
) -> str:
    """Hash only illustration configs and the scenes that reference illustrations."""
    illustrated_paths = {a.path for a in assets}
    illustrated_scenes = [
        scene.model_dump(mode='json', exclude={'start_frame'})
        for scene in board.scenes
        if any(PurePosixPath(ref.path).as_posix() in illustrated_paths for ref in scene.visual_assets)
    ]
    return canonical_json_hash({
        'format_profile': board.format_profile,
        'scenes': illustrated_scenes,
        'assets': [
            [a.path, a.sha256, illustration_recipe_hash(a.prompt, width, height, a.seed)]
            for a in assets
        ],
    })


def _asset_scene_signature(board: Storyboard, asset_path: str) -> str:
    scenes = [
        scene.model_dump(mode='json', exclude={'start_frame'})
        for scene in board.scenes
        if any(PurePosixPath(ref.path).as_posix() == asset_path for ref in scene.visual_assets)
    ]
    return canonical_json_hash(scenes)


def _locked_candidate_entries(
    root: Path,
    *,
    matched: Path,
    locked_sha256: str,
    seed: int,
    width: int,
    height: int,
    prior_assets: list[dict],
) -> tuple[list[dict], str]:
    prior_seeds = {
        c['path']: c['seed']
        for prev in prior_assets
        for c in prev.get('candidates', [])
        if isinstance(c, dict) and isinstance(c.get('path'), str) and isinstance(c.get('seed'), int)
    }
    matched_rel = matched.relative_to(root).as_posix()
    visual_dir = (root / 'reviews/visual').resolve()
    if matched.resolve().is_relative_to(visual_dir) and matched.name.startswith('candidate-'):
        round_files = [
            p for p in sorted(matched.parent.glob('candidate-*.png'))
            if p.resolve().is_relative_to(root.resolve()) and _valid_illustration_png(p, width, height)
        ]
        if round_files and matched in round_files:
            entries = [{
                'path': p.relative_to(root).as_posix(),
                'sha256': sha256_file(p),
                'seed': prior_seeds.get(p.relative_to(root).as_posix(), seed),
            } for p in round_files]
            return entries, matched_rel
    return [{'path': matched_rel, 'sha256': locked_sha256, 'seed': seed}], matched_rel


def _reusable_unlocked_asset(
    root: Path,
    *,
    record: AssetRecord,
    scene_ids: list[str],
    scene_sig: str,
    width: int,
    height: int,
    prior_assets: list[dict],
) -> dict | None:
    for prev in prior_assets:
        if prev.get('path') != record.path:
            continue
        prev_recipe_prompt = prev.get('recipe_prompt', prev.get('prompt'))
        if (
            prev_recipe_prompt != record.prompt
            or prev.get('seed') != record.seed
            or prev.get('width', width) != width
            or prev.get('height', height) != height
        ):
            continue
        prev_candidates = prev.get('candidates') or []
        if not prev_candidates:
            continue
        valid = True
        for cand in prev_candidates:
            rel = cand.get('path') if isinstance(cand, dict) else None
            if not isinstance(rel, str):
                valid = False
                break
            try:
                cand_path = _safe_path(root, rel)
            except ValueError:
                valid = False
                break
            if not _valid_illustration_png(cand_path, width, height) or sha256_file(cand_path) != cand.get('sha256'):
                valid = False
                break
        if not valid:
            continue
        same_scenes = prev.get('scene_signature') == scene_sig
        selected = prev.get('selected') if same_scenes else None
        fallback = prev.get('fallback') if same_scenes else None
        if selected is not None and selected not in {c['path'] for c in prev_candidates}:
            selected = None
        entry = {
            'path': record.path,
            'prompt': prev.get('prompt', record.prompt),
            'recipe_prompt': record.prompt,
            'seed': record.seed,
            'width': width,
            'height': height,
            'round': prev.get('round', 0),
            'scenes': scene_ids,
            'scene_signature': scene_sig,
            'candidates': [dict(c) for c in prev_candidates],
            'selected': selected,
            'fallback': fallback,
        }
        if same_scenes and prev.get('fallback_reason'):
            entry['fallback_reason'] = prev['fallback_reason']
        return entry
    return None


def _candidate_out_dir(
    root: Path,
    *,
    number: int,
    round_number: int,
    claimed_paths: set[str],
    locked_hashes: set[str],
) -> Path:
    slot = number
    while True:
        out_dir = root / 'reviews/visual' / f'asset-{slot:02d}' / f'round-{round_number}'
        existing = list(out_dir.glob('candidate-*.png')) if out_dir.is_dir() else []
        conflict = any(
            p.relative_to(root).as_posix() in claimed_paths
            or (locked_hashes and sha256_file(p) in locked_hashes)
            for p in existing
            if p.is_file()
        )
        if not conflict:
            return out_dir
        slot += 1


def _next_review_count(root: Path, prior: dict) -> int:
    prior_count = prior.get('review_count', 0) if isinstance(prior, dict) else 0
    if not isinstance(prior_count, int):
        prior_count = 0
    visual_dir = root / 'reviews/visual'
    highest_archived = 0
    if visual_dir.is_dir():
        for archive in visual_dir.glob('review-[0-9][0-9].yaml'):
            try:
                highest_archived = max(highest_archived, int(archive.stem.split('-', 1)[1]) + 1)
            except ValueError:
                continue
    return max(prior_count, highest_archived)


def ensure_candidates(root: Path, board: Storyboard, manifest: AssetManifest, *, generate) -> dict:
    spec = FORMAT_SPECS[board.format_profile]
    referenced = {PurePosixPath(ref.path).as_posix() for scene in board.scenes for ref in scene.visual_assets}
    assets = [a for a in manifest.assets if a.kind is AssetKind.ILLUSTRATION and a.path in referenced]
    if not assets:
        return {}
    locked_sources = restore_locked_illustrations(root, board, manifest)
    by_path = {a.path: a for a in assets}
    locked_hashes = {a.sha256 for a in assets if a.sha256 is not None}
    recipes = _illustrated_recipes_hash(board, assets, spec.width, spec.height)
    path = root / CANDIDATES
    prior_exists = path.is_file()
    prior = read_yaml(path) if prior_exists else {}
    prior_assets = list(prior.get('assets', [])) if isinstance(prior, dict) else []
    if prior.get('recipes_sha256') != recipes:
        if (root / REPORT).is_file():
            old = root / REPORT
            (root / 'reviews/visual').mkdir(parents=True, exist_ok=True)
            _replace_atomic_with_retry(old, root / 'reviews/visual' / f'stale-review-{sha256_file(old)}.yaml')
        new_assets: list[dict] = []
        for a in assets:
            assert a.prompt is not None and a.seed is not None
            scene_ids = [
                s.id for s in board.scenes
                if any(PurePosixPath(r.path).as_posix() == a.path for r in s.visual_assets)
            ]
            scene_sig = _asset_scene_signature(board, a.path)
            if a.sha256 is not None:
                cands, selected = _locked_candidate_entries(
                    root,
                    matched=locked_sources[a.path],
                    locked_sha256=a.sha256,
                    seed=a.seed,
                    width=spec.width,
                    height=spec.height,
                    prior_assets=prior_assets,
                )
                new_assets.append({
                    'path': a.path,
                    'prompt': a.prompt,
                    'recipe_prompt': a.prompt,
                    'seed': a.seed,
                    'width': spec.width,
                    'height': spec.height,
                    'round': 0,
                    'scenes': scene_ids,
                    'scene_signature': scene_sig,
                    'candidates': cands,
                    'selected': selected,
                    'fallback': None,
                    'locked': True,
                })
                continue
            reused = _reusable_unlocked_asset(
                root,
                record=a,
                scene_ids=scene_ids,
                scene_sig=scene_sig,
                width=spec.width,
                height=spec.height,
                prior_assets=prior_assets,
            )
            if reused is not None:
                new_assets.append(reused)
            else:
                new_assets.append({
                    'path': a.path,
                    'prompt': a.prompt,
                    'recipe_prompt': a.prompt,
                    'seed': a.seed,
                    'width': spec.width,
                    'height': spec.height,
                    'round': 0,
                    'scenes': scene_ids,
                    'scene_signature': scene_sig,
                    'candidates': [],
                    'selected': None,
                    'fallback': None,
                })
        data = {
            'recipes_sha256': recipes,
            'review_count': _next_review_count(root, prior),
            'assets': new_assets,
        }
    else:
        data = prior
        _check_candidates(root, data)
        if (root / REPORT).is_file() and data.get('review_sha256') == sha256_file(root / REPORT):
            mismatches = _report_selection_mismatches(data, read_yaml(root / REPORT))
            if mismatches:
                _archive_stale_selection(root, data, mismatches)
        _consume_report(root, data, board)
    if not prior_exists and all(a.sha256 is not None for a in assets):
        return data
    claimed_paths = {
        c['path'] for item in data['assets'] for c in item.get('candidates', []) if isinstance(c, dict) and 'path' in c
    }
    for number, asset in enumerate(data['assets']):
        record = by_path[asset['path']]
        if record.sha256 is not None:
            # Locked illustrations are already verified/restored; never regenerate or overwrite them.
            continue
        if not asset['candidates']:
            out_dir = _candidate_out_dir(
                root,
                number=number,
                round_number=asset['round'],
                claimed_paths=claimed_paths,
                locked_hashes=locked_hashes,
            )
            paths = generate_candidates(
                asset['prompt'],
                out_dir=out_dir,
                width=spec.width,
                height=spec.height,
                seed=(asset['seed'] + asset['round'] * 3) % 2**63,
                generate=generate,
            )
            asset['candidates'] = [{
                'path': p.relative_to(root).as_posix(),
                'sha256': sha256_file(p),
                'seed': (asset['seed'] + asset['round'] * 3 + i) % 2**63,
            } for i, p in enumerate(paths)]
            claimed_paths.update(c['path'] for c in asset['candidates'])
        if not asset.get('fallback'):
            source = _safe_path(root, asset.get('selected') or asset['candidates'][0]['path'])
            destination = _safe_path(root, asset['path'])
            if not destination.is_file() or sha256_file(destination) != sha256_file(source):
                _copy_file_atomic(source, destination)
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


def _run_contact_sheet_batch(
    video: Path,
    batch: list[int],
    pattern: Path,
    *,
    runner,
) -> list[Path]:
    expression = '+'.join(f'eq(n\\,{frame})' for frame in batch)
    expected_count = math.ceil(len(batch) / 25)
    try:
        result = run_with_deadline([
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(video),
            '-vf', f'select={expression},scale=384:-1,tile=5x5', '-vsync', 'vfr',
            '-frames:v', str(expected_count), str(pattern),
        ], timeout=CONTACT_SHEET_TIMEOUT, runner=runner, capture_output=True, text=True, check=False)
    except subprocess.TimeoutExpired as error:
        for partial in pattern.parent.glob(pattern.name.replace('%03d', '*')):
            partial.unlink(missing_ok=True)
        raise RuntimeError(f'Visual review contact sheet {timeout_diagnostic(error)}') from error
    paths = sorted(pattern.parent.glob(pattern.name.replace('%03d', '*')))
    if result.returncode or len(paths) != expected_count:
        raise RuntimeError(f'Visual review contact sheet failed: {result.stderr}')
    return paths


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
    prefix = 'final-contact-sheet' if final else 'contact-sheet'
    visual_dir = root / 'reviews/visual'
    visual_dir.mkdir(parents=True, exist_ok=True)
    for old in visual_dir.glob(f'{prefix}-*.jpg'):
        old.unlink()
    video = root / 'renders/video.mp4'
    # Keep every FFmpeg select expression <= 50 terms (exactly 2 5x5 sheets) to prevent
    # av_expr_parse recursion/memory failures on long videos.
    if len(ordered) <= _FFMPEG_SELECT_BATCH_SIZE:
        paths = _run_contact_sheet_batch(
            video, ordered, visual_dir / f'{prefix}-%03d.jpg', runner=runner,
        )
    else:
        paths = []
        sheet_index = 1
        with TemporaryDirectory(prefix=f'.{prefix}-', dir=visual_dir) as temp_dir:
            for batch_index, offset in enumerate(range(0, len(ordered), _FFMPEG_SELECT_BATCH_SIZE)):
                batch_dir = Path(temp_dir) / f'batch-{batch_index:03d}'
                batch_dir.mkdir(parents=True, exist_ok=True)
                batch_paths = _run_contact_sheet_batch(
                    video,
                    ordered[offset:offset + _FFMPEG_SELECT_BATCH_SIZE],
                    batch_dir / f'{prefix}-%03d.jpg',
                    runner=runner,
                )
                for batch_path in batch_paths:
                    destination = visual_dir / f'{prefix}-{sheet_index:03d}.jpg'
                    _replace_atomic_with_retry(batch_path, destination)
                    paths.append(destination)
                    sheet_index += 1
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
