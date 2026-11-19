"""Bounded product review: a critic agent scores the finished video before the doctor sees it.

Production holds a fresh final render at ``production_in_progress`` with a pending marker.
The critic scores it; fixable issues return for correction and another review.
Only a passing current review allows submission to the doctor.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.workflows import scoped_review
from healthvideo.workflows.decision_card import (
    MAX_DECISIONS,
    Decision,
    validate_decisions,
)
from healthvideo.workflows.factory_standards import style_a_active

PENDING = 'reviews/product/pending.yaml'
REPORT = 'reviews/product-review.yaml'
LOG = 'reviews/product-review-log.yaml'
RENDER_MANIFEST = 'renders/render-manifest.json'
PASS_SCORE = 7
MAX_REVIEWS = 3  # one first look plus two fixes, then the doctor sees the score
STYLE_CRITERION = 'dung_phong_cach_pyh'
LEGACY_CRITERIA: dict[str, str] = {
    'hinh_khop_loi': 'Hình khớp lời đọc từng cảnh, đúng cơ chế',
    'hinh_ro': 'Hình rõ, nhãn tiếng Việt đọc được, không chồng hay cắt chữ',
    'nhip_dung': 'Nhịp dựng nhanh, không giữ một hình quá lâu',
    'am_thanh_phu_de': 'Phụ đề khớp lời, phát âm thuật ngữ đúng, nhạc không lấn giọng',
    'mo_ket': 'Mở đầu cuốn hút, kết rõ ràng có nhận diện kênh',
    'bai_dang': 'Bài đăng đúng nội dung video, không hứa hẹn quá đà',
}
CRITERIA: dict[str, str] = {
    **LEGACY_CRITERIA,
    STYLE_CRITERION: 'Đúng phong cách PYH (màu, chữ, mascot đúng nghĩa, sơ đồ dựng dần, phụ đề)',
}
ProductAction = Literal['product_review', 'revise_product', 'submit_video']


class ProductIssue(BaseModel):
    model_config = ConfigDict(extra='forbid')

    at: str = Field(min_length=1)  # scene id, mm:ss, or 'posts'
    criterion: str
    problem: str = Field(min_length=1)
    fix: str = Field(min_length=1)
    fixable: bool  # the production agent may fix it without reopening the medical gate
    issue_id: str = ''
    blocking_safety: bool = False
    edits: list[scoped_review.EditScope] = Field(default_factory=list)


class ProductReviewReport(BaseModel):
    model_config = ConfigDict(extra='forbid')

    scores: dict[str, int]
    summary: str = Field(min_length=1)
    issues: list[ProductIssue] = Field(default_factory=list)
    dropped_issues: list[dict] = Field(default_factory=list)
    checked: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    issue_statuses: dict[str, Literal['resolved', 'still_open']] = Field(default_factory=dict)
    overall: str = ''


def _root(project: Path) -> Path:
    return resolve_project_layout(project).artifact_root


def _log(root: Path) -> dict:
    path = root / LOG
    data = read_yaml(path) if path.is_file() else {}
    return {'rounds': list(data.get('rounds', [])), 'submitted': int(data.get('submitted', 0))}


def _cycle(root: Path) -> list[dict]:
    """Rounds since the last submission to the doctor."""
    log = _log(root)
    return log['rounds'][log['submitted']:]


def render_hash(project: Path) -> str:
    return sha256_file(_root(project) / RENDER_MANIFEST)


def pending(project: Path) -> bool:
    try:
        return (_root(project) / PENDING).is_file()
    except (OSError, ValueError):
        return False


def hold(artifact_root: Path, input_hash: str) -> None:
    """Called by production after a final render: wait for the critic, not the doctor."""
    write_yaml_atomic(artifact_root / PENDING, {'version': 1, 'input_hash': input_hash})


def next_product_action(project: Path) -> ProductAction:
    rounds = _cycle(_root(project))
    if scoped_review.stuck(rounds) and not rounds[-1]['passed']:
        raise ValueError('Trạm 12 cần hướng dẫn: cùng issue kẹt 2 vòng; cần bác sĩ quyết định.')
    if not rounds or rounds[-1]['render_sha256'] != render_hash(project):
        return 'product_review'
    latest = rounds[-1]
    if latest['passed']:
        require_passed_review(project)
        return 'submit_video'
    if len(rounds) >= MAX_REVIEWS:
        raise ValueError('Trạm 12 chưa đạt sau các vòng sửa; cần xử lý nhận xét trước khi nộp bác sĩ.')
    if len(latest.get('decisions', [])) > MAX_DECISIONS:
        return 'product_review' if latest.get('fix_attempted') else 'revise_product'
    if latest.get('fix_attempted'):
        return 'product_review'
    if not any(item['fixable'] for item in latest['issues']):
        raise ValueError('Trạm 12 chưa đạt; lỗi vượt phạm vi thợ dựng, cần xử lý trước khi nộp bác sĩ.')
    return 'revise_product'


def criteria_for_revision(root: Path) -> dict[str, str]:
    """Return blocking Station 12 criteria: 7 for Style A revisions, 6 for legacy revisions."""
    return CRITERIA if style_a_active(root) else LEGACY_CRITERIA


def require_passed_review(project: Path) -> None:
    root = _root(project)
    rounds = _log(root)['rounds']
    if not rounds:
        raise ValueError('Trạm 12 chưa có kết quả kiểm định sản phẩm.')
    latest = rounds[-1]
    if latest.get('render_sha256') != render_hash(project):
        raise ValueError('Trạm 12 cần kiểm định lại bản dựng hiện hành.')
    report = ProductReviewReport.model_validate({
        key: latest[key] for key in ProductReviewReport.model_fields if key in latest
    })
    style_required = style_a_active(root)
    _validated(report, allow_legacy=not style_required, style_required=style_required)
    blocking = criteria_for_revision(root)
    if (latest.get('passed') is not True
            or any(report.scores[key] < PASS_SCORE for key in blocking)
            or len(report.decisions) > MAX_DECISIONS):
        raise ValueError('Trạm 12 chưa đạt; chưa được nộp bác sĩ duyệt video.')


def _validated(
    report: ProductReviewReport,
    *,
    allow_legacy: bool = False,
    style_required: bool | None = None,
) -> None:
    if style_required is None:
        style_required = not allow_legacy
    validate_decisions(report.decisions)
    allowed_keys = (set(CRITERIA), set(LEGACY_CRITERIA)) if allow_legacy else (set(CRITERIA),)
    if set(report.scores) not in allowed_keys:
        raise ValueError('Báo cáo duyệt sản phẩm phải có đủ đúng các tiêu chí.')
    if any(not 1 <= score <= 10 for score in report.scores.values()):
        raise ValueError('Điểm duyệt sản phẩm phải từ 1 đến 10.')
    for issue in report.issues:
        if issue.criterion not in CRITERIA:
            raise ValueError(f'Tiêu chí không tồn tại: {issue.criterion}')
    covered = {issue.criterion for issue in report.issues}
    checked_keys = CRITERIA if style_required else LEGACY_CRITERIA
    missing = [key for key in checked_keys
               if report.scores.get(key, PASS_SCORE) < PASS_SCORE and key not in covered]
    if missing:
        raise ValueError('Tiêu chí chưa đạt thiếu chỗ cần sửa: ' + ', '.join(missing))


def record_review(project: Path, reviewed_hash: str) -> dict:
    """Validate the critic's report, append it to the log and consume the report."""
    root = _root(project)
    if render_hash(project) != reviewed_hash:
        raise ValueError('Agent duyệt sản phẩm không được dựng lại hay sửa bản dựng.')
    report_file = root / REPORT
    if not report_file.is_file():
        raise ValueError('Agent duyệt sản phẩm chưa ghi báo cáo (thiếu reviews/product-review.yaml).')
    try:
        report = ProductReviewReport.model_validate(read_yaml(report_file))
    except yaml.YAMLError as exc:
        raise ValueError(f'Báo cáo duyệt sản phẩm sai YAML: {exc}') from exc
    log = _log(root)
    previous = log['rounds'][-1] if len(log['rounds']) > log['submitted'] else None
    report = ProductReviewReport.model_validate(scoped_review.reconcile(
        previous if previous and not previous['passed'] and previous.get('snapshot') is not None else None,
        report.model_dump(mode='json'), 'at'))
    style_required = style_a_active(root)
    _validated(report, allow_legacy=not style_required, style_required=style_required)
    blocking = criteria_for_revision(root)
    entry = {
        'round': len(log['rounds']) + 1,
        'render_sha256': reviewed_hash,
        'passed': (all(report.scores[key] >= PASS_SCORE for key in blocking)
                   and len(report.decisions) <= MAX_DECISIONS),
        **report.model_dump(mode='json'),
        'snapshot': snapshot(project),
    }
    log['rounds'].append(entry)
    write_yaml_atomic(root / LOG, {'version': 1, **log})
    report_file.unlink()
    return entry


