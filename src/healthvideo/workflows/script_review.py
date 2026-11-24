"""Bounded script review: a critic agent scores, Python decides rewrite or submit."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from healthvideo.storage.files import (
    canonical_json_hash,
    read_agent_yaml,
    read_yaml,
    write_yaml_atomic,
)
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.workflows import doctor_questions, review_budget, scoped_review
from healthvideo.workflows.decision_card import (
    MAX_DECISIONS,
    Decision,
    validate_decisions,
)

REPORT = 'reviews/script-review.yaml'
LOG = 'reviews/script-review-log.yaml'
PASS_SCORE = 7
MAX_REVIEWS = 2
MAX_CYCLES = 3
CYCLE_LIMIT_REASON = f'Trạm 07 chưa đạt sau {MAX_CYCLES} chu kỳ'
CRITERIA: dict[str, str] = {
    'giong_nguoi_that': 'Giọng người thật, không lộ ngôn ngữ rào đón nguồn',
    'nhip_cau': 'Nhịp câu đa dạng, không lặp khuôn rào đón',
    'khong_lap_y': 'Không lặp ý, phần cơ chế gọn',
    'hinh_anh': 'Hình ảnh so sánh đời thường dễ hiểu',
    'ca_tinh': 'Có cá tính, châm biếm đúng đối tượng',
    'dung_yeu_cau': 'Bám câu hỏi, ghi chú bác sĩ và đúng nghĩa claim',
}
ScriptAction = Literal['script_review', 'draft', 'submit_medical', 'wait_doctor']
class ScriptIssue(BaseModel):
    model_config = ConfigDict(extra='forbid')

    line: str
    criterion: str
    problem: str = Field(min_length=1)
    fix: str = Field(min_length=1)
    issue_id: str = ''
    blocking_safety: bool = False
    related_lines: list[str] = Field(default_factory=list)


class ResolvedScriptIssue(BaseModel):
    model_config = ConfigDict(extra='forbid')

    line: str
    criterion: str


class ScriptReviewReport(BaseModel):
    model_config = ConfigDict(extra='forbid')

    scores: dict[str, int]
    summary: str = Field(min_length=1)
    issues: list[ScriptIssue] = Field(default_factory=list)
    dropped_issues: list[dict] = Field(default_factory=list)
    resolved_issues: list[ResolvedScriptIssue] = Field(default_factory=list)
    checked: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    issue_statuses: dict[str, Literal['resolved', 'still_open']] = Field(default_factory=dict)
    overall: str = ''

    _normalize_issue_statuses = field_validator('issue_statuses', mode='before')(
        scoped_review.normalize_issue_statuses
    )


def _root(project: Path) -> Path:
    return resolve_project_layout(project).artifact_root


def script_path(project: Path) -> Path:
    return _root(project) / 'script/script.yaml'


def script_hash(project: Path) -> str:
    return canonical_json_hash(read_yaml(script_path(project)))


def _rounds(root: Path) -> list[dict]:
    path = root / LOG
    return list(read_yaml(path).get('rounds', [])) if path.is_file() else []


def _log(root: Path) -> dict:
    path = root / LOG
    return read_yaml(path) if path.is_file() else {}


def _cycle(root: Path) -> list[dict]:
    log = _log(root)
    start = max(int(log.get('submitted', 0)), int(log.get('cycle_start', 0)))
    return list(log.get('rounds', []))[start:]


def reset_for_doctor_guidance(
    project: Path,
    request_id: str,
    *,
    require_script_rewrite: bool = True,
) -> None:
    """A new confirmed chat request grants three fresh cycles, once per request."""
    root = _root(project)
    log = _log(root)
    if log.get('doctor_guidance_id') == request_id:
        if not require_script_rewrite and 'rewrite_pending_hash' in log:
            updated = dict(log)
            updated.pop('rewrite_pending_hash', None)
            write_yaml_atomic(root / LOG, updated)
        return
    count = len(log.get('rounds', []))
    baseline = (dict(log['rounds'][-1]) if count else None)
    if baseline:
        baseline['issues'] = [scoped_review.identify(item, 'line') for item in baseline['issues']]
        baseline['snapshot'] = {'script/script.yaml': script_path(project).read_bytes().decode('utf-8')}
    updated = {
        **log, 'version': 1, 'cycles': 1, 'cycle_start': count,
        'guidance_start': count, 'doctor_guidance_id': request_id,
        'guidance_baseline': baseline,
    }
    if require_script_rewrite:
        updated['rewrite_pending_hash'] = script_hash(project)
    else:
        updated.pop('rewrite_pending_hash', None)
    write_yaml_atomic(root / LOG, updated)


def in_rewrite_loop(project: Path) -> bool:
    """Defer visual/voice work after rejection, across automatic cycle boundaries."""
    log = _log(_root(project))
    start = max(int(log.get('submitted', 0)), int(log.get('guidance_start', 0)))
    return any(not row['passed'] for row in log.get('rounds', [])[start:])


def mark_submitted(artifact_root: Path) -> None:
    """Keep history visible while resetting the critic budget for the next submission."""
    rounds = _rounds(artifact_root)
    write_yaml_atomic(artifact_root / LOG,
                      {'version': 1, 'rounds': rounds, 'submitted': len(rounds)})
    from healthvideo.workflows.rework import PLAN

    (artifact_root / PLAN).unlink(missing_ok=True)


def next_script_action(
    project: Path,
    *,
    root: Path | None = None,
    create_question: bool = True,
) -> ScriptAction:
    """Choose the next step for a draft_ready script from the recorded rounds."""
    artifact_root = _root(project)
    review_budget.recover_results(artifact_root)
    log = _log(artifact_root)
    current = script_hash(project)
    if review_budget.enabled(artifact_root):
        all_rounds = _rounds(artifact_root)
        if not (all_rounds and all_rounds[-1].get('passed')
                and all_rounds[-1].get('script_sha256') == current):
            review_budget.require_available(artifact_root, 'script')
    active = _rounds(artifact_root)[max(int(log.get('submitted', 0)),
                                        int(log.get('guidance_start', 0))):]
    stuck = scoped_review.stuck(active)
    if stuck and not active[-1]['passed']:
        if create_question:
            stuck_issues = [
                item for item in active[-1].get('issues', [])
                if item.get('issue_id') in stuck
            ] or list(active[-1].get('issues', []))
            context = [
                {
                    'code': str(item.get('issue_id') or ''),
                    'location': str(item.get('line') or ''),
                    'summary': (
                        f"{CRITERIA.get(item.get('criterion', ''), item.get('criterion', ''))}: "
                        f"{item.get('problem', '')}"
                    ).strip()[:200],
                }
                for item in stuck_issues
            ]
            options = [
                {
                    'id': 'rewrite_stuck_lines',
                    'label': 'Viết lại các dòng bị nêu',
                    'detail': 'Giao Biên kịch sửa trực tiếp các dòng kẹt theo góp ý của bác sĩ.',
                },
                {
                    'id': 'keep_style_and_recheck',
                    'label': 'Giữ cách diễn đạt hiện tại, chỉnh nhẹ mạch nối',
                    'detail': 'Giữ ý chính của các dòng bị nêu, chỉ chỉnh nhẹ ngữ điệu và câu chuyển.',
                },
            ]
            factory_root = root if root is not None else project.resolve().parents[1]
            doctor_questions.ask(
                factory_root,
                project.name,
                station='07',
                kind='stuck_issue',
                question=(
                    f'Trạm 07 kẹt cùng issue qua 2 vòng chấm kịch bản ({len(active)} vòng); '
                    'bác sĩ chọn hướng xử lý cho Biên kịch.'
                ),
                context=context,
                options=options,
                allow_free_text=True,
            )
        return 'wait_doctor'
    if log.get('rewrite_pending_hash') == current:
        return 'draft'
    rounds = _cycle(artifact_root)
    if rounds and not rounds[-1]['passed'] and len(rounds) >= MAX_REVIEWS:
        cycles = int(log.get('cycles', 1))
        if cycles < MAX_CYCLES:
            rewritten = current != rounds[-1]['script_sha256']
            updated = {
                **log, 'cycles': cycles + 1, 'cycle_start': len(log['rounds']),
            }
            if rewritten:
                updated.pop('rewrite_pending_hash', None)
            else:
                updated['rewrite_pending_hash'] = current
            write_yaml_atomic(artifact_root / LOG, updated)
            return 'script_review' if rewritten else 'draft'
        stuck = ', '.join(f'{CRITERIA[key]} ({score}/10)'
                          for key, score in rounds[-1]['scores'].items() if score < PASS_SCORE)
        if not stuck:
            stuck = 'còn quá 5 điểm khó cần bác sĩ quyết định'
        start = max(int(log.get('submitted', 0)), int(log.get('guidance_start', 0)))
        total = len(log['rounds']) - start
        raise ValueError(f'{CYCLE_LIMIT_REASON} ({total} vòng); tiêu chí kẹt: {stuck}. '
                         'Bác sĩ gửi hướng dẫn cho Biên kịch qua chat để mở chu kỳ mới.')
    if not rounds or rounds[-1]['script_sha256'] != current:
        return 'script_review'
    if rounds[-1]['passed']:
        require_passed_review(project)
        return 'submit_medical'
    return 'draft'


def require_passed_review(project: Path) -> None:
    review_budget.recover_results(_root(project))
    rounds = _rounds(_root(project))
    if not rounds:
        raise ValueError('Trạm 07 chưa có kết quả kiểm duyệt kịch bản.')
    latest = rounds[-1]
    if latest.get('script_sha256') != script_hash(project):
        raise ValueError('Trạm 07 cần kiểm duyệt lại kịch bản hiện hành.')
    report = ScriptReviewReport.model_validate({
        key: latest[key] for key in ScriptReviewReport.model_fields if key in latest
    })
    script = read_yaml(script_path(project))
    _validated(report, {str(line.get('id')) for line in script.get('lines', [])})
    if (latest.get('passed') is not True
            or any(score < PASS_SCORE for score in report.scores.values())
            or len(report.decisions) > MAX_DECISIONS
            or any(i.blocking_safety for i in report.issues)):
        raise ValueError('Trạm 07 chưa đạt; chưa được nộp bác sĩ duyệt y khoa.')


def _validated(report: ScriptReviewReport, line_ids: set[str]) -> None:
    validate_decisions(report.decisions, line_ids)
    if set(report.scores) != set(CRITERIA):
        raise ValueError('Báo cáo chấm kịch bản phải có đủ đúng các tiêu chí.')
    if any(not 1 <= score <= 10 for score in report.scores.values()):
        raise ValueError('Điểm chấm kịch bản phải từ 1 đến 10.')
    for issue in report.issues:
        if issue.criterion not in CRITERIA:
            raise ValueError(f'Tiêu chí không tồn tại: {issue.criterion}')
        if issue.line not in line_ids:
            raise ValueError(f'Dòng không có trong kịch bản: {issue.line}')
        if not set(issue.related_lines).issubset(line_ids):
            raise ValueError('Related lines must identify real script lines')
    open_keys = {(issue.line, issue.criterion) for issue in report.issues}
    for issue in report.resolved_issues:
        if issue.line not in line_ids or issue.criterion not in CRITERIA:
            raise ValueError('Lỗi đã sửa phải trỏ tới dòng và tiêu chí có thật.')
        if (issue.line, issue.criterion) in open_keys:
            raise ValueError('Một lỗi không thể vừa còn mở vừa đã sửa.')
    covered = {issue.criterion for issue in report.issues}
    missing = [key for key, score in report.scores.items()
               if score < PASS_SCORE and key not in covered]
    if missing:
        raise ValueError('Tiêu chí chưa đạt thiếu chỗ cần sửa: ' + ', '.join(missing))


@review_budget.serialized_record
def record_review(project: Path, reviewed_hash: str, *, event_id: str | None = None) -> dict:
    """Validate the critic's report, append it to the log and consume the report."""
    root = _root(project)
    current = script_hash(project)
    if current != reviewed_hash:
        raise ValueError('Agent chấm điểm không được sửa kịch bản.')
    budget_event = None
    if review_budget.enabled(root):
        recorded = review_budget.recorded_result(root, 'script', event_id)
        if recorded is not None:
            return recorded
        budget_event = review_budget.report_event(
            root, 'script', root / REPORT, event_id=event_id)
    report_file = root / REPORT
    if not report_file.is_file():
        raise ValueError('Agent chấm điểm chưa ghi báo cáo (thiếu reviews/script-review.yaml).')
    try:
        report = ScriptReviewReport.model_validate(read_agent_yaml(report_file))
    except yaml.YAMLError as exc:
        raise ValueError(f'Báo cáo chấm kịch bản sai YAML: {exc}') from exc
    script = read_yaml(script_path(project))
    line_ids = {str(line.get('id')) for line in script.get('lines', [])}
    for issue in report.issues:
        if issue.line not in line_ids or not set(issue.related_lines).issubset(line_ids):
            raise ValueError(f'Dòng không có trong kịch bản: {issue.line}; related_lines={issue.related_lines}')
    rounds = _rounds(root)
    log = _log(root)
    start = max(int(log.get('submitted', 0)), int(log.get('guidance_start', 0)))
    previous = (rounds[-1] if len(rounds) > start and rounds[-1].get('snapshot')
                and not rounds[-1]['passed'] else None)
    if previous is None:
        previous = medical_baseline(project) or log.get('guidance_baseline')
    if previous:
        allowed = {line for item in previous['issues']
                   for line in [item['line'], *item.get('related_lines', [])]}
        scoped_review.check_script(previous['snapshot']['script/script.yaml'].encode('utf-8'),
                                   script_path(project).read_bytes(), allowed)
    report = ScriptReviewReport.model_validate(scoped_review.reconcile(
        previous, report.model_dump(mode='json'), 'line'))
    _validated(report, {str(line.get('id')) for line in script.get('lines', [])})
    entry = {
        'round': len(rounds) + 1,
        'script_sha256': current,
        'passed': (all(score >= PASS_SCORE for score in report.scores.values())
                   and len(report.decisions) <= MAX_DECISIONS
                   and not any(i.blocking_safety for i in report.issues)),
        **report.model_dump(mode='json'),
        'snapshot': {'script/script.yaml': script_path(project).read_bytes().decode('utf-8')},
    }
    if budget_event:
        entry['budget_event_id'] = budget_event
        review_budget.record_evidence(root, 'script', budget_event, entry, result=True)
    log = read_yaml(root / LOG) if (root / LOG).is_file() else {}
    log.pop('rewrite_pending_hash', None)
    write_yaml_atomic(root / LOG, {**log, 'version': 1, 'rounds': [*rounds, entry],
                                 'cycles': int(log.get('cycles', 1)),
                                 'submitted': int(log.get('submitted', 0))})
    report_file.unlink()
    return entry


