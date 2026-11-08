"""Decision cards preserve doctor control at both gates."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import product_review as pr
from healthvideo.workflows import script_review as sr
from tests.helpers import advance_v2_project_to_video_review, create_v2_project_fixture


def at_gate(tmp_path, gate):
    project = create_v2_project_fixture(tmp_path / 'projects')
    if gate == 'video':
        advance_v2_project_to_video_review(project, now=datetime(2026, 11, 8, tzinfo=UTC))
    else:
        data = read_yaml(project / 'project.yaml')
        write_yaml_atomic(project / 'project.yaml', data | {'state': 'awaiting_medical_review'})
    return project


def decision(where='N14', id='D1'):
    return {'id': id, 'where': where, 'question': 'Chọn cách nói?',
            'why_hard': 'Bác sĩ đã dặn phải hỏi.', 'options': [
                {'id': 'a', 'label': 'Giữ nguyên', 'effect': 'Không đổi', 'keep': True},
                {'id': 'b', 'label': 'Nói rõ hơn', 'effect': 'Thêm câu', 'recommended': True},
            ]}


def report(project, *, gate='medical', decisions=None, preserve_script=False):
    module = sr if gate == 'medical' else pr
    rev = project / 'revisions/001'
    write_yaml_atomic(rev / module.REPORT, {
        'scores': dict.fromkeys(module.CRITERIA, 8), 'summary': 'Đã kiểm',
        'checked': ['Đối chiếu ledger'], 'decisions': decisions or [],
    })
    if gate == 'medical':
        if not preserve_script:
            write_yaml_atomic(rev / 'script/script.yaml', {'lines': [{'id': 'N14'}]})
        return sr.record_review(project, sr.script_hash(project))
    path = rev / pr.RENDER_MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"render": 1}', encoding='utf-8')
    return pr.record_review(project, pr.render_hash(project))


@pytest.mark.parametrize('gate', ['medical', 'video'])
def test_old_logs_without_new_fields_still_load(tmp_path, gate):
    from healthvideo.workflows.decision_card import card
    module = sr if gate == 'medical' else pr
    project = at_gate(tmp_path, gate)
    rev = project / 'revisions/001'
    write_yaml_atomic(rev / module.LOG, {'rounds': [{
        'round': 1, 'passed': True, 'summary': 'Cũ', 'issues': [],
        'scores': dict.fromkeys(module.CRITERIA, 8),
    }]})
    assert module.review_view(rev)['summary'] == 'Cũ'
    result = card(project)
    assert result['checked'] == []
    assert result['decisions'] == []
    assert result['more'] == 0


@pytest.mark.parametrize('gate', ['medical', 'video'])
@pytest.mark.parametrize('keeps', [0, 2])
def test_decision_needs_exactly_one_keep(tmp_path, gate, keeps):
    project = create_v2_project_fixture(tmp_path / 'projects')
    item = decision()
    for option in item['options']:
        option['keep'] = keeps == 2
    with pytest.raises(ValueError, match='keep'):
        report(project, gate=gate, decisions=[item])
    module = sr if gate == 'medical' else pr
    assert not (project / 'revisions/001' / module.LOG).exists()


def test_script_where_must_be_real_line(tmp_path):
    project = create_v2_project_fixture(tmp_path / 'projects')
    with pytest.raises(ValueError, match='N99'):
        report(project, decisions=[decision('N99')])


def test_resubmission_starts_new_review_cycle(tmp_path):
    project = create_v2_project_fixture(tmp_path / 'projects')
    for _ in range(sr.MAX_REVIEWS):
        report(project)
    assert sr.next_script_action(project) == 'submit_medical'
    sr.mark_submitted(project / 'revisions/001')
    assert sr.next_script_action(project) == 'script_review'
    assert sr.review_view(project / 'revisions/001')['round'] == sr.MAX_REVIEWS


@pytest.mark.parametrize('gate', ['medical', 'video'])
def test_card_caps_five_and_counts_more(tmp_path, gate):
    from healthvideo.workflows.decision_card import card
    project = at_gate(tmp_path, gate)
    report(project, gate=gate, decisions=[decision(id=f'D{i}') for i in range(1, 8)])
    result = card(project)
    assert result['gate'] == gate and result['revision'] == '001'
    assert len(result['decisions']) == 5 and result['more'] == 2
    assert result['decisions'][0]['selected'] == 'b'
    assert result['checked'] == ['Đối chiếu ledger']


def test_compose_all_keep_approves():
    from healthvideo.workflows.decision_card import compose
    assert compose({'decisions': [decision()]}, {'D1': 'a'}, '') == (
        'approve', 'D1 (N14) → a: Giữ nguyên')
    assert compose({'decisions': []}, {}, '') == ('approve', '')


def test_compose_non_keep_sends_fix_with_choices():
    from healthvideo.workflows.decision_card import compose
    assert compose({'decisions': [decision()]}, {'D1': 'b'}, '') == (
        'send_fix', 'D1 (N14) → b: Nói rõ hơn')
    assert compose({'decisions': []}, {}, 'Ý khác')[0] == 'send_fix'


@pytest.mark.parametrize('choices', [{}, {'D1': 'bad'}, {'D1': 'a', 'D2': 'b'}])
def test_compose_refuses_invalid_or_missing_choices(choices):
    from healthvideo.workflows.decision_card import compose
    with pytest.raises(ValueError):
        compose({'decisions': [decision()]}, choices, '')


@pytest.mark.parametrize('change', ['duplicate_decision', 'duplicate_option', 'recommendations', 'one_option'])
def test_decision_ids_options_and_recommendation_are_validated(tmp_path, change):
    project = create_v2_project_fixture(tmp_path / 'projects')
    item = decision()
    items = [item]
    if change == 'duplicate_decision':
        items.append(deepcopy(item))
    elif change == 'duplicate_option':
        item['options'][1]['id'] = 'a'
    elif change == 'recommendations':
        item['options'][0]['recommended'] = True
    else:
        item['options'].pop()
    with pytest.raises(ValueError):
        report(project, decisions=items)


@pytest.mark.parametrize('gate', ['medical', 'video'])
def test_excess_decisions_require_bounded_rewrite(tmp_path, gate):
    project = create_v2_project_fixture(tmp_path / 'projects')
    for _ in range(3):
        entry = report(project, gate=gate, decisions=[decision(id=f'D{i}') for i in range(7)])
        assert not entry['passed']
        if gate == 'medical':
            action = sr.next_script_action(project)
            assert action == ('submit_medical' if entry['round'] == 3 else 'draft')
        else:
            action = pr.next_product_action(project)
            assert action == ('submit_video' if entry['round'] == 3 else 'revise_product')
    assert read_yaml(project / 'revisions/001' / (sr.LOG if gate == 'medical' else pr.LOG))
