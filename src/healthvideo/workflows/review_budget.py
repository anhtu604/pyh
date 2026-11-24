"""Revision-local D4 ledger. Submission markers and model choices grant no credit."""

from datetime import UTC, datetime
from functools import wraps
from pathlib import Path

from healthvideo.domain.quality_standards import (
    D4_EXHAUSTED_POLICY,
    D4_PRODUCT_REVIEW_ROUNDS,
    D4_SCRIPT_REVIEW_ROUNDS,
    D4_VISUAL_REVIEW_ROUNDS,
)
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.storage.revision_lock import revision_lock

LEDGER = 'reviews/review-budget.yaml'
LIMITS = {'script': D4_SCRIPT_REVIEW_ROUNDS, 'visual': D4_VISUAL_REVIEW_ROUNDS,
          'product': D4_PRODUCT_REVIEW_ROUNDS}
ROLES = {'script': 'writer', 'visual': 'storyboard_director', 'product': 'editor'}


def enabled(revision: Path) -> bool:
    """Opt in through the revision pin/board; a created ledger keeps the opt-in sticky."""
    if (revision / LEDGER).exists():
        return True
    for relative in ('workflow/standards.yaml', 'storyboard/storyboard.yaml'):
        path = revision / relative
        if path.is_file():
            data = read_yaml(path)
            if (data.get('quality_profile') == 'r5_v1'
                    or data.get('quality_standard', {}).get('profile') == 'r5_v1'):
                return True
    return False


def _limit(stage: str) -> int:
    if stage in LIMITS:
        return LIMITS[stage]
    if stage.startswith('diagnosis:') and stage.removeprefix('diagnosis:').strip():
        return 2
    raise ValueError(f'Unknown review budget stage: {stage}')


def _read(revision: Path) -> dict:
    path = revision / LEDGER
    if not path.exists():
        return {'version': 1, 'stages': {}}
    data = read_yaml(path)
    if (data.get('version') != 1 or not isinstance(data.get('stages'), dict)):
        raise ValueError('Invalid review budget ledger; requires operator investigation')
    for stage, events in data['stages'].items():
        _limit(stage)
        if (not isinstance(events, list) or any(not isinstance(e, dict)
                or not isinstance(e.get('event_id'), str) for e in events)
                or len({e['event_id'] for e in events}) != len(events)):
            raise ValueError('Invalid review budget events')
    return data


def _historical_events(revision: Path, stage: str) -> list[dict]:
    """Import counts without modifying or trusting submitted/cycle offsets."""
    if stage in {'script', 'product'}:
        path = revision / f'reviews/{stage}-review-log.yaml'
        rows = read_yaml(path).get('rounds', []) if path.is_file() else []
        return [{'event_id': f'legacy:{index}', 'evidence': row}
                for index, row in enumerate(rows)]
    if stage == 'visual':
        return [{'event_id': f'legacy:{p.name}', 'evidence': read_yaml(p)}
                for p in sorted((revision / 'reviews/visual').glob('review-[0-9][0-9].yaml'))]
    return []


def review_budget_status(revision: Path, stage: str) -> dict:
    """Read only, including when no ledger has been created yet."""
    limit = _limit(stage)
    events = _read(revision)['stages'].get(stage)
    if events is None:
        events = _historical_events(revision, stage)
    issue_sets = [{i.get('issue_id') for i in e.get('evidence', {}).get('issues', [])
                   if i.get('issue_id')} for e in events]
    repeated = sorted(issue_sets[-1] & issue_sets[-2]) if len(issue_sets) >= 2 else []
    return {'stage': stage, 'limit': limit, 'used': len(events), 'events': events,
            'repeated_issues': repeated, 'exhausted': len(events) >= limit or bool(repeated),
            'policy': D4_EXHAUSTED_POLICY}


def consume_review_budget(revision: Path, stage: str, event_id: str) -> int:
    """Reserve one attempt atomically; replay returns its original ordinal."""
    _limit(stage)
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError('Review budget event_id must be nonempty')
    with revision_lock(revision / 'reviews/budget'):
        data = _read(revision)
        events = data['stages'].setdefault(stage, _historical_events(revision, stage))
        for index, event in enumerate(events):
            if event['event_id'] == event_id:
                return index + 1
        require_available(revision, stage)
        events.append({'event_id': event_id, 'consumed_at': datetime.now(UTC).isoformat()})
        write_yaml_atomic(revision / LEDGER, data)
        return len(events)


def record_evidence(revision: Path, stage: str, event_id: str, evidence: dict, *,
                    result: bool = False) -> None:
    with revision_lock(revision / 'reviews/budget'):
        data = _read(revision)
        for event in data['stages'][stage]:
            if event['event_id'] == event_id:
                event['evidence'] = {**event.get('evidence', {}), **evidence}
                if result:
                    event['recorded_result'] = evidence
                write_yaml_atomic(revision / LEDGER, data)
                return
        raise ValueError('Unknown budget event')


