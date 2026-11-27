"""Locate doctor's requested repairs without granting agents a whole-document rewrite."""

import re
from pathlib import Path

import yaml

from healthvideo.storage.files import canonical_json_hash, read_yaml, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.workflows import scoped_review

PLAN = 'reviews/scoped-medical-rework.yaml'
COLLECTIONS = {'script/script.yaml': 'lines', 'storyboard/storyboard.yaml': 'scenes',
               'script/outline.yaml': 'chapters', 'script/clip-plan.yaml': 'clips',
               'assets/asset-manifest.yaml': 'assets'}
STORYBOARD_PLAN = 'reviews/storyboard-rework.yaml'


def _storyboard_plan(root: Path) -> dict:
    path = root / STORYBOARD_PLAN
    if not path.is_file():
        return {}
    plan = read_yaml(path)
    if plan.get('script_sha256') != canonical_json_hash(read_yaml(root / 'script/script.yaml')):
        path.unlink()
        return {}
    return plan


def _locate_storyboard_scenes(root: Path, board_raw: str, error_text: str) -> list[str]:
    try:
        board_data = yaml.safe_load(board_raw)
    except yaml.YAMLError:
        return []
    if not isinstance(board_data, dict) or not isinstance(board_data.get('scenes'), list):
        return []
    script_path = root / 'script/script.yaml'
    if not script_path.is_file():
        return []
    try:
        script_data = read_yaml(script_path)
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return []
    if not isinstance(script_data, dict) or not isinstance(script_data.get('lines'), list):
        return []
    lines = [line for line in script_data['lines'] if isinstance(line, dict)]
    scenes = [scene for scene in board_data['scenes'] if isinstance(scene, dict)]

    found: list[str] = []
    for line, scene in zip(lines, scenes):
        if scene.get('script_line_id') != line.get('id') or scene.get('narration') != line.get('text'):
            scene_id = str(scene.get('id') or '')
            if scene_id and scene_id not in found:
                found.append(scene_id)

    line_to_scenes: dict[str, list[str]] = {}
    for scene in scenes:
        scene_id = str(scene.get('id') or '')
        line_id = str(scene.get('script_line_id') or '')
        if scene_id and line_id:
            line_to_scenes.setdefault(line_id, []).append(scene_id)
    for line, scene in zip(lines, scenes):
        scene_id = str(scene.get('id') or '')
        line_id = str(line.get('id') or '')
        if scene_id and line_id and scene_id not in line_to_scenes.get(line_id, []):
            line_to_scenes.setdefault(line_id, []).append(scene_id)

    mentioned: list[str] = []
    for token in re.findall(r'(?<!\w)N\d+(?!\w)', error_text):
        if token not in mentioned:
            mentioned.append(token)
    for line in lines:
        line_id = str(line.get('id') or '')
        if (
            line_id
            and line_id not in mentioned
            and re.search(r'(?<!\w)' + re.escape(line_id) + r'(?!\w)', error_text)
        ):
            mentioned.append(line_id)
    for line_id in mentioned:
        for scene_id in line_to_scenes.get(line_id, []):
            if scene_id not in found:
                found.append(scene_id)
    return found


def storyboard_failure(project: Path, files: dict[str, Path], error: ValueError) -> None:
    root = resolve_project_layout(project).artifact_root
    path = root / STORYBOARD_PLAN
    previous = _storyboard_plan(root)
    snapshot, scope = {}, {}
    for relative, file in files.items():
        if file is None or not file.is_file():
            continue
        raw = file.read_bytes().decode('utf-8')
        snapshot[relative] = raw
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError:
            data = None
        items = data.get(COLLECTIONS[relative], []) if isinstance(data, dict) else []
        identities = [str(item.get('id') or item.get('path', '')) for item in items]
        scope[relative] = [identity for identity in identities if identity and identity in str(error)]
    if 'storyboard/storyboard.yaml' in scope and not scope['storyboard/storyboard.yaml']:
        scope['storyboard/storyboard.yaml'] = _locate_storyboard_scenes(
            root, snapshot['storyboard/storyboard.yaml'], str(error)
        )
    criterion = re.sub(r'\d+(?:\.\d+)?', '#', str(error))
    issue_id = 'storyboard-' + canonical_json_hash({'scope': scope, 'criterion': criterion})[:16]
    same_issue = previous.get('issue_id') == issue_id and previous.get('scope') == scope
    write_yaml_atomic(path, {'issue_id': issue_id, 'problem': str(error),
                            'scope': scope, 'snapshot': snapshot,
                            'script_sha256': canonical_json_hash(read_yaml(root / 'script/script.yaml')),
                            'still_open_rounds': (int(previous.get('still_open_rounds', 0)) + 1
                                                  if same_issue else 1)})


