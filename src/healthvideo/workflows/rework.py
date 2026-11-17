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
    criterion = re.sub(r'\d+(?:\.\d+)?', '#', str(error))
    issue_id = 'storyboard-' + canonical_json_hash({'scope': scope, 'criterion': criterion})[:16]
    write_yaml_atomic(path, {'issue_id': issue_id, 'problem': str(error),
                            'scope': scope, 'snapshot': snapshot,
                            'script_sha256': canonical_json_hash(read_yaml(root / 'script/script.yaml')),
                            'still_open_rounds': (int(previous.get('still_open_rounds', 0)) + 1
                                                  if previous.get('issue_id') == issue_id else 1)})


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
        scope[relative] = [identity for identity in identities if identity and re.search(
            r'(?<![\w])' + re.escape(identity) + r'(?![\w])', note)]
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