def repair_files(project: Path) -> dict[str, bytes]:
    """Capture permitted product sources, plus locked YAML to detect collateral edits."""
    root = _root(project)
    repo = project.parent.parent
    files = {p.relative_to(repo).as_posix(): p.read_bytes()
             for p in (repo / 'video/src/anatomy').rglob('*') if p.is_file()}
    files.update({p.relative_to(repo).as_posix(): p.read_bytes()
                  for directory in ('script', 'storyboard', 'assets', 'evidence', 'explainer', 'posts')
                  for p in (root / directory).rglob('*.yaml')})
    return files


def snapshot(project: Path) -> dict[str, str]:
    files = repair_files(project)
    return {path: raw.decode('utf-8') for path, raw in files.items()}


def incremental_context(project: Path, *, writer: bool = False) -> str:
    rounds = _cycle(_root(project))
    if not rounds or rounds[-1]['passed'] or 'snapshot' not in rounds[-1]:
        return ''
    latest = rounds[-1]
    if writer:
        current = snapshot(project)
        fragments = {}
        for item in latest['issues']:
            for scope in item.get('edits', []):
                path = scope['path']
                fragments[f"{path}:{scope['start_line']}-{scope['end_line']}"] = ''.join(
                    current.get(path, '').splitlines(keepends=True)[scope['start_line']-1:scope['end_line']])
        return ('Open issues:\n' + yaml.safe_dump(latest['issues'], allow_unicode=True)
                + '\nEditable fragments:\n' + yaml.safe_dump(fragments, allow_unicode=True))
    return (scoped_review.packet(latest['issues'], latest['snapshot'], snapshot(project))
            + '\nĐiểm và điểm khó đã ghi (chỉ đọc):\n' + yaml.safe_dump(
                {'scores': latest['scores'], 'decisions': latest.get('decisions', [])}, allow_unicode=True))


