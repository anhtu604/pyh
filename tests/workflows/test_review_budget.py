from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from healthvideo.workflows.review_budget import (
    consume_review_budget,
    review_budget_status,
)


def _consume(args):
    revision, event = args
    try:
        return consume_review_budget(Path(revision), 'product', event)
    except ValueError:
        return 'exhausted'


@pytest.mark.parametrize(('stage', 'limit'), [('script', 2), ('visual', 3), ('product', 3)])
def test_durable_idempotent_budget(tmp_path, stage, limit):
    assert review_budget_status(tmp_path, stage)['used'] == 0
    assert list(tmp_path.iterdir()) == []
    for index in range(limit):
        assert consume_review_budget(tmp_path, stage, str(index)) == index + 1
        assert consume_review_budget(tmp_path, stage, str(index)) == index + 1
    for index in range(24):
        with pytest.raises(ValueError, match='budget'):
            consume_review_budget(tmp_path, stage, f'reset-{index}')
    status = review_budget_status(tmp_path, stage)
    assert status['used'] == limit
    assert len(status['events']) == limit
    assert status['exhausted']
    assert consume_review_budget(tmp_path, stage, '0') == 1


def test_processes_cannot_exceed_limit(tmp_path):
    with ProcessPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(_consume, [(str(tmp_path), str(i)) for i in range(12)]))
    assert sorted(x for x in result if isinstance(x, int)) == [1, 2, 3]
    assert review_budget_status(tmp_path, 'product')['used'] == 3


def test_diagnosis_fingerprint_survives_sixty_restarts(tmp_path):
    for index in range(60):
        if index < 2:
            consume_review_budget(tmp_path, 'diagnosis:root-cause', str(index))
        else:
            with pytest.raises(ValueError):
                consume_review_budget(tmp_path, 'diagnosis:root-cause', str(index))
    assert review_budget_status(tmp_path, 'diagnosis:root-cause')['used'] == 2
    assert review_budget_status(tmp_path, 'diagnosis:other-cause')['used'] == 0
    assert review_budget_status(tmp_path / 'new-revision', 'product')['used'] == 0


def test_invalid_stage_and_corrupt_ledger_fail_closed(tmp_path):
    with pytest.raises(ValueError):
        consume_review_budget(tmp_path, 'typo', 'x')
    consume_review_budget(tmp_path, 'script', 'x')
    (tmp_path / 'reviews/review-budget.yaml').write_text('stages: corrupt', encoding='utf-8')
    with pytest.raises(ValueError):
        consume_review_budget(tmp_path, 'script', 'y')


def test_exhausted_brief_routes_open_issue_with_evidence(tmp_path):
    from healthvideo.workflows.review_budget import (
        ReviewBudgetExhausted,
        record_evidence,
        require_available,
    )

    for index in range(2):
        event = str(index)
        consume_review_budget(tmp_path, 'product', event)
        record_evidence(tmp_path, 'product', event, {
            'issues': [{'issue_id': 'same', 'fix': 'Scoped repair', 'blocking_safety': True}]})
    with pytest.raises(ReviewBudgetExhausted) as error:
        require_available(tmp_path, 'product')
    brief = error.value.brief
    assert brief['assigned_role'] == 'editor'
    assert brief['passed'] is False
    assert brief['repeated_issues'] == ['same']
    assert len(brief['events']) == 2
    assert all(event['issues'][0]['blocking_safety'] for event in brief['events'])


def test_report_binding_survives_restart_without_consuming_again(tmp_path):
    import importlib

    from healthvideo.storage.files import write_yaml_atomic
    from healthvideo.workflows import review_budget

    report = tmp_path / 'reviews/script-review.yaml'
    write_yaml_atomic(report, {'summary': 'Fixture'})
    consume_review_budget(tmp_path, 'script', 'run-one')
    review_budget.finish_attempt(tmp_path, 'script', 'run-one', outcome='reported',
                                 detail='fixture log', report=report)
    importlib.reload(review_budget)
    assert review_budget.report_event(tmp_path, 'script', report) == 'run-one'
    assert review_budget_status(tmp_path, 'script')['used'] == 1


def test_historical_submission_offsets_do_not_grant_credit_or_edit_history(tmp_path):
    from healthvideo.storage.files import write_yaml_atomic

    history = tmp_path / 'reviews/script-review-log.yaml'
    write_yaml_atomic(history, {'rounds': [{'passed': False}, {'passed': False}], 'submitted': 2})
    before = history.read_bytes()
    assert review_budget_status(tmp_path, 'script')['used'] == 2
    with pytest.raises(ValueError, match='budget'):
        consume_review_budget(tmp_path, 'script', 'reset')
    assert history.read_bytes() == before


def test_identical_concurrent_reports_keep_distinct_event_identities(tmp_path):
    from healthvideo.storage.files import write_yaml_atomic
    from healthvideo.workflows import review_budget

    report = tmp_path / 'reviews/product-review.yaml'
    write_yaml_atomic(report, {'summary': 'Same bytes'})
    for event in ('process-A', 'process-B'):
        consume_review_budget(tmp_path, 'product', event)
        review_budget.finish_attempt(tmp_path, 'product', event, outcome='reported',
                                     detail='Fixture', report=report)
    for event in ('process-A', 'process-B'):
        assert review_budget.report_event(tmp_path, 'product', report, event_id=event) == event
        review_budget.record_evidence(tmp_path, 'product', event,
                                       {'issues': [{'issue_id': 'same'}]}, result=True)
    status = review_budget_status(tmp_path, 'product')
    assert status['used'] == 2
    assert status['repeated_issues'] == ['same']
    assert status['exhausted']
    with pytest.raises(ValueError):
        review_budget.report_event(tmp_path, 'product', report)


def test_grant_extra_round_adds_exactly_one_round_with_evidence(tmp_path):
    from healthvideo.workflows.review_budget import (
        ReviewBudgetExhausted,
        grant_extra_round,
        record_evidence,
        require_available,
    )

    for index in range(2):
        event = f'ev-{index}'
        consume_review_budget(tmp_path, 'script', event)
        record_evidence(tmp_path, 'script', event, {
            'issues': [{'issue_id': 'style-01', 'fix': 'Tighten hook'}],
        })
    with pytest.raises(ReviewBudgetExhausted):
        require_available(tmp_path, 'script')

    grant = grant_extra_round(
        tmp_path,
        'script',
        source='playbook PB-002',
        issue_key='repair:station07_review_budget_style',
        grant_id='playbook:PB-002:repair:station07_review_budget_style:1',
    )
    assert grant['extra_rounds'] == 1
    assert grant['source'] == 'playbook PB-002'
    # Idempotent replay does not grant a second round.
    grant_extra_round(
        tmp_path,
        'script',
        source='playbook PB-002',
        issue_key='repair:station07_review_budget_style',
        grant_id='playbook:PB-002:repair:station07_review_budget_style:1',
    )
    status = review_budget_status(tmp_path, 'script')
    assert status['limit'] == 3
    assert status['exhausted'] is False
    assert consume_review_budget(tmp_path, 'script', 'ev-extra') == 3
    with pytest.raises(ReviewBudgetExhausted):
        consume_review_budget(tmp_path, 'script', 'ev-fourth')