class ReviewBudgetExhausted(ValueError):
    """A failed stage remains blocked; this brief asks for guidance, never approval."""

    def __init__(self, revision: Path, status: dict):
        role = ROLES.get(status['stage'], 'repair_engineer')
        self.brief = {
            'assigned_role': role, 'policy': D4_EXHAUSTED_POLICY, 'passed': False,
            'stage': status['stage'], 'used': status['used'], 'limit': status['limit'],
            'repeated_issues': status['repeated_issues'], 'evidence_path': str(revision / LEDGER),
            'events': [{'event_id': e['event_id'], 'consumed_at': e.get('consumed_at'),
                        'issues': e.get('evidence', {}).get('issues', []),
                        'outcome': e.get('evidence', {}).get('outcome', 'interrupted_or_legacy'),
                        'detail': e.get('evidence', {}).get('detail', ''),
                        'cause': e.get('evidence', {}).get('cause', ''),
                        'incident': e.get('evidence', {}).get('incident', {})}
                       for e in status['events']],
            'request': 'Present evidence and open issues to the doctor; await scoped guidance. '
                       'Do not submit a gate or reset this revision budget.',
        }
        super().__init__(f'Review budget exhausted: {status["stage"]}; '
                         f'{status["used"]}/{status["limit"]}; {D4_EXHAUSTED_POLICY}; '
                         f'assigned_role={role}; evidence={revision / LEDGER}; '
                         f'issues={status["repeated_issues"]}. {self.brief["request"]}')


def require_available(revision: Path, stage: str) -> None:
    status = review_budget_status(revision, stage)
    if status['exhausted']:
        raise ReviewBudgetExhausted(revision, status)


def finish_attempt(revision: Path, stage: str, event_id: str, *,
                   outcome: str, detail: str, report: Path | None = None) -> None:
    """Persist invocation outcome, including a report binding across process restart."""
    with revision_lock(revision / 'reviews/budget'):
        data = _read(revision)
        event = next(e for e in data['stages'][stage] if e['event_id'] == event_id)
        event['evidence'] = {'outcome': outcome, 'detail': detail}
        if report is not None and report.is_file():
            event['report_sha256'] = sha256_file(report)
            event['report_path'] = report.relative_to(revision).as_posix()
        write_yaml_atomic(revision / LEDGER, data)


def report_event(revision: Path, stage: str, report: Path, *, event_id: str | None = None,
                 allow_recorded: bool = False) -> str:
    """Match the invocation ID; the digest validates its bound output, never its identity."""
    if report.is_file():
        digest = sha256_file(report)
        events = review_budget_status(revision, stage)['events']
        for event in events:
            if event_id is not None and event['event_id'] != event_id:
                continue
            if event.get('report_sha256') == digest and 'recorded_result' not in event:
                return event['event_id']
        if allow_recorded:
            for event in reversed(events):
                if event.get('report_sha256') == digest:
                    return event['event_id']
    raise ValueError(f'Review budget reservation missing for {stage}; no critic result accepted')


def recorded_result(revision: Path, stage: str, event_id: str | None) -> dict | None:
    if event_id is None:
        return None
    return next((e.get('recorded_result') for e in review_budget_status(revision, stage)['events']
                 if e['event_id'] == event_id), None)


def _recover_results(revision: Path) -> None:
    """Replay committed result journals into missing canonical history, never re-score."""
    for stage in ('script', 'product'):
        results = [e['recorded_result'] for e in _read(revision)['stages'].get(stage, [])
                   if 'recorded_result' in e]
        if not results:
            continue
        path = revision / f'reviews/{stage}-review-log.yaml'
        log = read_yaml(path) if path.is_file() else {'version': 1, 'rounds': [], 'submitted': 0}
        known = {row.get('budget_event_id') for row in log.get('rounds', [])}
        missing = [r for r in results if r.get('budget_event_id') not in known]
        if missing:
            log['rounds'] = [*log.get('rounds', []), *missing]
            write_yaml_atomic(path, log)


def recover_results(revision: Path) -> None:
    if enabled(revision):
        with revision_lock(revision / 'reviews/results'):
            _recover_results(revision)


def serialized_record(function):
    """Serialize R5 result claims and history writes; preserve legacy entry points."""
    @wraps(function)
    def record(path: Path, *args, **kwargs):
        revision = (resolve_project_layout(path).artifact_root
                    if (path / 'project.yaml').is_file() else path)
        if not enabled(revision):
            return function(path, *args, **kwargs)
        with revision_lock(revision / 'reviews/results'):
            _recover_results(revision)
            return function(path, *args, **kwargs)
    return record
