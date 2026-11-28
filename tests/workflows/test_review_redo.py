"""Malformed critic reports get one correction without changing the reviewed input."""

import pytest

from healthvideo.agents import AgentResult
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import product_review, runner, script_review
from tests.helpers import create_v2_project_fixture


@pytest.mark.parametrize('step', ['script_review', 'product_review'])
@pytest.mark.parametrize('repair', ['valid', 'invalid', 'failed', 'changed', 'paused'])
@pytest.mark.parametrize('r5', [False, True])
def test_review_report_gets_only_one_correction(tmp_path, monkeypatch, step, repair, r5):
    project = create_v2_project_fixture(tmp_path / 'projects')
    revision = project / 'revisions/001'
    review = script_review if step == 'script_review' else product_review
    (revision / review.LOG).unlink(missing_ok=True)
    if r5:
        write_yaml_atomic(revision / 'workflow/standards.yaml',
                          {'quality_standard': {'profile': 'r5_v1'}})
    (revision / 'renders').mkdir(exist_ok=True)
    (revision / 'renders/render-manifest.json').write_text('{}', encoding='utf-8')
    criterion = 'nhip_cau' if step == 'script_review' else 'nhip_dung'
    original_hash = (script_review.script_hash(project) if step == 'script_review'
                     else product_review.render_hash(project))
    prompts = []

    def invoke(slots, prompt, **kwargs):
        assert kwargs['step'] == step
        prompts.append(prompt)
        issues = []
        if len(prompts) == 2 and repair in {'valid', 'changed', 'paused'}:
            issues = [{'criterion': criterion, 'problem': 'Nhịp còn chậm.',
                       'fix': 'Rút gọn đoạn này.',
                       **({'line': read_yaml(revision / 'script/script.yaml')['lines'][0]['id']}
                          if step == 'script_review'
                          else {'at': 'S01', 'fixable': True})}]
        write_yaml_atomic(revision / review.REPORT, {
            'scores': {**dict.fromkeys(review.CRITERIA, 8), criterion: 6},
            'summary': 'Nhịp cần sửa.', 'issues': issues,
        })
        if len(prompts) == 2 and repair == 'changed':
            if step == 'script_review':
                script = read_yaml(revision / 'script/script.yaml')
                script['lines'][0]['text'] += ' Nội dung đã thay đổi.'
                write_yaml_atomic(revision / 'script/script.yaml', script)
            else:
                (revision / 'renders/render-manifest.json').write_text('{"changed": true}', encoding='utf-8')
        if len(prompts) == 2 and repair == 'paused':
            (kwargs['log_dir'] / runner.PAUSED_FILE).touch()
        return AgentResult(slots[0].cli, not (len(prompts) == 2 and repair == 'failed'),
                           False, kwargs['log_dir'] / 'fake.log')

    monkeypatch.setattr(runner, 'next_step', lambda _: step)
    deps = runner.RunDeps(
        create_project=lambda *_: project, read_state=lambda _: WorkflowState.DRAFT_READY,
        reject_note=lambda _: None, python_steps={}, invoke=invoke,
        changed_code_paths=lambda _: [], storyboard_ready=lambda _: True,
        voice_prep_ready=lambda _: True,
    )
    entry = QueueEntry(slug=project.name, title='Fixture', question='Fixture?', added='2026-11-28')
    report = runner.RunReport()
    runner._run_topic(tmp_path, deps, entry, report, once=True)

    assert len(prompts) == 2
    assert f'Tiêu chí chưa đạt thiếu chỗ cần sửa: {criterion}' in prompts[1]
    assert 'giữ nguyên nhận định, điểm và lỗi đã ghi' in prompts[1]
    logs = tmp_path / 'topics/logs' / project.name
    if repair == 'paused':
        assert report.blocked == []
        assert not (logs / 'blocked.txt').exists()
        assert not (revision / review.LOG).exists()
    elif repair == 'valid':
        assert report.blocked == []
        assert not (logs / 'blocked.txt').exists()
        rounds = read_yaml(revision / review.LOG)['rounds']
        assert len(rounds) == 1
        assert rounds[0]['passed'] is False
        assert rounds[0]['scores'][criterion] == 6
        assert rounds[0]['script_sha256' if step == 'script_review' else 'render_sha256'] == original_hash
        if r5:
            from healthvideo.workflows.review_budget import review_budget_status

            budget = review_budget_status(revision, 'script' if step == 'script_review' else 'product')
            assert budget['used'] == 2
            assert rounds[0]['budget_event_id'] == budget['events'][-1]['event_id']
    else:
        assert report.blocked == [project.name]
        reason = (logs / 'blocked.txt').read_text(encoding='utf-8')
        assert {'invalid': criterion, 'failed': 'thất bại',
                'changed': 'không được'}[repair] in reason
        assert not (revision / review.LOG).exists()


def test_external_failed_review_is_recorded_without_correction(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects')
    revision = project / 'revisions/001'
    (revision / product_review.LOG).unlink(missing_ok=True)
    write_yaml_atomic(revision / 'workflow/external.yaml', {'production_mode': 'external'})
    (revision / 'renders').mkdir(exist_ok=True)
    (revision / 'renders/render-manifest.json').write_text('{}', encoding='utf-8')
    calls = []

    def require_passed(_):
        raise ValueError('Trạm 12 chưa đạt; chưa được nộp bác sĩ duyệt video.')

    monkeypatch.setattr(product_review, 'require_passed_review', require_passed)

    def invoke(slots, prompt, **kwargs):
        calls.append(kwargs['step'])
        write_yaml_atomic(revision / product_review.REPORT, {
            'scores': {**dict.fromkeys(product_review.CRITERIA, 8), 'nhip_dung': 6},
            'summary': 'Nhịp cần sửa.',
            'issues': [{'at': 'S01', 'criterion': 'nhip_dung', 'problem': 'Nhịp chậm.',
                        'fix': 'Rút gọn đoạn này.', 'fixable': True}],
        })
        return AgentResult(slots[0].cli, True, False, kwargs['log_dir'] / 'fake.log')

    monkeypatch.setattr(runner, 'next_step', lambda _: 'product_review')
    deps = runner.RunDeps(
        create_project=lambda *_: project,
        read_state=lambda _: WorkflowState.PRODUCTION_IN_PROGRESS,
        reject_note=lambda _: None, python_steps={}, invoke=invoke,
        changed_code_paths=lambda _: [],
    )
    entry = QueueEntry(slug=project.name, title='Fixture', question='Fixture?', added='2026-11-28')
    report = runner.RunReport()
    runner._run_topic(tmp_path, deps, entry, report, once=True)

    assert calls == ['product_review']
    assert report.blocked == [project.name]
    rounds = read_yaml(revision / product_review.LOG)['rounds']
    assert len(rounds) == 1 and rounds[0]['passed'] is False
    reason = (tmp_path / 'topics/logs' / project.name / 'blocked.txt').read_text(encoding='utf-8')
    assert 'Trạm 12 chưa đạt' in reason
