"""Critic agent scores a draft; Python decides rewrite or medical submission."""

from datetime import date
from pathlib import Path

import pytest

from healthvideo.agents import AgentResult
from healthvideo.company import load_company
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.queue import add_to_queue
from healthvideo.workflows.review_html import _render_script_review_section
from healthvideo.workflows.runner import RunDeps, run_queue
from healthvideo.workflows.script_review import (
    CRITERIA,
    LOG,
    MAX_REVIEWS,
    REPORT,
    next_script_action,
    record_review,
    review_view,
    revision_notes,
    script_hash,
)
from tests.helpers import create_v2_project_fixture

SLUG = 'muoi-va-huyet-ap-v2'


def _project(root: Path) -> Path:
    project = create_v2_project_fixture(root / 'projects')
    _script(project, 'Bộ tài liệu đã kiểm tra chưa chứng minh được.')
    return project


def _script(project: Path, text: str) -> None:
    write_yaml_atomic(project / 'revisions/001/script/script.yaml',
                      {'lines': [{'id': 'N01', 'text': text}]})


def _report(project: Path, score: int = 8, **changes) -> None:
    issues = [] if score >= 7 else [{
        'line': 'N01', 'criterion': key, 'problem': 'Lộ ngôn ngữ nguồn.', 'fix': 'Nói tự nhiên.',
    } for key in CRITERIA]
    write_yaml_atomic(project / 'revisions/001' / REPORT, {
        'scores': dict.fromkeys(CRITERIA, score), 'summary': 'Nhận xét.', 'issues': issues,
        **changes,
    })


def _review(project: Path, score: int) -> dict:
    _report(project, score)
    return record_review(project, script_hash(project))


def test_failed_review_requires_rewrite_then_new_script_is_reviewed(tmp_path):
    project = _project(tmp_path)
    assert next_script_action(project) == 'script_review'
    assert _review(project, 6)['passed'] is False
    assert not (project / 'revisions/001' / REPORT).exists()
    assert next_script_action(project) == 'draft'
    assert 'Nói tự nhiên.' in revision_notes(project)
    _script(project, 'Tìm đỏ mắt cũng chẳng thấy bằng chứng.')
    assert next_script_action(project) == 'script_review'
    assert _review(project, 8)['passed'] is True
    assert next_script_action(project) == 'submit_medical'


def test_one_criterion_below_pass_score_fails_even_with_high_average(tmp_path):
    project = _project(tmp_path)
    scores = dict.fromkeys(CRITERIA, 10) | {'ca_tinh': 6}
    issue = {'line': 'N01', 'criterion': 'ca_tinh', 'problem': 'Khô.', 'fix': 'Dí dỏm hơn.'}
    _report(project, scores=scores, issues=[issue])
    assert record_review(project, script_hash(project))['passed'] is False


def test_reviews_are_bounded_then_doctor_sees_the_failed_score(tmp_path):
    project = _project(tmp_path)
    for attempt in range(MAX_REVIEWS):
        _script(project, f'Bản {attempt}')
        _review(project, 5)
    assert next_script_action(project) == 'submit_medical'
    root = project / 'revisions/001'
    assert review_view(root)['round'] == MAX_REVIEWS
    assert 'Chưa đạt' in _render_script_review_section(root)


@pytest.mark.parametrize(('change', 'message'), [
    ({'scores': {'ca_tinh': 8}}, 'đủ đúng các tiêu chí'),
    ({'scores': dict.fromkeys(CRITERIA, 11)}, 'từ 1 đến 10'),
    ({'scores': dict.fromkeys(CRITERIA, 5), 'issues': []}, 'thiếu chỗ cần sửa'),
    ({'issues': [{'line': 'N99', 'criterion': 'ca_tinh', 'problem': 'x', 'fix': 'y'}]},
     'Dòng không có'),
    ({'issues': [{'line': 'N01', 'criterion': 'la', 'problem': 'x', 'fix': 'y'}]},
     'Tiêu chí không tồn tại'),
])
def test_invalid_report_is_refused_and_not_logged(tmp_path, change, message):
    project = _project(tmp_path)
    _report(project, **change)
    with pytest.raises(ValueError, match=message):
        record_review(project, script_hash(project))
    assert not (project / 'revisions/001' / LOG).exists()


def test_missing_report_and_critic_edit_are_refused(tmp_path):
    project = _project(tmp_path)
    with pytest.raises(ValueError, match='chưa ghi báo cáo'):
        record_review(project, script_hash(project))
    before = script_hash(project)
    _script(project, 'Biên tập viên tự sửa.')
    _report(project)
    with pytest.raises(ValueError, match='không được sửa'):
        record_review(project, before)


