"""Bounded script review: a critic agent scores, Python decides rewrite or submit."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from healthvideo.storage.files import canonical_json_hash, read_yaml, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout

REPORT = 'reviews/script-review.yaml'
LOG = 'reviews/script-review-log.yaml'
PASS_SCORE = 7
MAX_REVIEWS = 3  # one first read plus two rewrites, then the doctor sees the score
CRITERIA: dict[str, str] = {
    'giong_nguoi_that': 'Giọng người thật, không lộ ngôn ngữ rào đón nguồn',
    'nhip_cau': 'Nhịp câu đa dạng, không lặp khuôn rào đón',
    'khong_lap_y': 'Không lặp ý, phần cơ chế gọn',
    'hinh_anh': 'Hình ảnh so sánh đời thường dễ hiểu',
    'ca_tinh': 'Có cá tính, châm biếm đúng đối tượng',
    'dung_yeu_cau': 'Bám câu hỏi, ghi chú bác sĩ và đúng nghĩa claim',
}
ScriptAction = Literal['script_review', 'draft', 'submit_medical']


class ScriptIssue(BaseModel):
    model_config = ConfigDict(extra='forbid')

    line: str
    criterion: str
    problem: str = Field(min_length=1)
    fix: str = Field(min_length=1)


class ScriptReviewReport(BaseModel):
    model_config = ConfigDict(extra='forbid')

    scores: dict[str, int]
    summary: str = Field(min_length=1)
    issues: list[ScriptIssue] = Field(default_factory=list)


def _root(project: Path) -> Path:
    return resolve_project_layout(project).artifact_root


def script_path(project: Path) -> Path:
    return _root(project) / 'script/script.yaml'


def script_hash(project: Path) -> str:
    return canonical_json_hash(read_yaml(script_path(project)))


def _rounds(root: Path) -> list[dict]:
    path = root / LOG
    return list(read_yaml(path).get('rounds', [])) if path.is_file() else []


def next_script_action(project: Path) -> ScriptAction:
    """Choose the next step for a draft_ready script from the recorded rounds."""
    rounds = _rounds(_root(project))
    if len(rounds) >= MAX_REVIEWS:
        return 'submit_medical'
    if not rounds or rounds[-1]['script_sha256'] != script_hash(project):
        return 'script_review'
    return 'submit_medical' if rounds[-1]['passed'] else 'draft'


def _validated(report: ScriptReviewReport, line_ids: set[str]) -> None:
    if set(report.scores) != set(CRITERIA):
        raise ValueError('Báo cáo chấm kịch bản phải có đủ đúng các tiêu chí.')
    if any(not 1 <= score <= 10 for score in report.scores.values()):
        raise ValueError('Điểm chấm kịch bản phải từ 1 đến 10.')
    for issue in report.issues:
        if issue.criterion not in CRITERIA:
            raise ValueError(f'Tiêu chí không tồn tại: {issue.criterion}')
        if issue.line not in line_ids:
            raise ValueError(f'Dòng không có trong kịch bản: {issue.line}')
    covered = {issue.criterion for issue in report.issues}
    missing = [key for key, score in report.scores.items()
               if score < PASS_SCORE and key not in covered]
    if missing:
        raise ValueError('Tiêu chí chưa đạt thiếu chỗ cần sửa: ' + ', '.join(missing))


def record_review(project: Path, reviewed_hash: str) -> dict:
    """Validate the critic's report, append it to the log and consume the report."""
    root = _root(project)
    current = script_hash(project)
    if current != reviewed_hash:
        raise ValueError('Agent chấm điểm không được sửa kịch bản.')
    report_file = root / REPORT
    if not report_file.is_file():
        raise ValueError('Agent chấm điểm chưa ghi báo cáo.')
    try:
        report = ScriptReviewReport.model_validate(read_yaml(report_file))
    except yaml.YAMLError as exc:
        raise ValueError(f'Báo cáo chấm kịch bản sai YAML: {exc}') from exc
    script = read_yaml(script_path(project))
    _validated(report, {str(line.get('id')) for line in script.get('lines', [])})
    rounds = _rounds(root)
    entry = {
        'round': len(rounds) + 1,
        'script_sha256': current,
        'passed': all(score >= PASS_SCORE for score in report.scores.values()),
        **report.model_dump(mode='json'),
    }
    write_yaml_atomic(root / LOG, {'version': 1, 'rounds': [*rounds, entry]})
    report_file.unlink()
    return entry


def revision_notes(project: Path) -> str:
    """Render the latest critic report as rewrite instructions for the draft agent."""
    rounds = _rounds(_root(project))
    if not rounds:
        return ''
    latest = rounds[-1]
    rows = [f"- {item['line']} ({CRITERIA[item['criterion']]}): {item['problem']} "
            f"Hướng sửa: {item['fix']}" for item in latest['issues']]
    return '\n'.join([f"Biên tập viên chấm lần {latest['round']}: {latest['summary']}", *rows])


def review_view(root: Path) -> dict | None:
    """Latest score in display form for the app and the medical packet."""
    rounds = _rounds(root)
    if not rounds:
        return None
    latest = rounds[-1]
    return {
        'round': latest['round'],
        'passed': latest['passed'],
        'summary': latest['summary'],
        'scores': [{'label': label, 'score': latest['scores'][key]}
                   for key, label in CRITERIA.items()],
        'issues': [{**item, 'criterion': CRITERIA[item['criterion']]}
                   for item in latest['issues']],
        'pass_score': PASS_SCORE,
    }
