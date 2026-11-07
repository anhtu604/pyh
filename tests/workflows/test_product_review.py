"""Product critic scores the final cut; fixable faults are fixed and re-rendered before the doctor."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from healthvideo.agents import AgentCli, AgentResult
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.queue import add_to_queue
from healthvideo.workflows import product_review as pr
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.produce import submit_video
from healthvideo.workflows.runner import RunDeps, run_queue
from tests.helpers import create_v2_project_fixture

SLUG = 'muoi-va-huyet-ap-v2'
WRITER, CRITIC = AgentCli('writer', ('w',), True), AgentCli('critic', ('c',), True)
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


def test_unchanged_render_after_fix_or_unfixable_faults_go_to_doctor(tmp_path):
    project = _project(tmp_path)
    _review(project, 5)
    pr.mark_fix_attempted(project)
    assert pr.next_product_action(project) == 'submit_video'

    other = _project(tmp_path / 'b')
    _review(other, 5, fixable=False)
    assert pr.next_product_action(other) == 'submit_video'
    assert 'cần bác sĩ mở cổng y khoa' in pr.review_view(other / REV)['issues'][0]['fix']


def test_rounds_are_bounded_and_reset_after_submission(tmp_path):
    project = _project(tmp_path)
    for version in range(pr.MAX_REVIEWS):
        _render(project, version + 10)
        _review(project, 5)
    assert pr.next_product_action(project) == 'submit_video'
    pr.mark_submitted(project / REV)
    assert not pr.pending(project)
    _render(project, 99)
    assert pr.next_product_action(project) == 'product_review'
    assert pr.review_view(project / REV)['round'] == pr.MAX_REVIEWS


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

    def invoke(agents, prompt, *, cwd, log_dir):
        del cwd
        log_dir.mkdir(parents=True, exist_ok=True)
        reviewing = '(`product_review`)' in prompt
        calls.append((agents[0].name, 'review' if reviewing else 'fix'))
        if reviewing:
            _report(project, 6 if len(calls) == 1 else 8)
        else:
            assert '(`revise_product`)' in prompt
            assert 'Thu nhỏ nhãn.' in prompt
        return AgentResult(agents[0].name, True, False, log_dir / 'fake.log')

    report = run_queue(tmp_path, _deps(project, state, invoke), agents=(WRITER, CRITIC))

    assert calls == [('critic', 'review'), ('writer', 'fix'), ('critic', 'review')]
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

    def invoke(agents, prompt, *, cwd, log_dir):
        del prompt, cwd
        log_dir.mkdir(parents=True, exist_ok=True)
        return AgentResult(agents[0].name, True, False, log_dir / 'fake.log')

    report = run_queue(tmp_path, _deps(project, state, invoke), agents=(WRITER, CRITIC))

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

    submit_video(project)

    assert read_yaml(project / 'project.yaml')['state'] == 'awaiting_video_review'
    assert not pr.pending(project)
    with pytest.raises(ValueError, match='production_in_progress'):
        submit_video(project)


def test_step_agents_override_the_default_order(tmp_path):
    project = _queue(tmp_path)
    state = {'value': WorkflowState.PRODUCTION_IN_PROGRESS, 'renders': 1}
    seen = []
    special = AgentCli('special', ('s',), True)

    def invoke(agents, prompt, *, cwd, log_dir):
        del prompt, cwd
        log_dir.mkdir(parents=True, exist_ok=True)
        seen.append(agents[0].name)
        _report(project, 8)
        return AgentResult(agents[0].name, True, False, log_dir / 'fake.log')

    deps = replace(_deps(project, state, invoke),
                   step_agents={'product_review': (special, CRITIC)})
    run_queue(tmp_path, deps, agents=(WRITER, CRITIC))
    assert seen == ['special']