def revision_notes(project: Path) -> str:
    """Merge open issues from three recent reports; explicit resolutions remove them."""
    rounds = _rounds(_root(project))
    if not rounds:
        return ''
    latest = rounds[-1]
    if latest.get('snapshot'):
        return incremental_context(project, writer=True)
    recent = rounds[-3:]
    issues = {}
    for row in recent:
        for item in row.get('resolved_issues', []):
            issues.pop((item['line'], item['criterion']), None)
        for item in row['issues']:
            issues[item['line'], item['criterion']] = item
    rows = [f"- {item['line']} ({CRITERIA[item['criterion']]}): {item['problem']} "
            f"Hướng sửa: {item['fix']}" for item in issues.values()]
    trends = [f"- {label}: " + ' → '.join(str(row['scores'][key]) for row in recent)
              for key, label in CRITERIA.items()]
    if len(latest.get('decisions', [])) > MAX_DECISIONS:
        rows.append('Còn quá 5 điểm khó: tự xử lý các lỗi thuộc thẩm quyền; '
                    'không tự quyết điểm cần bác sĩ. Xếp điểm nặng nhất trước.')
    return '\n'.join([f"Biên tập viên chấm lần {latest['round']}: {latest['summary']}",
                      'Lỗi còn mở (tối đa 3 vòng gần nhất, vòng mới nhất thắng):', *rows,
                      'Xu hướng điểm (cũ → mới):', *trends,
                      ('Chỉ sửa các dòng trong danh sách lỗi và dòng kề cần nối ý; '
                       'giữ nguyên id dòng; không thêm dòng mới lặp lại ý đã có ở dòng khác; '
                       'không viết lại toàn bài.')])


