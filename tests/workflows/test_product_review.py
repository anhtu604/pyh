"""Product critic scores the final cut; fixable faults are fixed and re-rendered before the doctor."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from healthvideo.agents import AgentResult
from healthvideo.company import ModelSlot, load_company
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.queue import add_to_queue
from healthvideo.workflows import product_review as pr
from healthvideo.workflows.factory_standards import (
    STYLE_SPEC_FILE,
    pin_standards,
    style_a_active,
)
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.produce import submit_video
from healthvideo.workflows.runner import RunDeps, run_queue
from tests.helpers import create_v2_project_fixture

SLUG = 'muoi-va-huyet-ap-v2'
REV = Path('revisions/001')


def _render(project: Path, version: int) -> None:
    path = project / REV / pr.RENDER_MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'version': version}), encoding='utf-8')
    pr.hold(project / REV, f'{version:064}')


def _project(root: Path) -> Path:
    project = create_v2_project_fixture(root / 'projects')
    _render(project, 1)
    return project


def _report(project: Path, score: int = 8, *, fixable: bool = True, **changes) -> None:
    issues = [] if score >= pr.PASS_SCORE else [{
        'at': 'S02', 'criterion': key, 'problem': 'Nhãn bị cắt.', 'fix': 'Thu nhỏ nhãn.',
        'fixable': fixable,
    } for key in pr.CRITERIA]
    write_yaml_atomic(project / REV / pr.REPORT, {
        'scores': dict.fromkeys(pr.CRITERIA, score), 'summary': 'Nhận xét.', 'issues': issues,
        **changes,
    })


def _review(project: Path, score: int, **kwargs) -> dict:
    _report(project, score, **kwargs)
    return pr.record_review(project, pr.render_hash(project))


@pytest.mark.parametrize('field', ['summary', 'overall', 'checked', 'problem', 'fix'])
def test_corrupt_product_review_is_not_logged(tmp_path, field):
    project = _project(tmp_path)
    log = project / REV / pr.LOG
    before = log.read_bytes() if log.exists() else None
    bad = 'Kh?ng c? issue m? c?n x? l? trong v?ng n?y.'
    changes = {field: [bad] if field == 'checked' else bad}
    if field in {'problem', 'fix'}:
        changes = {'issues': [{'at': 'S02', 'criterion': 'hinh_ro', 'fixable': True,
                               'problem': 'Nhận xét.', 'fix': 'Sửa nhãn.', field: bad}]}
    _report(project, **changes)
    with pytest.raises(ValueError, match=r'văn bản bị mất dấu \(mã hóa\)'):
        pr.record_review(project, pr.render_hash(project))
    assert (log.read_bytes() if log.exists() else None) == before
    assert (project / REV / pr.REPORT).exists()


def test_product_utf8_review_and_question_are_preserved(tmp_path):
    project = _project(tmp_path)
    text = 'Vì sao? Không có vấn đề cần xử lý. https://example.org/a?b=c'
    _report(project, summary=text, overall=text, checked=[text])
    pr.record_review(project, pr.render_hash(project))
    saved = read_yaml(project / REV / pr.LOG)['rounds'][-1]
    assert saved['summary'] == saved['overall'] == text
    assert saved['checked'] == [text]


def test_failed_fixable_review_asks_for_fix_then_new_render_is_reviewed(tmp_path):
    project = _project(tmp_path)
    assert pr.pending(project)
    assert pr.next_product_action(project) == 'product_review'
    assert _review(project, 6)['passed'] is False
    assert not (project / REV / pr.REPORT).exists()
    assert pr.next_product_action(project) == 'revise_product'
    assert 'S02' in pr.revision_notes(project) and 'Thu nhỏ nhãn.' in pr.revision_notes(project)
    pr.mark_fix_attempted(project)
    _render(project, 2)
    assert pr.next_product_action(project) == 'product_review'
    assert _review(project, 8)['passed'] is True
    assert pr.next_product_action(project) == 'submit_video'


def test_unchanged_render_after_fix_requires_review_and_unfixable_faults_stay_held(tmp_path):
    project = _project(tmp_path)
    _review(project, 5)
    pr.mark_fix_attempted(project)
    assert pr.next_product_action(project) == 'product_review'

    other = _project(tmp_path / 'b')
    _review(other, 5, fixable=False)
    with pytest.raises(ValueError, match='Trạm 12 chưa đạt'):
        pr.next_product_action(other)
    assert 'cần bác sĩ mở cổng y khoa' in pr.review_view(other / REV)['issues'][0]['fix']


def test_rounds_are_bounded_and_reset_after_submission(tmp_path):
    from healthvideo.workflows import doctor_questions

    project = _project(tmp_path)
    for version in range(pr.MAX_REVIEWS):
        _render(project, version + 10)
        _review(project, 5)
    assert pr.next_product_action(project, root=tmp_path) == 'wait_doctor'
    assert doctor_questions.open_question(tmp_path, project.name)['station'] == '12'
    pr.mark_submitted(project / REV)
    assert not pr.pending(project)
    _render(project, 99)
    assert pr.next_product_action(project, root=tmp_path) == 'product_review'
    assert pr.review_view(project / REV)['round'] == pr.MAX_REVIEWS


def test_excess_decisions_recheck_after_unchanged_fix_and_stay_bounded(tmp_path):
    from tests.workflows.test_decision_card import decision

    project = _project(tmp_path)
    decisions = [decision(id=f'D{i}') for i in range(7)]
    for attempt in range(pr.MAX_REVIEWS):
        _review(project, 8, decisions=decisions)
        if attempt == pr.MAX_REVIEWS - 1:
            with pytest.raises(ValueError, match='Trạm 12 chưa đạt'):
                pr.next_product_action(project)
        else:
            assert pr.next_product_action(project) == 'revise_product'
            pr.mark_fix_attempted(project)
            assert pr.next_product_action(project) == 'product_review'


@pytest.mark.parametrize(('change', 'message'), [
    ({'scores': {'hinh_ro': 8}}, 'đủ đúng'),
    ({'scores': dict.fromkeys(pr.CRITERIA, 11)}, '1 đến 10'),
    ({'scores': dict.fromkeys(pr.CRITERIA, 5), 'issues': []}, 'thiếu chỗ cần sửa'),
])
def test_invalid_report_is_refused(tmp_path, change, message):
    project = _project(tmp_path)
    _report(project, **change)
    with pytest.raises(ValueError, match=message):
        pr.record_review(project, pr.render_hash(project))
    assert not (project / REV / pr.LOG).exists()


def test_missing_report_and_critic_rerender_are_refused(tmp_path):
    project = _project(tmp_path)
    with pytest.raises(ValueError, match='chưa ghi báo cáo'):
        pr.record_review(project, pr.render_hash(project))
    before = pr.render_hash(project)
    _render(project, 7)
    _report(project)
    with pytest.raises(ValueError, match='không được dựng lại'):
        pr.record_review(project, before)


def _deps(project: Path, state: dict, invoke) -> RunDeps:
    def produce(_project):
        state['renders'] += 1
        _render(project, state['renders'])

    def submit(_project):
        pr.mark_submitted(project / REV)
        state['value'] = WorkflowState.AWAITING_VIDEO_REVIEW

    return RunDeps(
        create_project=lambda *_: None,
        read_state=lambda _project: state['value'],
        reject_note=lambda _project: None,
        python_steps={'produce': produce, 'submit_video': submit},
        changed_code_paths=lambda _root: [],
        invoke=invoke,
        visual_review_pending=lambda _project: False,
    )


def _queue(root: Path) -> Path:
    add_to_queue(root, QueueEntry(slug=SLUG, title='Muối', question='Vì sao?',
                                  added=date(2026, 11, 7)))
    project = create_v2_project_fixture(root / 'projects')
    _render(project, 1)
    return project


def test_run_reviews_fixes_rerenders_then_submits_without_approving(tmp_path):
    project = _queue(tmp_path)
    state = {'value': WorkflowState.PRODUCTION_IN_PROGRESS, 'renders': 1}
    calls: list[tuple[str, str]] = []

    def invoke(agents, prompt, *, cwd, log_dir, **_):
        del cwd
        log_dir.mkdir(parents=True, exist_ok=True)
        reviewing = '(`product_review`)' in prompt
        calls.append((agents[0].model, 'review' if reviewing else 'fix'))
        if reviewing:
            _report(project, 6 if len(calls) == 1 else 8)
        else:
            assert '(`revise_product`)' in prompt
            assert 'Thu nhỏ nhãn.' in prompt
        return AgentResult(agents[0].cli, True, False, log_dir / 'fake.log')

    report = run_queue(tmp_path, _deps(project, state, invoke))

    # Sol critic remains independent of the Neon editor across both reviews.
    assert calls == [('gpt-6.1-sol', 'review'), ('gemini-4-neon-medium', 'fix'), ('gpt-6.1-sol', 'review')]
    assert state['renders'] == 2
    assert state['value'] == WorkflowState.AWAITING_VIDEO_REVIEW
    assert report.at_gate == [SLUG]
    assert report.blocked == []
    assert not pr.pending(project)
    rounds = read_yaml(project / REV / pr.LOG)['rounds']
    assert [row['passed'] for row in rounds] == [False, True]


def test_run_blocks_when_critic_writes_no_report(tmp_path):
    project = _queue(tmp_path)
    state = {'value': WorkflowState.PRODUCTION_IN_PROGRESS, 'renders': 1}

    def invoke(agents, prompt, *, cwd, log_dir, **_):
        del prompt, cwd
        log_dir.mkdir(parents=True, exist_ok=True)
        return AgentResult(agents[0].cli, True, False, log_dir / 'fake.log')

    report = run_queue(tmp_path, _deps(project, state, invoke))

    assert report.blocked == [SLUG]
    assert state['value'] == WorkflowState.PRODUCTION_IN_PROGRESS
    blocked = tmp_path / 'topics/logs' / SLUG / 'blocked.txt'
    assert 'duyệt sản phẩm lỗi' in blocked.read_text(encoding='utf-8')


def test_submit_video_moves_held_render_to_the_doctor_gate(tmp_path):
    project = create_v2_project_fixture(tmp_path / 'projects')
    manifest = ProjectManifestV2.model_validate(read_yaml(project / 'project.yaml'))
    context = TransitionContext(active_revision='001', current_input_hash='0' * 64,
                                validated_artifacts=frozenset({
                                    'script/script.yaml', 'storyboard/storyboard.yaml',
                                    'assets/asset-manifest.yaml'}))
    manifest = transition_v2(manifest, WorkflowState.AWAITING_MEDICAL_REVIEW, context)
    write_yaml_atomic(project / 'project.yaml', manifest.model_dump(mode='json'))
    approve_gate(project, GateKind.MEDICAL, reviewer='BS An', now=datetime(2026, 11, 7, tzinfo=UTC))
    manifest = ProjectManifestV2.model_validate(read_yaml(project / 'project.yaml'))
    manifest = transition_v2(manifest, WorkflowState.PRODUCTION_IN_PROGRESS, TransitionContext(
        active_revision='001', current_input_hash='1' * 64,
        validated_artifacts=frozenset({'reviews/medical-approval.yaml'})))
    manifest = manifest.model_copy(update={'artifact_hashes': {
        **manifest.artifact_hashes, 'production': '1' * 64}})
    write_yaml_atomic(project / 'project.yaml', manifest.model_dump(mode='json'))
    _render(project, 1)

    with pytest.raises(ValueError, match='Trạm 12 chưa có'):
        submit_video(project)
    _review(project, 8)
    submit_video(project)

    assert read_yaml(project / 'project.yaml')['state'] == 'awaiting_video_review'
    assert not pr.pending(project)
    with pytest.raises(ValueError, match='production_in_progress'):
        submit_video(project)


def test_role_model_override_picks_the_chain(tmp_path):
    project = _queue(tmp_path)
    state = {'value': WorkflowState.PRODUCTION_IN_PROGRESS, 'renders': 1}
    seen = []
    special = ModelSlot(cli='codex', model='special')

    def invoke(agents, prompt, *, cwd, log_dir, **_):
        del prompt, cwd
        log_dir.mkdir(parents=True, exist_ok=True)
        seen.append(agents[0])
        _report(project, 8)
        return AgentResult(agents[0].cli, True, False, log_dir / 'fake.log')

    company = load_company()
    critic = company.roles['product_critic'].model_copy(update={'models': [special]})
    company = company.model_copy(update={'roles': {**company.roles, 'product_critic': critic}})
    run_queue(tmp_path, replace(_deps(project, state, invoke), company=company))
    assert seen == [special]


def test_pyh_style_criterion_required_for_new_reviews_and_exposed_in_view(tmp_path):
    project = _project(tmp_path)
    spec_path = tmp_path / STYLE_SPEC_FILE
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text('# Style A spec\n', encoding='utf-8')
    pin_standards(tmp_path, project)
    assert style_a_active(project / REV) is True
    assert pr.STYLE_CRITERION in pr.CRITERIA
    assert pr.criteria_for_revision(project / REV) == pr.CRITERIA

    _report(project, scores=dict.fromkeys(pr.LEGACY_CRITERIA, 8))
    with pytest.raises(ValueError, match='đủ đúng'):
        pr.record_review(project, pr.render_hash(project))

    _report(
        project,
        scores={**dict.fromkeys(pr.LEGACY_CRITERIA, 8), pr.STYLE_CRITERION: 5},
        issues=[{
            'at': 'S02',
            'criterion': pr.STYLE_CRITERION,
            'problem': 'Chưa dùng mascot Style A.',
            'fix': 'Thêm pose mascot.',
            'fixable': True,
        }],
    )
    failed_entry = pr.record_review(project, pr.render_hash(project))
    assert failed_entry['passed'] is False
    with pytest.raises(ValueError, match='Trạm 12 chưa đạt'):
        pr.require_passed_review(project)

    _render(project, 2)
    _report(project, scores={**dict.fromkeys(pr.LEGACY_CRITERIA, 8), pr.STYLE_CRITERION: 9})
    entry = pr.record_review(project, pr.render_hash(project))
    assert entry['passed'] is True
    style = pr.style_score(project / REV)
    assert style is not None
    assert style['key'] == pr.STYLE_CRITERION
    assert style['score'] == 9
    assert style['passed'] is True
    view = pr.review_view(project / REV)
    assert view['style_score'] == style
    assert any(row['key'] == pr.STYLE_CRITERION and row['score'] == 9 for row in view['scores'])


def test_pre_style_a_revision_does_not_block_gate_on_pyh_style_criterion(tmp_path):
    project = _project(tmp_path)
    assert style_a_active(project / REV) is False
    assert pr.criteria_for_revision(project / REV) == pr.LEGACY_CRITERIA

    # 6 legacy criteria >= 7 pass directly without requiring dung_phong_cach_pyh.
    _report(project, scores=dict.fromkeys(pr.LEGACY_CRITERIA, 8))
    entry_six = pr.record_review(project, pr.render_hash(project))
    assert entry_six['passed'] is True
    pr.require_passed_review(project)
    assert pr.next_product_action(project) == 'submit_video'

    # 7 criteria with low dung_phong_cach_pyh (< 7) stays non-blocking when all 6 legacy >= 7.
    _render(project, 2)
    _report(
        project,
        scores={**dict.fromkeys(pr.LEGACY_CRITERIA, 8), pr.STYLE_CRITERION: 4},
        issues=[{
            'at': 'S01',
            'criterion': pr.STYLE_CRITERION,
            'problem': 'Video cũ không theo mascot Style A.',
            'fix': 'Gợi ý tham khảo cho video mới.',
            'fixable': True,
        }],
    )
    entry_advisory = pr.record_review(project, pr.render_hash(project))
    assert entry_advisory['passed'] is True
    pr.require_passed_review(project)
    assert pr.next_product_action(project) == 'submit_video'
    advisory_style = pr.style_score(project / REV)
    assert advisory_style is not None and advisory_style['score'] == 4 and advisory_style['passed'] is False

    # If a legacy criterion also fails, revision_notes keeps legacy fix notes and hides Style A churn.
    _render(project, 3)
    _report(
        project,
        scores={**dict.fromkeys(pr.LEGACY_CRITERIA, 8), 'hinh_ro': 5, pr.STYLE_CRITERION: 4},
        issues=[
            {
                'at': 'S02',
                'criterion': 'hinh_ro',
                'problem': 'Nhãn bị cắt.',
                'fix': 'Thu nhỏ nhãn.',
                'fixable': True,
            },
            {
                'at': 'S01',
                'criterion': pr.STYLE_CRITERION,
                'problem': 'Thiếu mascot Style A.',
                'fix': 'Dựng lại mascot.',
                'fixable': True,
            },
        ],
    )
    failed_legacy = pr.record_review(project, pr.render_hash(project))
    assert failed_legacy['passed'] is False
    notes = pr.revision_notes(project)
    assert 'Thu nhỏ nhãn.' in notes
    assert 'Dựng lại mascot.' not in notes


def test_run_queue_pre_style_a_passes_gate_and_missing_report_records_retry_reason(tmp_path):
    project = _queue(tmp_path)
    state = {'value': WorkflowState.PRODUCTION_IN_PROGRESS, 'renders': 1}
    prompts: list[str] = []

    def invoke(agents, prompt, *, cwd, log_dir, **_):
        del cwd
        log_dir.mkdir(parents=True, exist_ok=True)
        prompts.append(prompt)
        _report(
            project,
            scores={**dict.fromkeys(pr.LEGACY_CRITERIA, 8), pr.STYLE_CRITERION: 3},
            issues=[{
                'at': 'S01',
                'criterion': pr.STYLE_CRITERION,
                'problem': 'Chưa theo mascot A.',
                'fix': 'Bỏ qua trên video cũ.',
                'fixable': True,
            }],
        )
        return AgentResult(agents[0].cli, True, False, log_dir / 'fake.log')

    report = run_queue(tmp_path, _deps(project, state, invoke))
    assert report.blocked == []
    assert report.at_gate == [SLUG]
    assert state['value'] == WorkflowState.AWAITING_VIDEO_REVIEW
    assert 'TRƯỚC Chuẩn phong cách A' in prompts[0]

    # When Style A is active and critic omits report, concrete missing-file cause lands in both blocked & agent-retry.
    other_root = tmp_path / 'missing-report'
    other_project = _queue(other_root)
    (other_root / STYLE_SPEC_FILE).parent.mkdir(parents=True, exist_ok=True)
    (other_root / STYLE_SPEC_FILE).write_text('# Style A spec\n', encoding='utf-8')
    pin_standards(other_root, other_project)
    other_state = {'value': WorkflowState.PRODUCTION_IN_PROGRESS, 'renders': 1}

    def silent_invoke(agents, prompt, *, cwd, log_dir, **_):
        del cwd
        log_dir.mkdir(parents=True, exist_ok=True)
        assert 'đã ghim Chuẩn phong cách PYH' in prompt
        return AgentResult(agents[0].cli, True, False, log_dir / 'fake.log')

    blocked_report = run_queue(other_root, _deps(other_project, other_state, silent_invoke))
    assert blocked_report.blocked == [SLUG]
    blocked_text = (other_root / 'topics/logs' / SLUG / 'blocked.txt').read_text(encoding='utf-8')
    assert 'reviews/product-review.yaml' in blocked_text
    retry_data = read_yaml(other_root / 'topics/logs' / SLUG / 'agent-retry.yaml')
    assert 'reviews/product-review.yaml' in retry_data['steps']['product_review']['reason']


def test_legacy_pre_r33b_product_review_log_remains_valid_and_viewable(tmp_path):
    project = _project(tmp_path)
    write_yaml_atomic(project / REV / pr.LOG, {
        'version': 1,
        'submitted': 0,
        'rounds': [{
            'round': 1,
            'render_sha256': pr.render_hash(project),
            'passed': True,
            'scores': dict.fromkeys(pr.LEGACY_CRITERIA, 8),
            'summary': 'Bản duyệt cũ trước R3.3b.',
            'issues': [],
            'checked': ['Đã kiểm contact sheet'],
            'decisions': [],
        }],
    })
    pr.require_passed_review(project)
    assert pr.next_product_action(project) == 'submit_video'
    assert pr.style_score(project / REV) is None
    view = pr.review_view(project / REV)
    assert view is not None
    assert view['style_score'] is None
    assert len(view['scores']) == len(pr.LEGACY_CRITERIA)


def _approved_production_project(tmp_path: Path) -> Path:
    from healthvideo.storage.files import canonical_json_hash
    from tests.helpers import write_critic_review_fixture

    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    rev = project / REV
    write_critic_review_fixture(project)
    approve_gate(project, GateKind.MEDICAL, reviewer='BS An', now=datetime(2026, 11, 7, tzinfo=UTC))
    manifest = ProjectManifestV2.model_validate(read_yaml(project / 'project.yaml'))
    manifest = transition_v2(manifest, WorkflowState.PRODUCTION_IN_PROGRESS, TransitionContext(
        active_revision='001', current_input_hash='1' * 64,
        validated_artifacts=frozenset({'reviews/medical-approval.yaml'})))
    write_yaml_atomic(project / 'project.yaml', manifest.model_dump(mode='json'))
    rev_hash = canonical_json_hash({
        'script': read_yaml(rev / 'script/script.yaml'),
        'storyboard': read_yaml(rev / 'storyboard/storyboard.yaml'),
    })
    write_yaml_atomic(rev / 'posts/shorts-plan.yaml', {
        'schema_version': '1.0',
        'revision_hash': rev_hash,
        'clips': [{
            'id': 'CL01',
            'title': 'Clip test',
            'hook_text': 'Huyết áp và muối',
            'start_scene_id': 'S01',
            'end_scene_id': 'S02',
            'target_seconds': 65,
            'caption': 'Cơ chế ăn mặn [claim:C01]',
            'safety_caveat': 'Theo dõi bác sĩ [claim:C01]',
            'safe_zone_checked': True,
        }],
    })
    _render(project, 1)
    return project


@pytest.mark.parametrize('station', ['product', 'script'])
def test_cp1252_question_mark_rejected_while_urls_allowed(tmp_path, station):
    from healthvideo.workflows import script_review as sr

    project = _project(tmp_path / station)
    rev = project / REV
    if station == 'product':
        module, digest_fn, target_at = pr, pr.render_hash, 'S02'
        fail_criterion = 'hinh_ro'
        extra_issue = {'at': target_at, 'criterion': fail_criterion, 'fixable': True}
    else:
        module, digest_fn, target_at = sr, sr.script_hash, 'L01'
        fail_criterion = 'ca_tinh'
        extra_issue = {'line': target_at, 'criterion': fail_criterion}
    base_scores = dict.fromkeys(module.CRITERIA, 8) | {fail_criterion: 6}
    log_path = rev / module.LOG
    log_path.unlink(missing_ok=True)

    # URL with '?' and normal question mark must pass cleanly.
    write_yaml_atomic(rev / module.REPORT, {
        'scores': base_scores,
        'summary': 'Vì sao cần sửa? Xem https://example.com/watch?v=1 để đối chiếu.',
        'overall': 'Cần sửa theo https://example.org/search?q=men&t=2',
        'checked': ['Đã kiểm https://pubmed.example/123?id=4'],
        'issues': [{
            **extra_issue,
            'problem': 'Chưa rõ ở https://example.com/?tab=a',
            'fix': 'Chỉnh lại? Tham khảo https://example.com/?p=9',
        }],
        'decisions': [{
            'id': 'D1',
            'where': target_at,
            'question': 'Chọn cách viết theo https://example.com/?doc=1?',
            'why_hard': 'Hai nguồn khác nhau ở https://example.com/?ref=2',
            'options': [
                {'id': 'a', 'label': 'Giữ nguyên', 'effect': 'Không đổi', 'keep': True},
                {'id': 'b', 'label': 'Đổi câu', 'effect': 'Rõ hơn', 'recommended': True},
            ],
        }],
    })
    module.record_review(project, digest_fn(project))
    assert log_path.is_file()

    # CP1252 '?' inside Vietnamese words must be rejected in every checked field.
    if station == 'product':
        _render(project, 2)
    else:
        script_path = rev / 'script/script.yaml'
        script = read_yaml(script_path)
        script['lines'][0]['text'] += ' thêm ý.'
        write_yaml_atomic(script_path, script)
    before_bytes = log_path.read_bytes()
    for field, value in [
        ('summary', 'B?n d?ng chưa đạt'),
        ('overall', 'C?n sửa lại'),
        ('checked', ['Ki?m tra chưa đủ']),
        ('problem', 'Nhãn bị c?t mép'),
        ('fix', 'D?i nhãn lên trên'),
        ('decisions', [{
            'id': 'D1',
            'where': target_at,
            'question': 'Ch?n cách viết?',
            'why_hard': 'Lý do rõ.',
            'options': [
                {'id': 'a', 'label': 'Giữ nguyên', 'effect': 'Không đổi', 'keep': True},
                {'id': 'b', 'label': 'Đổi câu', 'effect': 'Rõ hơn', 'recommended': True},
            ],
        }]),
    ]:
        payload = {
            'scores': base_scores,
            'summary': 'Tóm tắt chuẩn UTF-8.',
            'overall': 'Ổn.',
            'checked': ['Đã kiểm'],
            'issues': [{**extra_issue, 'problem': 'Lỗi nhỏ.', 'fix': 'Sửa gọn.'}],
            'decisions': [],
        }
        if field in {'problem', 'fix'}:
            payload['issues'][0][field] = value
        else:
            payload[field] = value
        write_yaml_atomic(rev / module.REPORT, payload)
        with pytest.raises(ValueError, match='utf-8'):
            module.record_review(project, digest_fn(project))
        assert log_path.read_bytes() == before_bytes


def test_surgical_repair_allows_flagged_scene_and_syncs_medical_and_shorts_hashes(tmp_path):
    from healthvideo.workflows.gate_review import MEDICAL_APPROVAL_ARTIFACT
    from healthvideo.workflows.produce import _ensure_v2_medical_approval_current

    project = _approved_production_project(tmp_path)
    rev = project / REV
    (tmp_path / 'video/src/anatomy').mkdir(parents=True)
    (tmp_path / 'video/src/scenes').mkdir(parents=True)
    (tmp_path / 'video/src/anatomy/ArterySection.tsx').write_text('export const Artery = 1;\n', encoding='utf-8')
    (tmp_path / 'video/src/anatomy/Heart.tsx').write_text('export const Heart = 1;\n', encoding='utf-8')
    (tmp_path / 'video/src/anatomy/UnrelatedOrgan.tsx').write_text('export const Other = 1;\n', encoding='utf-8')
    (tmp_path / 'video/src/scenes/OutroScene.tsx').write_text('export const Outro = 1;\n', encoding='utf-8')
    (tmp_path / 'video/src/scenes/SourceCardScene.tsx').write_text('export const Source = 1;\n', encoding='utf-8')

    _report(
        project,
        scores={**dict.fromkeys(pr.CRITERIA, 8), 'nhip_dung': 5},
        issues=[{
            'at': 'S02@00:10-00:20',
            'criterion': 'nhip_dung',
            'problem': 'Nhịp cảnh S02 chậm.',
            'fix': 'Thêm nhịp focus vào S02.',
            'fixable': True,
            'edits': [],
        }],
    )
    entry = pr.record_review(project, pr.render_hash(project))
    assert 'video/src/anatomy/UnrelatedOrgan.tsx' not in entry['snapshot']
    assert 'video/src/anatomy/ArterySection.tsx' in entry['snapshot']
    assert 'S02' in pr.revision_notes(project)
    assert 'narration, claim_id' in pr.revision_notes(project)

    before = pr.repair_files(project)
    approval_before = read_yaml(rev / MEDICAL_APPROVAL_ARTIFACT)

    # Modify S02 non-medical field (beats/motion) + S02 anatomy component + OutroScene.
    sb_path = rev / 'storyboard/storyboard.yaml'
    sb = read_yaml(sb_path)
    sb['scenes'][1]['anatomy']['motion'] = 'Adjusted surgical pacing'
    write_yaml_atomic(sb_path, sb)
    (tmp_path / 'video/src/anatomy/ArterySection.tsx').write_text('export const Artery = 2;\n', encoding='utf-8')
    (tmp_path / 'video/src/scenes/OutroScene.tsx').write_text('export const Outro = 2;\n', encoding='utf-8')

    pr.check_repair(project, before)
    pr.finalize_product_repair(project, before)

    approval_after = read_yaml(rev / MEDICAL_APPROVAL_ARTIFACT)
    assert approval_after['artifact_hashes']['storyboard/storyboard.yaml'] != (
        approval_before['artifact_hashes']['storyboard/storyboard.yaml']
    )
    for core_key in ('evidence/ledger.yaml', 'script/script.yaml', 'assets/license-ledger.yaml',
                     'profiles/pronunciation.vi.yaml', 'asset:assets/evidence-r01.svg'):
        assert approval_after['artifact_hashes'][core_key] == approval_before['artifact_hashes'][core_key]

    shorts = read_yaml(rev / 'posts/shorts-plan.yaml')
    assert shorts['revision_hash'] != ''
    sync_log = read_yaml(rev / pr.MEDICAL_HASH_SYNC_LOG)
    assert sync_log['entries'][-1]['changed_artifacts'] == ['storyboard/storyboard.yaml']
    assert 'S02' in sync_log['entries'][-1]['allowed_scenes']
    _ensure_v2_medical_approval_current(rev)


def test_surgical_repair_blocks_medical_fields_unflagged_scenes_and_locked_files(tmp_path):
    project = _approved_production_project(tmp_path)
    rev = project / REV
    (tmp_path / 'video/src/anatomy').mkdir(parents=True)
    (tmp_path / 'video/src/scenes').mkdir(parents=True)
    (tmp_path / 'video/src/anatomy/ArterySection.tsx').write_text('export const Artery = 1;\n', encoding='utf-8')
    (tmp_path / 'video/src/anatomy/Heart.tsx').write_text('export const Heart = 1;\n', encoding='utf-8')
    (tmp_path / 'video/src/scenes/SourceCardScene.tsx').write_text('export const Source = 1;\n', encoding='utf-8')

    _report(
        project,
        scores={**dict.fromkeys(pr.CRITERIA, 8), 'nhip_dung': 5},
        issues=[{
            'at': 'S02',
            'criterion': 'nhip_dung',
            'problem': 'Nhịp chậm.',
            'fix': 'Chỉnh beats ở S02.',
            'fixable': True,
        }],
    )
    pr.record_review(project, pr.render_hash(project))
    before = pr.repair_files(project)

    # 1. Touching locked medical script -> blocked.
    script_path = rev / 'script/script.yaml'
    orig_script = script_path.read_bytes()
    script_path.write_bytes(orig_script + b'\n# tamper\n')
    with pytest.raises(ValueError, match='medical artifact is locked'):
        pr.check_repair(project, before)
    script_path.write_bytes(orig_script)

    # 2. Touching unflagged scene S01 -> blocked.
    sb_path = rev / 'storyboard/storyboard.yaml'
    orig_sb = sb_path.read_bytes()
    sb = read_yaml(sb_path)
    sb['scenes'][0]['evidence_highlight']['quote'] = 'tampered'
    write_yaml_atomic(sb_path, sb)
    with pytest.raises(ValueError, match='Repair scope violation'):
        pr.check_repair(project, before)
    sb_path.write_bytes(orig_sb)

    # 3. Touching medical fields (narration / claim_id) inside allowed scene S02 -> blocked.
    for field, val in [('narration', 'Đổi lời đọc trái phép.'), ('claim_id', 'C99')]:
        sb = read_yaml(sb_path)
        sb['scenes'][1][field] = val
        write_yaml_atomic(sb_path, sb)
        with pytest.raises(ValueError, match='Repair scope violation'):
            pr.check_repair(project, before)
        sb_path.write_bytes(orig_sb)

    # 4. Touching unrelated scene component SourceCardScene.tsx or Heart.tsx (used by S03) -> blocked.
    for locked_ts in ('video/src/scenes/SourceCardScene.tsx', 'video/src/anatomy/Heart.tsx'):
        target = tmp_path / locked_ts
        orig_ts = target.read_bytes()
        target.write_text('export const Tampered = 1;\n', encoding='utf-8')
        with pytest.raises(ValueError, match='Repair scope violation: product target is locked'):
            pr.check_repair(project, before)
        target.write_bytes(orig_ts)

    # 5. Creating a new TSX file -> blocked.
    new_file = tmp_path / 'video/src/scenes/ExtraScene.tsx'
    new_file.write_text('export const Extra = 1;\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Repair scope violation: product target is locked'):
        pr.check_repair(project, before)
    new_file.unlink()


def test_runner_revise_product_syncs_medical_approval_before_produce(tmp_path):
    from healthvideo.workflows.produce import _ensure_v2_medical_approval_current

    add_to_queue(tmp_path, QueueEntry(slug=SLUG, title='Muối', question='Vì sao?',
                                      added=date(2026, 11, 7)))
    project = _approved_production_project(tmp_path)
    rev = project / REV
    state = {'value': WorkflowState.PRODUCTION_IN_PROGRESS, 'renders': 1}
    checked_approval: list[bool] = []

    def produce(proj):
        _ensure_v2_medical_approval_current(proj / REV)
        checked_approval.append(True)
        state['renders'] += 1
        _render(proj, state['renders'])

    def submit(_proj):
        pr.mark_submitted(rev)
        state['value'] = WorkflowState.AWAITING_VIDEO_REVIEW

    def invoke(agents, prompt, *, cwd, log_dir, step, **_):
        del cwd
        log_dir.mkdir(parents=True, exist_ok=True)
        if step == 'product_review':
            _report(
                project,
                scores=dict.fromkeys(pr.CRITERIA, 8) if state['renders'] > 1
                else {**dict.fromkeys(pr.CRITERIA, 8), 'nhip_dung': 5},
                issues=[] if state['renders'] > 1 else [{
                    'at': 'S02',
                    'criterion': 'nhip_dung',
                    'problem': 'Nhịp chậm.',
                    'fix': 'Đổi motion S02.',
                    'fixable': True,
                }],
            )
        elif step == 'revise_product':
            assert 'S02' in prompt
            sb_path = rev / 'storyboard/storyboard.yaml'
            sb = read_yaml(sb_path)
            sb['scenes'][1]['anatomy']['motion'] = 'Updated by revise_product'
            write_yaml_atomic(sb_path, sb)
        return AgentResult(agents[0].cli, True, False, log_dir / 'fake.log')

    deps = RunDeps(
        create_project=lambda *_: None,
        read_state=lambda _p: state['value'],
        reject_note=lambda _p: None,
        python_steps={'produce': produce, 'submit_video': submit},
        changed_code_paths=lambda _r: [],
        invoke=invoke,
        visual_review_pending=lambda _p: False,
    )
    report = run_queue(tmp_path, deps)
    assert report.blocked == []
    assert report.at_gate == [SLUG]
    assert checked_approval == [True]
    assert (rev / pr.MEDICAL_HASH_SYNC_LOG).is_file()


def test_record_review_and_mark_submitted_keep_snapshot_only_on_latest_round(tmp_path):
    project = _project(tmp_path)
    _review(project, 6)
    _render(project, 2)
    _review(project, 6)
    log_data = read_yaml(project / REV / pr.LOG)
    assert len(log_data['rounds']) == 2
    assert 'snapshot' not in log_data['rounds'][0]
    assert 'snapshot' in log_data['rounds'][-1]

    _render(project, 3)
    _review(project, 8)
    pr.mark_submitted(project / REV)
    submitted_log = read_yaml(project / REV / pr.LOG)
    assert len(submitted_log['rounds']) == 3
    assert all('snapshot' not in r for r in submitted_log['rounds'][:-1])
    assert 'snapshot' in submitted_log['rounds'][-1]


def test_stale_render_invalidates_pending_and_requests_produce(tmp_path):
    project = _project(tmp_path)
    manifest_path = project / REV / pr.RENDER_MANIFEST
    manifest_path.write_text(
        json.dumps({'input_hash': 'a' * 64, 'pronunciation_sha256': '0' * 64}),
        encoding='utf-8',
    )
    assert pr.render_is_stale(project) is True
    assert pr.pending(project) is False
    assert pr.next_product_action(project, root=tmp_path) == 'produce'
    assert not (project / REV / pr.PENDING).exists()


def test_surgical_repair_blocks_m64_outro_regression_and_supports_leader_guidance_restore(tmp_path):
    project = _approved_production_project(tmp_path)
    rev = project / REV
    sb_path = rev / 'storyboard/storyboard.yaml'
    sb_orig = read_yaml(sb_path)
    outro_idx = len(sb_orig['scenes']) - 1
    outro_sid = sb_orig['scenes'][outro_idx]['id']

    _report(
        project,
        scores={**dict.fromkeys(pr.CRITERIA, 8), 'nhip_dung': 5},
        issues=[{
            'at': outro_sid,
            'criterion': 'nhip_dung',
            'problem': 'Outro tinh.',
            'fix': 'Chinh outro.',
            'fixable': True,
        }],
    )
    pr.record_review(project, pr.render_hash(project))
    before = pr.repair_files(project)

    # 1. Converting final scene from brand_outro to whiteboard is rejected right away by check_repair.
    bad_sb = read_yaml(sb_path)
    bad_sb['scenes'][outro_idx]['visual'] = 'whiteboard'
    bad_sb['scenes'][outro_idx]['on_screen_text'] = 'Thong tin tong hop'
    bad_sb['scenes'][outro_idx]['visual_assets'] = []
    write_yaml_atomic(sb_path, bad_sb)
    with pytest.raises(ValueError, match='M6.4 final scene must be nonmedical brand_outro'):
        pr.check_repair(project, before)

    # 2. Simulate post-mark_submitted state with leader-guidance.yaml targeting revise_product:
    # restoring outro back to brand_outro succeeds, while tampering narration/script remains blocked.
    pr.mark_submitted(rev)
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True, exist_ok=True)
    write_yaml_atomic(logs / 'leader-guidance.yaml', {
        'revision': '001',
        'role': 'editor',
        'step': 'revise_product',
        'brief': f'Khoi phuc {outro_sid} thanh brand_outro theo M6.4.',
    })
    assert outro_sid in pr.revision_notes(project)

    before_restore = pr.repair_files(project)
    restored_sb = read_yaml(sb_path)
    restored_sb['scenes'][outro_idx]['visual'] = 'brand_outro'
    restored_sb['scenes'][outro_idx]['visual_assets'] = sb_orig['scenes'][outro_idx]['visual_assets']
    write_yaml_atomic(sb_path, restored_sb)
    pr.check_repair(project, before_restore)
    pr.finalize_product_repair(project, before_restore)

    tamper_sb = read_yaml(sb_path)
    tamper_sb['scenes'][outro_idx]['narration'] = 'Doi loi ket trai phep'
    write_yaml_atomic(sb_path, tamper_sb)
    with pytest.raises(ValueError, match='Repair scope violation'):
        pr.check_repair(project, before_restore)
    write_yaml_atomic(sb_path, restored_sb)

    script_path = rev / 'script/script.yaml'
    orig_script = script_path.read_bytes()
    script_path.write_bytes(orig_script + b'\n# tamper\n')
    with pytest.raises(ValueError, match='medical artifact is locked'):
        pr.check_repair(project, before_restore)
    script_path.write_bytes(orig_script)


def test_check_repair_rejects_orphaning_manifest_visual_asset(tmp_path):
    project = _approved_production_project(tmp_path)
    rev = project / REV
    sb_path = rev / 'storyboard/storyboard.yaml'
    sb = read_yaml(sb_path)
    manifest_assets = {a['path'] for a in read_yaml(rev / 'assets/asset-manifest.yaml')['assets']}
    ref_counts: dict[str, int] = {}
    for s in sb['scenes']:
        for ref in s.get('visual_assets') or ():
            ref_counts[ref['path']] = ref_counts.get(ref['path'], 0) + 1
    target_scene, removed_path = next(
        (s, ref['path'])
        for s in sb['scenes']
        for ref in (s.get('visual_assets') or ())
        if ref['path'] in manifest_assets and ref_counts[ref['path']] == 1
    )
    target_sid = target_scene['id']

    _report(
        project,
        scores={**dict.fromkeys(pr.CRITERIA, 8), 'nhip_dung': 5},
        issues=[{
            'at': target_sid,
            'criterion': 'nhip_dung',
            'problem': 'Anh de chu.',
            'fix': 'Chinh bo cuc.',
            'fixable': True,
        }],
    )
    pr.record_review(project, pr.render_hash(project))
    before = pr.repair_files(project)

    edited_sb = read_yaml(sb_path)
    for scene in edited_sb['scenes']:
        if scene['id'] == target_sid:
            scene['visual_assets'] = [
                ref for ref in scene['visual_assets'] if ref['path'] != removed_path
            ]
    write_yaml_atomic(sb_path, edited_sb)

    with pytest.raises(
        ValueError,
        match=f'visual asset is not referenced by storyboard: {removed_path}',
    ):
        pr.check_repair(project, before)
