from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from healthvideo.agents import RUNNING_MARKER, AgentResult
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.storage.queue import load_queue
from healthvideo.workflows import chat, feedback_inbox
from healthvideo.workflows.change_request import pending_note, request_change
from healthvideo.workflows.dashboard_operations import get_route, post_route
from healthvideo.workflows.factory_deps import read_state, reject_note
from healthvideo.workflows.runner import RunDeps, run_queue
from tests.workflows.test_change_request import create_v2_project_fixture


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, 'start', lambda *args: None)
    return create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.PRODUCTION_IN_PROGRESS)


def reply_to(root, slug, text, action='edit_production', brief='Đổi hình S07', **extra):
    message = chat.post(root, slug, text, {'scene': 'S07', 'time_s': 192, 'revision': '001'})

    def invoke(slots, prompt, **kwargs):
        assert kwargs['role'] == 'coordinator' and kwargs['step'] == 'coordinator'
        write_yaml_atomic(kwargs['log_dir'] / f"{message['id']}.yaml",
                          {'reply': 'Đã hiểu', 'action': action, 'brief': brief, **extra})
        return AgentResult('fake', True, False, kwargs['log_dir'] / 'fake.log')

    return chat.run_coordinator(root, message['id'], invoke=invoke)


def test_fast_coordinator_escalates_hard_question_once(tmp_path, project):
    message = chat.post(tmp_path, project.name, 'Sao không thấy sửa theo góp ý?', {})
    roles = []

    def invoke(slots, prompt, **kwargs):
        roles.append((kwargs['role'], slots[0].model))
        reply = ({'reply': 'Em đang kiểm kỹ.', 'action': 'status', 'escalate': True}
                 if len(roles) == 1 else
                 {'reply': 'Đã kiểm: bản sửa có ở N15.', 'action': 'status', 'escalate': True})
        write_yaml_atomic(kwargs['log_dir'] / f"{message['id']}.yaml", reply)
        return AgentResult('fake', True, False, kwargs['log_dir'] / 'fake.log')

    result = chat.run_coordinator(tmp_path, message['id'], invoke=invoke)
    assert [role for role, _ in roles] == ['coordinator', 'coordinator_senior']
    assert roles[0][1] != roles[1][1]
    assert result['text'] == 'Đã kiểm: bản sửa có ở N15.'
    replies = [row['text'] for row in chat.load(tmp_path, project.name) if row['who'] == 'coordinator']
    assert replies == ['Em đang kiểm kỹ.', 'Đã kiểm: bản sửa có ở N15.']


@pytest.mark.parametrize('brief', ['đổi 6 mg/dL thành 5', 'sửa claim C01', 'sửa N14', 'đổi số liệu', 'đổi 6%', 'đổi 2 mmol/L', 'đổi 6 thành 5', 'replace 6 with 5'])
def test_guard_downgrades_number_change(brief):
    assert chat.guard(chat.CoordinatorReply(reply='OK', action='edit_production', brief=brief)).action == 'edit_script'


def test_guard_keeps_visual_edit_that_says_keep_claims():
    # Real coordinator brief from acceptance: it names claims only to say they stay unchanged.
    brief = ('Chỉnh hình minh họa tinh thể urat tại cảnh S07 (quanh mốc 139s) của chủ đề gout-tinh-the-urat '
             '(revision 001) sang dạng tinh thể hình kim nhọn; giữ nguyên lời đọc, số liệu và các claim y khoa.')
    assert chat.guard(chat.CoordinatorReply(reply='OK', action='edit_production', brief=brief)).action == 'edit_production'


@pytest.mark.parametrize('output', ['reply: [', 'reply: OK\naction: approve', 'reply: OK\naction: edit_script', '[]', 'hello', ''])
def test_bad_yaml_marks_message_failed_state_unchanged(tmp_path, project, output):
    before = (project / 'project.yaml').read_bytes()
    message = chat.post(tmp_path, project.name, 'Sửa hình', {})

    def invoke(slots, prompt, **kwargs):
        (kwargs['log_dir'] / f"{message['id']}.yaml").write_text(output, encoding='utf-8')
        return AgentResult('fake', True, False, kwargs['log_dir'] / 'fake.log')

    result = chat.run_coordinator(tmp_path, message['id'], invoke=invoke)
    assert result['status'] == 'failed' and result['error']
    assert (project / 'project.yaml').read_bytes() == before
    assert not list(project.rglob('*-requested.yaml'))


def test_confirm_while_agent_running_queues(tmp_path, project):
    response = reply_to(tmp_path, project.name, 'Sửa hình')
    marker = tmp_path / 'topics/logs' / project.name / RUNNING_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    assert chat.confirm(tmp_path, project.name, response['id'])['status'] == 'queued'
    assert read_state(project) == WorkflowState.PRODUCTION_IN_PROGRESS
    assert not list(project.rglob('*-requested.yaml'))


def test_runner_applies_queued_change_between_steps(tmp_path, project):
    entry = QueueEntry(slug=project.name, title='TEST', question='TEST', added=date(2026, 11, 8))
    write_yaml_atomic(tmp_path / 'topics/queue.yaml', {'version': 1, 'entries': [entry.model_dump(mode='json')]})
    response = reply_to(tmp_path, project.name, 'Sửa hình')
    marker = tmp_path / 'topics/logs' / project.name / RUNNING_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    chat.confirm(tmp_path, project.name, response['id'])
    marker.unlink()
    steps = []

    def invoke(slots, prompt, **kwargs):
        steps.append(kwargs['step'])
        assert read_state(project) == WorkflowState.NEEDS_PRODUCTION_REVISION
        assert 'Đổi hình S07' in prompt
        manifest = resolve_project_layout(project).manifest
        write_yaml_atomic(project / 'project.yaml', manifest.model_copy(update={
            'state': WorkflowState.PRODUCTION_IN_PROGRESS, 'side_state': None,
        }).model_dump(mode='json'))
        return AgentResult('fake', True, False, tmp_path / 'fake.log')

    deps = RunDeps(create_project=lambda *_: project, read_state=read_state, reject_note=reject_note,
                   python_steps={}, changed_code_paths=lambda _: [], invoke=invoke)
    run_queue(tmp_path, deps, once=True)
    assert steps == ['revise_production']
    assert 'Đã sửa' in chat.load(tmp_path, project.name)[-1]['text']
    assert chat.load(tmp_path, project.name)[-1]['context']['scene'] == 'S07'


