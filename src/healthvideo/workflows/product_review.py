"""Bounded product review: a critic agent scores the finished video before the doctor sees it.

Production holds a fresh final render at ``production_in_progress`` with a pending marker.
The critic scores it; failing issues the production agent may fix go back for a fix and a
re-render, at most ``MAX_REVIEWS`` times per submission, then Python submits to the doctor.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout

PENDING = 'reviews/product/pending.yaml'
REPORT = 'reviews/product-review.yaml'
LOG = 'reviews/product-review-log.yaml'
RENDER_MANIFEST = 'renders/render-manifest.json'
PASS_SCORE = 7
MAX_REVIEWS = 3  # one first look plus two fixes, then the doctor sees the score
CRITERIA: dict[str, str] = {
    'hinh_khop_loi': 'Hình khớp lời đọc từng cảnh, đúng cơ chế',
    'hinh_ro': 'Hình rõ, nhãn tiếng Việt đọc được, không chồng hay cắt chữ',
    'nhip_dung': 'Nhịp dựng nhanh, không giữ một hình quá lâu',
    'am_thanh_phu_de': 'Phụ đề khớp lời, phát âm thuật ngữ đúng, nhạc không lấn giọng',
    'mo_ket': 'Mở đầu cuốn hút, kết rõ ràng có nhận diện kênh',
    'bai_dang': 'Bài đăng đúng nội dung video, không hứa hẹn quá đà',
}
ProductAction = Literal['product_review', 'revise_product', 'submit_video']


class ProductIssue(BaseModel):
    model_config = ConfigDict(extra='forbid')

    at: str = Field(min_length=1)  # scene id, mm:ss, or 'posts'
    criterion: str
    problem: str = Field(min_length=1)
    fix: str = Field(min_length=1)
    fixable: bool  # the production agent may fix it without reopening the medical gate


class ProductReviewReport(BaseModel):
    model_config = ConfigDict(extra='forbid')

    scores: dict[str, int]
    summary: str = Field(min_length=1)
    issues: list[ProductIssue] = Field(default_factory=list)


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
    if len(rounds) >= MAX_REVIEWS:
        return 'submit_video'
    if not rounds or rounds[-1]['render_sha256'] != render_hash(project):
        return 'product_review'
    latest = rounds[-1]
    if latest['passed'] or latest.get('fix_attempted'):
        return 'submit_video'
    if not any(item['fixable'] for item in latest['issues']):
        return 'submit_video'  # only the doctor can reopen what is wrong
    return 'revise_product'


def _validated(report: ProductReviewReport) -> None:
    if set(report.scores) != set(CRITERIA):
        raise ValueError('Báo cáo duyệt sản phẩm phải có đủ đúng các tiêu chí.')
    if any(not 1 <= score <= 10 for score in report.scores.values()):
        raise ValueError('Điểm duyệt sản phẩm phải từ 1 đến 10.')
    for issue in report.issues:
        if issue.criterion not in CRITERIA:
            raise ValueError(f'Tiêu chí không tồn tại: {issue.criterion}')
    covered = {issue.criterion for issue in report.issues}
    missing = [key for key, score in report.scores.items()
               if score < PASS_SCORE and key not in covered]
    if missing:
        raise ValueError('Tiêu chí chưa đạt thiếu chỗ cần sửa: ' + ', '.join(missing))


def record_review(project: Path, reviewed_hash: str) -> dict:
    """Validate the critic's report, append it to the log and consume the report."""
    root = _root(project)
    if render_hash(project) != reviewed_hash:
        raise ValueError('Agent duyệt sản phẩm không được dựng lại hay sửa bản dựng.')
    report_file = root / REPORT
    if not report_file.is_file():
        raise ValueError('Agent duyệt sản phẩm chưa ghi báo cáo.')
    try:
        report = ProductReviewReport.model_validate(read_yaml(report_file))
    except yaml.YAMLError as exc:
        raise ValueError(f'Báo cáo duyệt sản phẩm sai YAML: {exc}') from exc
    _validated(report)
    log = _log(root)
    entry = {
        'round': len(log['rounds']) + 1,
        'render_sha256': reviewed_hash,
        'passed': all(score >= PASS_SCORE for score in report.scores.values()),
        **report.model_dump(mode='json'),
    }
    log['rounds'].append(entry)
    write_yaml_atomic(root / LOG, {'version': 1, **log})
    report_file.unlink()
    return entry


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
    rounds = _cycle(_root(project))
    if not rounds:
        return ''
    latest = rounds[-1]
    rows = [f"- {item['at']} ({CRITERIA[item['criterion']]}): {item['problem']} "
            f"Hướng sửa: {item['fix']}" for item in latest['issues'] if item['fixable']]
    return '\n'.join([f"Người duyệt sản phẩm chấm lần {latest['round']}: {latest['summary']}", *rows])


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
        'summary': latest['summary'],
        'scores': [{'label': label, 'score': latest['scores'][key]}
                   for key, label in CRITERIA.items()],
        'issues': [{**item, 'line': item['at'], 'criterion': CRITERIA[item['criterion']],
                    'fix': item['fix'] + ('' if item['fixable'] else ' (cần bác sĩ mở cổng y khoa)')}
                   for item in latest['issues']],
        'pass_score': PASS_SCORE,
    }
