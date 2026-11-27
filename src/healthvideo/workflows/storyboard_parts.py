"""Incremental scene checkpoints, with the unchanged final storyboard contract."""

import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.storage.files import canonical_json_hash, read_yaml, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.storage.revision_lock import revision_lock

PART_FIELDS = {'script_sha256', 'status', 'missing', 'validation_error', 'rework_request'}
METADATA = 'storyboard/parts-metadata.yaml'
_PRE_GATE_STATES = frozenset({WorkflowState.DRAFT_READY, WorkflowState.NEEDS_MEDICAL_REVISION})


def _can_migrate(root: Path) -> bool:
    if (root / 'storyboard/parts').is_dir() or not (root / 'storyboard/storyboard.yaml').is_file():
        return False
    if not (root / 'script/script.yaml').is_file():
        return False
    try:
        project_dir = root.parents[1]
    except IndexError:
        return False
    if not (project_dir / 'project.yaml').is_file():
        return False
    try:
        layout = resolve_project_layout(project_dir)
        if layout.manifest.state not in _PRE_GATE_STATES:
            return False
        board = read_yaml(root / 'storyboard/storyboard.yaml')
        if not isinstance(board, dict) or not isinstance(board.get('scenes'), list):
            return False
        return len(board['scenes']) == len(_lines(root))
    except (OSError, ValueError, TypeError, AttributeError, yaml.YAMLError):
        return False


def migrate(root: Path) -> None:
    """Split a pre-gate 1-to-1 monolithic storyboard into scene parts once."""
    with revision_lock(root):
        if (root / 'storyboard/parts').is_dir():
            return
        board = read_yaml(root / 'storyboard/storyboard.yaml')
        scenes = board.get('scenes') if isinstance(board, dict) else None
        lines = _lines(root)
        if not isinstance(board, dict) or not isinstance(scenes, list) or len(scenes) != len(lines):
            raise ValueError('Storyboard không ánh xạ 1-1 theo thứ tự với kịch bản.')
        hashes = script_hashes(root)
        write_yaml_atomic(root / METADATA, {k: v for k, v in board.items() if k != 'scenes'})
        for (scene_id, line), raw_scene in zip(lines.items(), scenes, strict=True):
            part = (
                {k: v for k, v in raw_scene.items() if k not in PART_FIELDS}
                if isinstance(raw_scene, dict)
                else {}
            )
            part['id'] = scene_id
            part['script_sha256'] = hashes[scene_id]
            mismatches = []
            if part.get('script_line_id') != line.id:
                mismatches.append('script_line_id')
            if part.get('narration') != line.text:
                mismatches.append('narration')
            if part.get('claim_id') != line.claim_id:
                mismatches.append('claim_id')
            if part.get('clip_only') != line.clip_id:
                mismatches.append('clip_only')
            if mismatches:
                part['status'] = 'invalid'
                part['validation_error'] = 'không khớp dòng kịch bản: ' + ', '.join(mismatches)
            else:
                try:
                    Scene.model_validate(_scene(part))
                except (ValueError, TypeError) as exc:
                    part['status'] = 'invalid'
                    part['validation_error'] = str(exc)
                else:
                    part['status'] = 'ok'
            write_yaml_atomic(root / f'storyboard/parts/{scene_id}.yaml', part)


def enabled(root: Path) -> bool:
    """Enable scene parts for new boards, existing parts, or pre-gate 1-to-1 legacy boards."""
    if (root / 'storyboard/parts').is_dir() or not (root / 'storyboard/storyboard.yaml').is_file():
        return True
    if _can_migrate(root):
        migrate(root)
        return True
    return False


def _lines(root: Path) -> dict:
    script = Script.model_validate(read_yaml(root / 'script/script.yaml'))
    if not script.lines or len({line.id for line in script.lines}) != len(script.lines):
        raise ValueError('Kịch bản cần các dòng có ID duy nhất và không rỗng.')
    # validate_hook_outro aligns scene and script line one-to-one in script order,
    # including the separate clip hook/outro lines. New parts use stable positional IDs.
    return {f'S{index:02}': line for index, line in enumerate(script.lines, 1)}


def script_hashes(artifact_root: Path) -> dict[str, str]:
    return {scene_id: canonical_json_hash([line.model_dump(mode='json')])
            for scene_id, line in _lines(artifact_root).items()}


def _scene(data: dict) -> dict:
    return {key: value for key, value in data.items() if key not in PART_FIELDS}


def part_details(artifact_root: Path) -> dict[str, tuple[str, str]]:
    result = {}
    hashes = script_hashes(artifact_root)
    for scene_id, line in _lines(artifact_root).items():
        path = artifact_root / f'storyboard/parts/{scene_id}.yaml'
        if not path.is_file():
            result[scene_id] = ('missing', 'chưa lưu cảnh')
            continue
        try:
            data = read_yaml(path)
            if data.get('script_sha256') != hashes[scene_id]:
                raise ValueError('script_sha256 thiếu hoặc dòng kịch bản đã đổi')
            if data.get('status') == 'needs_asset':
                if not str(data.get('missing') or '').strip():
                    raise ValueError('needs_asset cần missing mô tả hình cần')
                result[scene_id] = ('needs_asset', str(data['missing']))
                continue
            if data.get('status', 'ok') != 'ok' or data.get('validation_error'):
                raise ValueError(data.get('validation_error') or 'cảnh cần sửa')
            scene = Scene.model_validate(_scene(data))
            if scene.id != scene_id or scene.script_line_id != line.id or scene.narration != line.text:
                raise ValueError('id/script_line_id/narration không khớp dòng kịch bản')
            if scene.claim_id != line.claim_id or scene.clip_only != line.clip_id:
                raise ValueError('claim_id/clip_only không khớp dòng kịch bản')
            result[scene_id] = ('ok', '')
        except (OSError, ValueError, TypeError, AttributeError, yaml.YAMLError) as exc:
            result[scene_id] = ('invalid', str(exc))
    return result