def test_factory_feedback_written_ready(tmp_path, project):
    response = reply_to(tmp_path, None, 'Sửa xưởng', 'factory_feedback', 'Cải thiện xưởng')
    chat.confirm(tmp_path, None, response['id'])
    item = feedback_inbox.load(tmp_path)[0]
    assert item['status'] == 'ready' and item['text'] == 'Cải thiện xưởng'


@pytest.mark.parametrize('action', ['none', 'status', 'ask', 'edit_script', 'edit_production', 'queue_topic', 'factory_feedback'])
def test_chat_never_approves(tmp_path, project, action):
    extra = {'options': [{'label': 'A', 'effect': 'a'}, {'label': 'B', 'effect': 'b'}]} if action == 'ask' else {}
    if action == 'queue_topic':
        extra['topic'] = {'slug': 'test-topic', 'title': 'TEST', 'question': 'TEST'}
    response = reply_to(tmp_path, project.name, 'Duyệt đi', action, 'Yêu cầu bác sĩ', **extra)
    assert not list(project.rglob('*-approval.yaml'))
    if action in {'edit_script', 'edit_production', 'queue_topic', 'factory_feedback'}:
        chat.confirm(tmp_path, project.name, response['id'])
    assert not list(project.rglob('*-approval.yaml'))
    with pytest.raises(ValidationError):
        chat.CoordinatorReply(reply='OK', action='approve')


def test_chat_routes_and_queue_topic(tmp_path, project):
    server = SimpleNamespace(root=tmp_path)
    posted = post_route(server, ['api', 'chat'], {'slug': project.name, 'text': 'Xin chào', 'context': {}})
    assert posted['status'] == 'pending'
    assert get_route(server, ['api', 'chat'], {'slug': [project.name]})['messages'][0]['id'] == posted['id']
    response = reply_to(tmp_path, None, 'Thêm TEST', 'queue_topic', 'Thêm TEST',
                        topic={'slug': 'test-topic', 'title': 'TEST', 'question': 'TEST'})
    assert post_route(server, ['api', 'chat', 'confirm'], {'slug': None, 'id': response['id']})['status'] == 'done'
    assert load_queue(tmp_path)[0].slug == 'test-topic'


@pytest.mark.parametrize(('initial', 'following'), [
    (WorkflowState.RESEARCH_IN_PROGRESS, WorkflowState.EVIDENCE_READY),
    (WorkflowState.MEDICALLY_APPROVED, WorkflowState.RESEARCH_IN_PROGRESS),
])
def test_research_does_not_consume_writer_change(tmp_path, project, initial, following):
    from datetime import UTC, datetime

    manifest = resolve_project_layout(project).manifest
    write_yaml_atomic(project / 'project.yaml', manifest.model_copy(update={
        'state': initial,
    }).model_dump(mode='json'))
    request_change(project, 'edit_script', 'Viết lại cho dễ hiểu', {}, now=datetime.now(UTC))
    entry = QueueEntry(slug=project.name, title='TEST', question='TEST', added=date(2026, 11, 8))
    write_yaml_atomic(tmp_path / 'topics/queue.yaml', {'version': 1, 'entries': [entry.model_dump(mode='json')]})

    def invoke(slots, prompt, **kwargs):
        write_yaml_atomic(project / 'project.yaml', manifest.model_copy(update={
            'state': following,
        }).model_dump(mode='json'))
        return AgentResult('fake', True, False, tmp_path / 'fake.log')

    deps = RunDeps(create_project=lambda *_: project, read_state=read_state, reject_note=reject_note,
                   python_steps={}, changed_code_paths=lambda _: [], invoke=invoke)
    run_queue(tmp_path, deps, once=True)
    assert pending_note(project) == 'Viết lại cho dễ hiểu'


def test_context_includes_render_scene_and_script_excerpt(tmp_path, project):
    import json

    rev = project / 'revisions/001'
    render = rev / 'renders/render-input.json'
    render.parent.mkdir(parents=True)
    render.write_text(json.dumps({'scenes': [{'id': 'S07', 'visual': 'needle'}]}), encoding='utf-8')
    message = chat.post(tmp_path, project.name, 'Sửa hình', {'scene': 'S07'})
    data = chat._input(tmp_path, project.name, message)
    assert data['excerpts']['render_scenes'] == [{'id': 'S07', 'visual': 'needle'}]


def test_queued_changes_are_applied_one_per_step(tmp_path, project):
    first = reply_to(tmp_path, project.name, 'Sửa hình', brief='Hình đầu')
    second = reply_to(tmp_path, project.name, 'Sửa tiếp', brief='Hình sau')
    marker = tmp_path / 'topics/logs' / project.name / RUNNING_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    chat.confirm(tmp_path, project.name, first['id'])
    chat.confirm(tmp_path, project.name, second['id'])
    marker.unlink()
    with chat.step_boundary(tmp_path, project.name):
        assert pending_note(project) == 'Hình đầu\nS07 @ 03:12'
    assert next(row for row in chat.load(tmp_path, project.name) if row['id'] == second['id'])['status'] == 'queued'