def previous_review_notes(project: Path) -> str:
    """Give Critic exact previous issue identities for comparison, including old logs."""
    rounds = _rounds(_root(project))
    if not rounds:
        return ''
    latest = rounds[-1]
    return 'Issues của vòng trước (đối chiếu với bản hiện hành):\n' + yaml.safe_dump(
        latest.get('issues', []), allow_unicode=True, sort_keys=False)


def incremental_context(project: Path, *, writer: bool = False) -> str:
    root = _root(project)
    log = _log(root)
    rounds = log.get('rounds', [])
    start = max(int(log.get('submitted', 0)), int(log.get('guidance_start', 0)))
    latest = (rounds[-1] if len(rounds) > start and not rounds[-1]['passed']
              else medical_baseline(project) or log.get('guidance_baseline'))
    if latest is None:
        return ''
    if not latest.get('snapshot'):
        return ''  # Old logs have no trustworthy baseline; take one full review first.
    before = latest['snapshot']
    current = {'script/script.yaml': script_path(project).read_bytes().decode('utf-8')}
    issues = latest['issues']
    if writer:
        script = read_yaml(script_path(project))
        allowed = {line for item in issues for line in [item['line'], *item.get('related_lines', [])]}
        fragments = [line for line in script['lines'] if line['id'] in allowed]
        return ('Open issues:\n' + yaml.safe_dump(issues, allow_unicode=True)
                + '\nEditable lines only:\n' + yaml.safe_dump(fragments, allow_unicode=True))
    return (scoped_review.packet(issues, before, current)
            + '\nĐiểm và điểm khó đã ghi (chỉ đọc):\n' + yaml.safe_dump(
                {'scores': latest['scores'], 'decisions': latest.get('decisions', [])}, allow_unicode=True))