def check_storyboard(project: Path, files: dict[str, Path], *, plan: dict | None = None) -> None:
    root = resolve_project_layout(project).artifact_root
    plan = _storyboard_plan(root) if plan is None else plan
    if not plan:
        return
    if plan['still_open_rounds'] >= 2:
        raise ValueError('Storyboard cần hướng dẫn: cùng issue kẹt hai vòng; chờ bác sĩ hướng dẫn.')
    for relative, before in plan['snapshot'].items():
        file = files.get(relative)
        if file is None:
            raise ValueError('Repair scope violation: omitted storyboard input')
        scoped_review.check_nodes(before.encode('utf-8'), file.read_bytes(),
                                  set(plan['scope'][relative]), COLLECTIONS[relative])


def storyboard_context(project: Path) -> str:
    root = resolve_project_layout(project).artifact_root
    plan = _storyboard_plan(root)
    if not plan:
        return ''
    if plan['still_open_rounds'] >= 2 or not any(plan['scope'].values()):
        raise ValueError('Storyboard cần hướng dẫn: lỗi lặp hai vòng hoặc chưa xác định vị trí; '
                         'cần bác sĩ chỉ rõ hướng sửa. ' + plan['problem'])
    fragments = {}
    for relative, before in plan['snapshot'].items():
        data = yaml.safe_load(before)
        fragments[relative] = [item for item in data[COLLECTIONS[relative]]
                               if str(item.get('id') or item.get('path', '')) in plan['scope'][relative]]
    return ('Chỉ sửa issue mở, giữ nguyên từng chữ ngoài phạm vi.\n'
            + yaml.safe_dump({'issue_id': plan['issue_id'], 'problem': plan['problem'],
                              'fragments': fragments}, allow_unicode=True))


_RANGE = re.compile(r'(?<![\w])([A-Z]+)(\d+)\s*[–-]\s*(?:\1)?(\d+)(?![\w])')


def _in_range(identity: str, note: str) -> bool:
    """An explicit range such as N01–N53 names every ID inside it (still explicit scope)."""
    match = re.fullmatch(r'([A-Z]+)(\d+)', identity)
    return bool(match) and any(
        prefix == match[1] and int(low) <= int(match[2]) <= int(high)
        for prefix, low, high in _RANGE.findall(note))


def prepare(project: Path, note: str) -> dict:
    root = resolve_project_layout(project).artifact_root
    path = root / PLAN
    request = canonical_json_hash({'note': note})
    if path.is_file() and read_yaml(path).get('request') == request:
        return read_yaml(path)
    scope = {}
    snapshot = {}
    for relative, collection in COLLECTIONS.items():
        file = root / relative
        if not file.is_file():
            continue
        snapshot[relative] = file.read_bytes().decode('utf-8')
        items = read_yaml(file).get(collection, [])
        identities = [str(item.get('id') or item.get('path', '')) for item in items]
        scope[relative] = [identity for identity in identities if identity and (re.search(
            r'(?<![\w])' + re.escape(identity) + r'(?![\w])', note) or _in_range(identity, note))]
    issues = [{'issue_id': 'medical-' + request[:12] + '-' + identity,
               'line': identity, 'criterion': 'dung_yeu_cau', 'problem': note,
               'fix': 'Sửa đúng góp ý bác sĩ; giữ nguyên mọi phần khác.'}
              for identity in dict.fromkeys(scope.get('script/script.yaml', []))]
    plan = {'request': request, 'scope': scope, 'snapshot': snapshot, 'issues': issues,
            'note': note}
    write_yaml_atomic(path, plan)
    return plan


def context(project: Path, note: str) -> str:
    plan = prepare(project, note)
    if not any(plan['scope'].values()):
        raise ValueError('Góp ý y khoa chưa có vị trí: cần bác sĩ chỉ rõ ID dòng/cảnh cần sửa.')
    fragments = {}
    for relative, identities in plan['scope'].items():
        if identities:
            data = yaml.safe_load(plan['snapshot'][relative])
            fragments[relative] = [item for item in data[COLLECTIONS[relative]]
                                   if str(item.get('id') or item.get('path', '')) in identities]
    return ('Góp ý bác sĩ (chỉ sửa các ID được nêu rõ):\n' + plan['note']
            + '\nIssue và đoạn liên quan:\n' + yaml.safe_dump(
                {'issues': plan['issues'], 'fragments': fragments}, allow_unicode=True)
            + '\nGiữ nguyên từng chữ ngoài các ID trên. Nếu thiếu vị trí thì dừng, '
            'báo cần bác sĩ chỉ rõ dòng/cảnh; không tự nhận toàn bài làm phạm vi.')


def check(project: Path) -> None:
    root = resolve_project_layout(project).artifact_root
    plan = read_yaml(root / PLAN)
    for relative, before in plan['snapshot'].items():
        scoped_review.check_nodes(before.encode('utf-8'), (root / relative).read_bytes(),
                                  set(plan['scope'][relative]), COLLECTIONS[relative])
