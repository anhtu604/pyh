"""Critic agent scores a draft; Python decides rewrite or medical submission."""

from dataclasses import replace
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
    MAX_CYCLES,
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
    (project / 'revisions/001' / LOG).unlink()
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


def _legacy_review(project: Path, score: int) -> dict:
    entry = _review(project, score)
    path = project / 'revisions/001' / LOG
    log = read_yaml(path)
    for row in log['rounds']:
        row.pop('snapshot', None)
        row.pop('issue_statuses', None)
    write_yaml_atomic(path, log)
    return entry


def test_reviews_are_bounded_and_failed_script_stays_before_doctor_gate(tmp_path):
    project = _project(tmp_path)
    for cycle in range(MAX_CYCLES):
        for attempt in range(MAX_REVIEWS):
            _script(project, f'Bản {cycle}-{attempt}')
            _legacy_review(project, 6)
        if cycle < MAX_CYCLES - 1:
            assert next_script_action(project) == 'draft'
            log = read_yaml(project / 'revisions/001' / LOG)
            assert log['cycles'] == cycle + 2
            assert log['submitted'] == 0
            # A restart before Writer completes must still request a rewrite.
            assert next_script_action(project) == 'draft'
    with pytest.raises(ValueError, match=r'3 chu kỳ \(6 vòng\).*Giọng người thật.*6.*Bác sĩ.*chat'):
        next_script_action(project)
    root = project / 'revisions/001'
    assert review_view(root)['round'] == MAX_REVIEWS * MAX_CYCLES
    assert 'Chưa đạt' in _render_script_review_section(root)


@pytest.mark.parametrize('cycles', [1, MAX_CYCLES])
def test_rewritten_script_after_exhausted_cycle_is_reviewed_unless_at_limit(tmp_path, cycles):
    project = _project(tmp_path)
    for _ in range(MAX_REVIEWS):
        _legacy_review(project, 6)
    path = project / 'revisions/001' / LOG
    log = read_yaml(path)
    # Legacy logs have no cycle metadata and start at cycle one.
    if cycles == 1:
        log.pop('cycles')
    else:
        log['cycles'] = cycles
    write_yaml_atomic(path, log)
    _script(project, 'Writer đã sửa sau vòng chấm cuối.')
    assert script_hash(project) != log['rounds'][-1]['script_sha256']

    if cycles == MAX_CYCLES:
        with pytest.raises(ValueError, match='Trạm 07'):
            next_script_action(project)
        assert read_yaml(path) == log
        return

    assert next_script_action(project) == 'script_review'
    updated = read_yaml(path)
    assert updated['cycles'] == cycles + 1
    assert updated['cycle_start'] == len(log['rounds'])
    assert updated['rounds'] == log['rounds']
    assert 'rewrite_pending_hash' not in updated
    assert next_script_action(project) == 'script_review'
    assert _review(project, 8)['passed'] is True
    assert next_script_action(project) == 'submit_medical'


def test_legacy_submitted_log_starts_at_cycle_one(tmp_path):
    project = _project(tmp_path)
    for _ in range(5):
        _legacy_review(project, 6)
    path = project / 'revisions/001' / LOG
    log = read_yaml(path)
    write_yaml_atomic(path, {'version': 1, 'submitted': 3, 'rounds': log['rounds']})
    assert next_script_action(project) == 'draft'
    assert read_yaml(path)['cycles'] == 2
    _script(project, 'Sửa trong chu kỳ hai')
    assert next_script_action(project) == 'script_review'


def test_revision_notes_merge_three_rounds_latest_wins_and_resolved_is_removed(tmp_path):
    from healthvideo.workflows.runner import _build_step_prompt

    project = _project(tmp_path)
    for number, criterion in enumerate(CRITERIA):
        if number == 4:
            break
        issue = {'line': 'N01', 'criterion': criterion,
                 'problem': f'issue-{number}', 'fix': f'fix-{number}'}
        _report(project, scores=dict.fromkeys(CRITERIA, 7 + number % 2), issues=[issue])
        record_review(project, script_hash(project))
        path = project / 'revisions/001' / LOG
        log = read_yaml(path)
        for row in log['rounds']:
            row.pop('snapshot', None)
        write_yaml_atomic(path, log)
    notes = revision_notes(project)
    assert 'issue-0' not in notes
    assert all(f'issue-{n}' in notes for n in (1, 2, 3))
    _report(project, scores=dict.fromkeys(CRITERIA, 8), issues=[{
        'line': 'N01', 'criterion': 'khong_lap_y', 'problem': 'newest', 'fix': 'newest-fix',
    }], resolved_issues=[{'line': 'N01', 'criterion': 'hinh_anh'}])
    record_review(project, script_hash(project))
    path = project / 'revisions/001' / LOG
    log = read_yaml(path)
    for row in log['rounds']:
        row.pop('snapshot', None)
    write_yaml_atomic(path, log)
    notes = revision_notes(project)
    assert 'newest' in notes and 'issue-2' not in notes and 'issue-3' not in notes
    assert '7 → 8 → 8' in notes
    assert 'giữ nguyên id dòng' in notes
    assert 'không viết lại toàn bài' in notes
    entry = QueueEntry(slug=SLUG, title='Muối', question='Vì sao?', added=date(2026, 11, 6))
    prompt = _build_step_prompt(tmp_path, _deps({}, None), entry, project, 'draft', rewriting=True)
    assert 'newest' in prompt and 'issue-1' not in prompt