def check_repair(project: Path, before: dict[str, bytes]) -> None:
    rounds = _cycle(_root(project))
    if not rounds:
        return
    scopes = [scope for item in rounds[-1]['issues'] if item['fixable']
              for scope in item.get('edits', [])]
    repo = project.parent.parent
    for scope in scopes:
        path = (repo / scope['path']).resolve()
        if not (path.is_relative_to((repo / 'video/src/anatomy').resolve())
                or path == (_root(project) / 'posts/posts.yaml').resolve()):
            raise ValueError('Repair scope violation: product target is locked')
    scoped_review.check_edits(before, repair_files(project), scopes)


def mark_fix_attempted(project: Path) -> None:
    root = _root(project)
    log = _log(root)
    log['rounds'][-1]['fix_attempted'] = True
    write_yaml_atomic(root / LOG, {'version': 1, **log})


def mark_submitted(artifact_root: Path) -> None:
    """A new submission starts a new review cycle; the latest score stays visible."""
    log = _log(artifact_root)
    log['submitted'] = len(log['rounds'])
    write_yaml_atomic(artifact_root / LOG, {'version': 1, **log})
    (artifact_root / PENDING).unlink(missing_ok=True)


def revision_notes(project: Path) -> str:
    """Render the fixable issues of the latest round as instructions for the fixer."""
    root = _root(project)
    rounds = _cycle(root)
    if not rounds:
        return ''
    latest = rounds[-1]
    style_required = style_a_active(root)
    rows = [f"- {item['at']} ({CRITERIA[item['criterion']]}): {item['problem']} "
            f"Hướng sửa: {item['fix']}"
            for item in latest['issues']
            if item['fixable'] and (style_required or item['criterion'] != STYLE_CRITERION)]
    if len(latest.get('decisions', [])) > MAX_DECISIONS:
        rows.append('Còn quá 5 điểm khó: tự xử lý các lỗi thuộc thẩm quyền; '
                    'không tự quyết điểm cần bác sĩ. Xếp điểm nặng nhất trước.')
    return '\n'.join([f"Người duyệt sản phẩm chấm lần {latest['round']}: {latest['summary']}", *rows])


def style_score(root: Path) -> dict | None:
    """Return the latest PYH style score from Station 12 if present."""
    rounds = _log(root)['rounds']
    if not rounds:
        return None
    latest = rounds[-1]
    scores = latest.get('scores') or {}
    if STYLE_CRITERION not in scores:
        return None
    value = int(scores[STYLE_CRITERION])
    return {
        'key': STYLE_CRITERION,
        'label': CRITERIA[STYLE_CRITERION],
        'score': value,
        'pass_score': PASS_SCORE,
        'passed': value >= PASS_SCORE,
        'round': latest.get('round'),
    }


def review_view(root: Path) -> dict | None:
    """Latest score in display form for the app and the video packet."""
    rounds = _log(root)['rounds']
    if not rounds:
        return None
    latest = rounds[-1]
    return {
        'title': 'Người duyệt sản phẩm',
        'round': latest['round'],
        'passed': latest['passed'],
        'summary': latest.get('overall') or latest['summary'],
        'scores': [
            {'key': key, 'label': label, 'score': latest['scores'][key]}
            for key, label in CRITERIA.items()
            if key in latest['scores']
        ],
        'style_score': style_score(root),
        'issues': [{**item, 'line': item['at'], 'criterion': CRITERIA[item['criterion']],
                    'fix': item['fix'] + ('' if item['fixable'] else ' (cần bác sĩ mở cổng y khoa)')}
                   for item in latest['issues']],
        'pass_score': PASS_SCORE,
    }
