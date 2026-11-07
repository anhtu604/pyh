"""Doctor opinions become validated work items; failures stay visible and retryable."""

import pytest

from healthvideo.agents import AgentCli, AgentResult, AllAgentsExhausted
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import dashboard
from healthvideo.workflows import feedback_inbox as inbox

CODEX, AGY = AgentCli('codex', ('c',), True), AgentCli('agy', ('a',), True)
TASK = {'kind': 'xuong', 'target': 'prompts/draft.md', 'request': 'Bớt rào đón.',
        'done_when': 'Không còn cụm rào đón.'}


def _invoke(report, *, ok=True):
    def invoke(agents, prompt, *, cwd, log_dir):
        invoke.agents, invoke.prompt, invoke.cwd = agents, prompt, cwd
        if report is not None:
            write_yaml_atomic(log_dir / invoke.name, report)
        return AgentResult(agents[0].name, ok, False, log_dir / 'fake.log')
    return invoke


def _run(root, report, *, ok=True, text='Giọng nghe như đọc biên bản.'):
    entry = inbox.add(root, 'gout', text)
    invoke = _invoke(report, ok=ok)
    invoke.name = f"{entry['id']}.yaml"
    inbox.analyze(root, entry['id'], invoke=invoke, agents=(AGY, CODEX))
    return invoke, inbox.view(root)[0]


def test_analysis_is_stored_as_ready_work_for_claude(tmp_path):
    invoke, entry = _run(tmp_path, {'summary': 'Giọng máy móc.', 'tasks': [TASK]})
    assert entry['status'] == 'ready'
    assert entry['analysis']['tasks'] == [TASK]
    assert entry['project'] == 'gout'
    assert invoke.agents[0].name == 'agy'
    assert 'Giọng nghe như đọc biên bản.' in invoke.prompt
    assert invoke.cwd == tmp_path
    assert not list((tmp_path / inbox.REPORT_DIR).glob('*.yaml'))
    assert read_yaml(tmp_path / inbox.FEEDBACK_FILE)['entries'][0]['status'] == 'ready'


@pytest.mark.parametrize(('report', 'ok', 'message'), [
    (None, True, 'chưa ghi báo cáo'),
    ({'summary': 'x', 'tasks': []}, True, 'tasks'),
    ({'summary': 'x', 'tasks': [TASK | {'kind': 'la'}]}, True, 'kind'),
    ({'summary': 'x', 'tasks': [TASK]}, False, 'không phân tích được'),
])
def test_bad_analysis_fails_visibly_then_retry_succeeds(tmp_path, report, ok, message):
    _, entry = _run(tmp_path, report, ok=ok)
    assert entry['status'] == 'failed'
    assert message in entry['error']
    assert entry['analysis'] is None

    assert inbox.retry(tmp_path, entry['id'])['status'] == 'analyzing'
    invoke = _invoke({'summary': 'Ổn.', 'tasks': [TASK]})
    invoke.name = f"{entry['id']}.yaml"
    inbox.analyze(tmp_path, entry['id'], invoke=invoke, agents=(CODEX, AGY))
    assert inbox.view(tmp_path)[0]['status'] == 'ready'


def test_quota_exhaustion_is_retryable(tmp_path):
    entry = inbox.add(tmp_path, 'chung', 'Thêm nhạc.')

    def invoke(agents, prompt, *, cwd, log_dir):
        raise AllAgentsExhausted('hết hạn mức')

    inbox.analyze(tmp_path, entry['id'], invoke=invoke, agents=(CODEX, AGY))
    assert inbox.view(tmp_path)[0]['status'] == 'failed'


def test_analysis_left_by_closed_app_shows_as_failed_and_can_retry(tmp_path):
    entry = inbox.add(tmp_path, 'chung', 'Thêm nhạc.')
    inbox._ACTIVE.discard(entry['id'])
    shown = inbox.view(tmp_path)[0]
    assert shown['status'] == 'failed'
    assert shown['error'] == inbox.ORPHAN_REASON
    assert inbox.retry(tmp_path, entry['id'])['status'] == 'analyzing'
    inbox._ACTIVE.discard(entry['id'])


def test_retry_refuses_running_or_finished_items(tmp_path):
    entry = inbox.add(tmp_path, 'chung', 'Thêm nhạc.')
    with pytest.raises(ValueError, match='đã lỗi'):
        inbox.retry(tmp_path, entry['id'])
    inbox._ACTIVE.discard(entry['id'])
    with pytest.raises(LookupError):
        inbox.retry(tmp_path, 'khong-co')


@pytest.mark.parametrize('text', ['', '   ', 'x' * (inbox.MAX_TEXT + 1)])
def test_empty_or_too_long_opinion_is_refused(tmp_path, text):
    with pytest.raises(ValueError):
        inbox.add(tmp_path, 'chung', text)
    assert inbox.load(tmp_path) == []


def test_app_routes_save_opinion_start_analyst_and_check_project(tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(inbox, 'start', lambda root, entry_id: started.append(entry_id))
    server = dashboard.DashboardServer(tmp_path, 0)
    try:
        message = server.dispatch(['api', 'feedback', 'add'], {'project': '', 'text': 'Thêm nhạc.'})
        assert 'phân tích' in message
        with pytest.raises(LookupError):
            server.dispatch(['api', 'feedback', 'add'], {'project': 'khong-co', 'text': 'x'})
    finally:
        server.server_close()
    entry = inbox.load(tmp_path)[0]
    assert entry['project'] == inbox.GENERAL
    assert started == [entry['id']]
    assert len(inbox.load(tmp_path)) == 1
    inbox._ACTIVE.discard(entry['id'])