def test_medical_submission_marks_review_cycle_without_losing_history(tmp_path):
    from healthvideo.workflows.draft import submit_medical_review

    project = create_v2_project_fixture(tmp_path / 'projects')
    _report(project)
    record_review(project, script_hash(project))
    submit_medical_review(project)
    log = read_yaml(project / 'revisions/001' / LOG)
    assert log['submitted'] == len(log['rounds']) == 2
    assert next_script_action(project) == 'script_review'


@pytest.mark.parametrize('problem', ['missing', 'stale'])
def test_medical_submission_and_approval_require_current_passing_critic(tmp_path, problem):
    from datetime import UTC, datetime

    from healthvideo.domain.gate_review import GateKind
    from healthvideo.domain.project_v2 import ProjectManifestV2
    from healthvideo.workflows import factory
    from healthvideo.workflows.draft import submit_medical_review
    from healthvideo.workflows.gate_review import approve_gate

    project = create_v2_project_fixture(tmp_path / 'projects')
    log_path = project / 'revisions/001' / LOG
    if problem == 'missing':
        log_path.unlink()
    else:
        log = read_yaml(log_path)
        log['rounds'][-1]['script_sha256'] = 'stale'
        write_yaml_atomic(log_path, log)
    before = (project / 'project.yaml').read_bytes()
    with pytest.raises(ValueError, match='Trạm 07'):
        submit_medical_review(project)
    assert (project / 'project.yaml').read_bytes() == before
    manifest = read_yaml(project / 'project.yaml')
    write_yaml_atomic(project / 'project.yaml', {**manifest, 'state': 'awaiting_medical_review'})
    assert factory.gate_for_project(project, ProjectManifestV2.model_validate(
        read_yaml(project / 'project.yaml'))) is None
    with pytest.raises(ValueError, match='Trạm 07'):
        approve_gate(project, GateKind.MEDICAL, reviewer='Fixture doctor', now=datetime.now(UTC))
    assert not (project / 'revisions/001/reviews/medical-approval.yaml').exists()