def _deps(state: dict, invoke) -> RunDeps:
    def submit(_project):
        state['value'] = WorkflowState.AWAITING_MEDICAL_REVIEW
        state['submitted'] = True

    return RunDeps(
        create_project=lambda *_: None,
        read_state=lambda _project: state['value'],
        reject_note=lambda _project: 'Bác sĩ muốn nói rõ hơn.',
        python_steps={'submit_medical': submit},
        changed_code_paths=lambda _root: [],
        invoke=invoke,
    )


def _queue(root: Path) -> Path:
    add_to_queue(root, QueueEntry(slug=SLUG, title='Muối', question='Vì sao?',
                                  added=date(2026, 11, 6)))
    return _project(root)


def test_run_reviews_rewrites_with_notes_then_submits_without_approving(tmp_path):
    project = _queue(tmp_path)
    state = {'value': WorkflowState.DRAFT_READY}
    calls: list[tuple[str, str]] = []

    def invoke(agents, prompt, *, cwd, log_dir, **_):
        del cwd
        log_dir.mkdir(parents=True, exist_ok=True)
        reviewing = '(`script_review`)' in prompt
        calls.append((agents[0].cli, 'review' if reviewing else 'draft'))
        if reviewing:
            _report(project, 6 if len(calls) == 1 else 8)
        else:
            assert 'Nói tự nhiên.' in prompt
            assert 'Bác sĩ muốn nói rõ hơn.' in prompt
            _script(project, 'Bản đã sửa.')
        return AgentResult(agents[0].cli, True, False, log_dir / 'fake.log')

    report = run_queue(tmp_path, _deps(state, invoke))

    # The critic (codex first) never starts on the writer's model (claude first).
    assert calls == [('codex', 'review'), ('claude', 'draft'), ('codex', 'review')]
    assert state['submitted'] is True
    assert report.at_gate == [SLUG]
    assert report.blocked == []
    rounds = read_yaml(project / 'revisions/001' / LOG)['rounds']
    assert [row['passed'] for row in rounds] == [False, True]


def test_run_blocks_when_writer_leaves_script_unchanged(tmp_path):
    project = _queue(tmp_path)
    state = {'value': WorkflowState.DRAFT_READY}

    def invoke(agents, prompt, *, cwd, log_dir, **_):
        del cwd
        log_dir.mkdir(parents=True, exist_ok=True)
        if '(`script_review`)' in prompt:
            _report(project, 5)
        return AgentResult(agents[0].cli, True, False, log_dir / 'fake.log')

    report = run_queue(tmp_path, _deps(state, invoke))

    assert report.blocked == [SLUG]
    assert 'submitted' not in state
    blocked = tmp_path / 'topics/logs' / SLUG / 'blocked.txt'
    assert 'không sửa kịch bản' in blocked.read_text(encoding='utf-8')


def test_run_blocks_when_critic_writes_no_report(tmp_path):
    _queue(tmp_path)
    state = {'value': WorkflowState.DRAFT_READY}

    def invoke(agents, prompt, *, cwd, log_dir, **_):
        del prompt, cwd
        log_dir.mkdir(parents=True, exist_ok=True)
        return AgentResult(agents[0].cli, True, False, log_dir / 'fake.log')

    report = run_queue(tmp_path, _deps(state, invoke))

    assert report.blocked == [SLUG]
    assert 'submitted' not in state


def test_runner_uses_role_chain_for_step(tmp_path):
    _queue(tmp_path)
    state = {'value': WorkflowState.DRAFT_READY}
    seen = []

    def invoke(slots, prompt, *, cwd, log_dir, **kwargs):
        del prompt, cwd
        seen.append((list(slots), kwargs))
        log_dir.mkdir(parents=True, exist_ok=True)
        return AgentResult(slots[0].cli, True, False, log_dir / 'fake.log')

    run_queue(tmp_path, _deps(state, invoke), once=True)

    slots, kwargs = seen[0]
    assert kwargs == {'role': 'script_critic', 'slug': SLUG, 'step': 'script_review'}
    assert slots == load_company().chain('script_critic')


@pytest.mark.parametrize('step', ['draft', 'script_review', 'revise_medical'])
def test_script_prompts_carry_the_ai_writing_signs(step):
    from healthvideo.workflows.runner import render_prompt
    assert 'Dấu hiệu văn AI cần tránh trong lời đọc' in render_prompt(step)