def ensure_repair_baseline(project: Path) -> None:
    """Upgrade a legacy rejected report only while its reviewed script is still present."""
    root = _root(project)
    log = _log(root)
    rounds = log.get('rounds', [])
    start = max(int(log.get('submitted', 0)), int(log.get('guidance_start', 0)))
    if len(rounds) <= start:
        return
    latest = rounds[-1]
    if (latest['passed'] or latest.get('snapshot')
            or latest['script_sha256'] != script_hash(project)):
        return
    latest['issues'] = [scoped_review.identify(item, 'line') for item in latest['issues']]
    latest['issue_statuses'] = dict.fromkeys((item['issue_id'] for item in latest['issues']), 'still_open')
    latest['snapshot'] = {'script/script.yaml': script_path(project).read_bytes().decode('utf-8')}
    write_yaml_atomic(root / LOG, log)


def medical_baseline(project: Path) -> dict | None:
    from healthvideo.workflows.rework import PLAN

    path = _root(project) / PLAN
    rounds = _rounds(_root(project))
    if not path.is_file() or not rounds:
        return None
    plan = read_yaml(path)
    return {**rounds[-1], 'snapshot': {'script/script.yaml': plan['snapshot']['script/script.yaml']},
            'issues': plan['issues'], 'issue_statuses': {}}


def check_rewrite(project: Path, before: bytes, after: bytes) -> None:
    log = _log(_root(project))
    rounds = log.get('rounds', [])
    start = max(int(log.get('submitted', 0)), int(log.get('guidance_start', 0)))
    latest = rounds[-1] if len(rounds) > start else log.get('guidance_baseline')
    if not latest or latest['passed']:
        return
    allowed = {line for item in latest['issues']
               for line in [item['line'], *item.get('related_lines', [])]}
    scoped_review.check_script(before, after, allowed)


def review_view(root: Path) -> dict | None:
    """Latest score in display form for the app and the medical packet."""
    rounds = _rounds(root)
    if not rounds:
        return None
    latest = rounds[-1]
    return {
        'round': latest['round'],
        'passed': latest['passed'],
        'summary': latest.get('overall') or latest['summary'],
        'scores': [{'label': label, 'score': latest['scores'][key]}
                   for key, label in CRITERIA.items()],
        'issues': [{**item, 'criterion': CRITERIA[item['criterion']]}
                   for item in latest['issues']],
        'pass_score': PASS_SCORE,
    }