@pytest.mark.parametrize(('change', 'message'), [
    ({'scores': {'ca_tinh': 8}}, 'đủ đúng các tiêu chí'),
    ({'scores': dict.fromkeys(CRITERIA, 11)}, 'từ 1 đến 10'),
    ({'scores': dict.fromkeys(CRITERIA, 5), 'issues': []}, 'thiếu chỗ cần sửa'),
    ({'issues': [{'line': 'N99', 'criterion': 'ca_tinh', 'problem': 'x', 'fix': 'y'}]},
     'Dòng không có'),
    ({'issues': [{'line': 'N01', 'criterion': 'la', 'problem': 'x', 'fix': 'y'}]},
     'Tiêu chí không tồn tại'),
    ({'resolved_issues': [{'line': 'N99', 'criterion': 'ca_tinh'}]}, 'dòng và tiêu chí'),
    ({'resolved_issues': [{'line': 'N01', 'criterion': 'la'}]}, 'dòng và tiêu chí'),
    ({'issues': [{'line': 'N01', 'criterion': 'ca_tinh', 'problem': 'x', 'fix': 'y'}],
      'resolved_issues': [{'line': 'N01', 'criterion': 'ca_tinh'}]}, 'vừa còn mở vừa đã sửa'),
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
        calls.append((agents[0].model, 'review' if reviewing else 'draft'))
        if reviewing:
            _report(project, 6 if len(calls) == 1 else 8)
        else:
            assert 'Nói tự nhiên.' in prompt
            assert 'Bác sĩ muốn nói rõ hơn.' in prompt
            assert 'Giữ id, thứ tự' in prompt
            assert 'Giữ nguyên từng byte ngoài phạm vi' in prompt
            assert 'Editable lines only' in prompt
            _script(project, 'Bản đã sửa.')
        return AgentResult(agents[0].cli, True, False, log_dir / 'fake.log')

    report = run_queue(tmp_path, _deps(state, invoke))

    # The critic never starts on the writer's model.
    assert calls == [('codex/gpt-6.1-terra', 'review'), ('codex/gpt-6.1-sol', 'draft'), ('codex/gpt-6.1-terra', 'review')]
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


@pytest.mark.parametrize('parallel', [False, True])
@pytest.mark.parametrize('initial_draft', [False, True])
def test_runner_defers_storyboard_voice_until_current_script_passes(tmp_path, parallel, initial_draft):
    project = _queue(tmp_path)
    if not initial_draft:
        _review(project, 6)
    state = {'value': WorkflowState.DRAFT_READY}
    calls = []
    prepared = {}
    review_count = 0

    def invoke(agents, prompt, *, log_dir, step, **_):
        nonlocal review_count
        log_dir.mkdir(parents=True, exist_ok=True)
        calls.append(step)
        if step == 'script_review':
            review_count += 1
            if not initial_draft or review_count > 1:
                assert 'Open issues' in prompt
                assert 'Lộ ngôn ngữ nguồn.' in prompt
            _report(project, 8 if review_count == (2 if initial_draft else 1) else 6)
        elif step == 'draft':
            assert 'Open issues' in prompt
            _script(project, f'Bản sửa {len(calls)}')
        else:
            assert step in {'storyboard_design', 'voice_prep'}
            log = read_yaml(project / 'revisions/001' / LOG) if (
                project / 'revisions/001' / LOG).exists() else {}
            if log.get('rounds'):
                assert log['rounds'][-1]['passed']
                assert log['rounds'][-1]['script_sha256'] == script_hash(project)
            prepared[step] = script_hash(project)
        return AgentResult(agents[0].cli, True, False, log_dir / 'fake.log')

    deps = replace(
        _deps(state, invoke), parallel_branches=parallel,
        storyboard_ready=lambda _: prepared.get('storyboard_design') == script_hash(project),
        voice_prep_ready=lambda _: prepared.get('voice_prep') == script_hash(project),
    )
    result = run_queue(tmp_path, deps)
    assert result.blocked == []
    assert state['submitted']
    expected = 2 if initial_draft else 1
    assert calls.count('storyboard_design') == calls.count('voice_prep') == expected
    assert read_yaml(project / 'revisions/001' / LOG)['cycles'] == 1


def test_doctor_pending_request_restarts_exhausted_budget_once_and_runs_writer(tmp_path):
    from healthvideo.workflows.script_review import reset_for_doctor_guidance

    project = _queue(tmp_path)
    for cycle in range(MAX_CYCLES):
        for number in range(MAX_REVIEWS):
            _script(project, f'Bản {cycle}-{number}')
            _legacy_review(project, 6)
        if cycle < MAX_CYCLES - 1:
            next_script_action(project)
    with pytest.raises(ValueError):
        next_script_action(project)
    path = project / 'revisions/001/reviews/changes/doctor-requested.yaml'
    write_yaml_atomic(path, {'kind': 'edit_script', 'brief': 'Rút phần cơ chế',
                             'context': {}, 'applied': False})
    state = {'value': WorkflowState.DRAFT_READY}
    seen = []

    def invoke(agents, prompt, *, log_dir, step, **_):
        seen.append(step)
        assert step == 'draft'
        assert 'Nói tự nhiên.' in prompt
        _script(project, 'Sửa theo hướng dẫn bác sĩ')
        log_dir.mkdir(parents=True, exist_ok=True)
        return AgentResult(agents[0].cli, True, False, log_dir / 'fake.log')

    result = run_queue(tmp_path, _deps(state, invoke), once=True)
    assert result.blocked == [] and seen == ['draft']
    log_path = project / 'revisions/001' / LOG
    log = read_yaml(log_path)
    assert log['cycles'] == 1 and log['cycle_start'] == 6
    assert len(log['rounds']) == 6
    assert next_script_action(project) == 'script_review'
    _legacy_review(project, 6)
    reset_for_doctor_guidance(project, str(path))
    assert read_yaml(log_path)['cycle_start'] == 6
    assert next_script_action(project) == 'draft'


def test_station_07_cycle_cap_formats_score_and_missing_report_names_file(tmp_path):
    project = _project(tmp_path)
    with pytest.raises(ValueError, match=r'thiếu reviews/script-review\.yaml'):
        record_review(project, script_hash(project))

    # Simulate reaching MAX_CYCLES * MAX_REVIEWS where final round fails 'dung_yeu_cau' at 6/10.
    for cycle in range(MAX_CYCLES):
        for number in range(MAX_REVIEWS):
            _script(project, f'Phiên bản {cycle}-{number}')
            failing = 'giong_nguoi_that' if number == 0 else 'dung_yeu_cau'
            scores = {**dict.fromkeys(CRITERIA, 8), failing: 6}
            _report(
                project,
                scores=scores,
                issues=[{
                    'line': 'N01',
                    'criterion': failing,
                    'problem': f'Cần sửa tiêu chí {failing} (vòng {cycle}-{number}).',
                    'fix': 'Chỉnh lại đúng câu hỏi.',
                }],
            )
            record_review(project, script_hash(project))
            log_path = project / 'revisions/001' / LOG
            log_data = read_yaml(log_path)
            for row in log_data['rounds']:
                row.pop('snapshot', None)
            write_yaml_atomic(log_path, log_data)
        if cycle < MAX_CYCLES - 1:
            assert next_script_action(project) == 'draft'

    with pytest.raises(ValueError, match=r'3 chu kỳ \(6 vòng\).*đúng nghĩa claim \(6/10\).*Bác sĩ.*chat') as exc_info:
        next_script_action(project)
    assert 'claim 6.' not in str(exc_info.value)