def part_status(artifact_root: Path) -> dict[str, str]:
    return {scene_id: status for scene_id, (status, _) in part_details(artifact_root).items()}


def apply_rework(root: Path) -> None:
    """Invalidate only named scenes, once per review request."""
    plan_path = root / 'reviews/storyboard-rework.yaml'
    if not plan_path.is_file():
        return
    plan = read_yaml(plan_path)
    if plan.get('script_sha256') != canonical_json_hash(read_yaml(root / 'script/script.yaml')):
        return
    request = canonical_json_hash(plan)
    for scene_id in plan.get('scope', {}).get('storyboard/storyboard.yaml', []):
        if scene_id not in _lines(root):
            continue
        path = root / f'storyboard/parts/{scene_id}.yaml'
        if not path.is_file():
            continue
        data = read_yaml(path)
        if data.get('rework_request') != request:
            data.update(status='invalid', validation_error=plan.get('problem', 'Cần sửa theo kiểm duyệt'),
                        rework_request=request)
            write_yaml_atomic(path, data)


def prompt_context(root: Path) -> str:
    apply_rework(root)
    details = part_details(root)
    hashes = script_hashes(root)
    lines = _lines(root)
    pending = {scene_id: {'status': status, 'reason': reason, 'script_line_id': lines[scene_id].id,
                          'script_sha256': hashes[scene_id]}
               for scene_id, (status, reason) in details.items() if status != 'ok'}
    locked = [scene_id for scene_id, (status, _) in details.items() if status == 'ok']
    error_path = root / 'storyboard/parts-validation.yaml'
    return ('## Phân cảnh từng phần\n'
            'Hợp đồng riêng của lượt này thay thế yêu cầu ghi storyboard cuối và chạy submit bên trên. '
            'Code preflight đã kiểm đầu vào; không kiểm lại provenance catalog đã có.\n'
            'Chỉ làm các cảnh chưa đạt dưới đây. Cảnh đã khoá, không sửa: ' + ', '.join(locked)
            + '\nGhi ngay từng cảnh vào storyboard/parts/<scene_id>.yaml: các trường Scene cùng '
            'script_sha256 được cấp; status: ok khi xong, bỏ validation_error/missing đã giải quyết. '
            'Thiếu hình: status: needs_asset, missing: mô tả cụ thể; lưu rồi tiếp tục cảnh khác. '
            'Giữ rework_request nếu đã có. Không sửa script để khớp hình. '
            'Ghi trường cấp Storyboard (không scenes) vào storyboard/parts-metadata.yaml; '
            'Python ghép và kiểm storyboard cuối. Không gọi lệnh submit storyboard trong chế độ parts.\n'
            + yaml.safe_dump({'pending': pending}, allow_unicode=True, sort_keys=False)
            + ('\nLỗi ghép cần xử lý: ' + str(read_yaml(error_path)) if error_path.is_file() else ''))


def _validation_error(root: Path) -> str | None:
    from healthvideo.workflows.storyboard_design import storyboard_validation_error

    return storyboard_validation_error(root.parents[1])


def assemble(artifact_root: Path) -> list[str]:
    """Promote only a fully validated board; retain successful parts on any failure."""
    with revision_lock(artifact_root):
        return _assemble(artifact_root)


def _assemble(artifact_root: Path) -> list[str]:
    details = part_details(artifact_root)
    if any(status != 'ok' for status, _ in details.values()):
        return [f'{scene_id}: {status}: {reason}' for scene_id, (status, reason) in details.items()
                if status != 'ok']
    root = artifact_root
    target = root / 'storyboard/storyboard.yaml'
    original = target.read_bytes() if target.is_file() else None
    try:
        metadata_path = root / METADATA
        metadata = (read_yaml(metadata_path) if metadata_path.is_file()
                    else read_yaml(target) if target.is_file()
                    else {'title': read_yaml(root / 'script/script.yaml')['title']})
        data = dict(metadata)
        data['scenes'] = [_scene(read_yaml(root / f'storyboard/parts/{scene_id}.yaml'))
                          for scene_id in details]
        from healthvideo.workflows.storyboard_design import normalize_outro

        script = Script.model_validate(read_yaml(root / 'script/script.yaml'))
        data = normalize_outro(data, script)
        Storyboard.model_validate(data)
        write_yaml_atomic(target, data)
        error = _validation_error(root)
        if error:
            raise ValueError(error)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        if original is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(original)
        error = str(exc)
        affected = {scene_id for scene_id in details
                    if re.search(r'(?<!\w)' + re.escape(scene_id) + r'(?!\w)', error)}
        if isinstance(exc, ValidationError):
            for issue in exc.errors():
                loc = issue['loc']
                if len(loc) > 1 and loc[0] == 'scenes' and isinstance(loc[1], int):
                    affected.add(list(details)[loc[1]])
        for scene_id in affected:
            path = root / f'storyboard/parts/{scene_id}.yaml'
            part = read_yaml(path)
            part.update(status='invalid', validation_error=error)
            write_yaml_atomic(path, part)
        # Unlocalized errors belong to metadata/shared inputs; never unlock all scenes.
        write_yaml_atomic(root / 'storyboard/parts-validation.yaml', {'error': error})
        return [error]
    (root / 'storyboard/parts-validation.yaml').unlink(missing_ok=True)
    return []
