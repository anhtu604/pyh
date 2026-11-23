"""Tests for the doctor question gate outside formal medical/video approvals."""

from __future__ import annotations

import json
import threading
from datetime import date
from http.client import HTTPConnection
from pathlib import Path

import pytest

from healthvideo.agents import AgentResult
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.queue import add_to_queue
from healthvideo.workflows import (
    chat,
    dashboard,
    dashboard_operations,
    doctor_questions,
    factory,
    standards,
)
from healthvideo.workflows import product_review as pr
from healthvideo.workflows import script_review as sr
from healthvideo.workflows.runner import RunDeps, run_queue
from tests.helpers import create_v2_project_fixture

SLUG = 'muoi-va-huyet-ap-v2'
REV = Path('revisions/001')


def _sample_options() -> list[dict[str, str]]:
    return [
        {'id': 'opt_a', 'label': 'Phương án A', 'detail': 'Đề xuất chính'},
        {'id': 'opt_b', 'label': 'Phương án B', 'detail': 'Phương án phụ'},
    ]


def test_ask_creates_atomically_truncates_context_and_deduplicates(tmp_path: Path) -> None:
    long_desc = 'Mô tả dài ' * 40
    q1 = doctor_questions.ask(
        tmp_path,
        SLUG,
        station='12',
        kind='stuck_issue',
        question='Cần chọn hướng xử lý cảnh S04.',
        context=[{'code': 'PR-01', 'location': 'S04@01:12', 'summary': long_desc}],
        options=_sample_options(),
        allow_free_text=True,
    )
    assert q1['status'] == 'open'
    assert q1['answer'] is None
    assert q1['station'] == '12'
    assert q1['kind'] == 'stuck_issue'
    assert len(q1['context']) == 1
    assert len(q1['context'][0]['summary']) <= doctor_questions.MAX_SUMMARY_CHARS
    assert doctor_questions.open_question(tmp_path, SLUG) == q1

    # Duplicate open question with same kind + station returns the original without overwriting.
    q2 = doctor_questions.ask(
        tmp_path,
        SLUG,
        station='12',
        kind='stuck_issue',
        question='Câu hỏi mới không được ghi đè.',
        context=[],
        options=_sample_options(),
        allow_free_text=False,
    )
    assert q2['id'] == q1['id']
    assert q2['question'] == q1['question']
    assert doctor_questions.open_question(tmp_path, SLUG)['id'] == q1['id']


def test_ask_rejects_invalid_slug_and_options(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match='Slug'):
        doctor_questions.ask(
            tmp_path, '../escape', station='12', kind='free', question='Test?', options=_sample_options()
        )
    with pytest.raises(ValueError, match='2 đến 4'):
        doctor_questions.ask(
            tmp_path, SLUG, station='12', kind='free', question='Test?',
            options=[{'id': 'only_one', 'label': 'Một lựa chọn', 'detail': ''}],
        )


def test_answer_valid_wrong_id_and_duplicate(tmp_path: Path) -> None:
    q = doctor_questions.ask(
        tmp_path,
        SLUG,
        station='12',
        kind='stuck_issue',
        question='Chọn hướng sửa hình?',
        context=[{'code': 'PR-01', 'location': 'S02', 'summary': 'Nhãn nhỏ'}],
        options=_sample_options(),
        allow_free_text=True,
    )

    with pytest.raises(ValueError, match='không khớp'):
        doctor_questions.answer(tmp_path, SLUG, 'wrong-id', 'opt_a', '')
    assert doctor_questions.open_question(tmp_path, SLUG)['id'] == q['id']

    with pytest.raises(ValueError, match='không hợp lệ'):
        doctor_questions.answer(tmp_path, SLUG, q['id'], 'nonexistent', '')
    assert doctor_questions.open_question(tmp_path, SLUG)['id'] == q['id']

    answered = doctor_questions.answer(tmp_path, SLUG, q['id'], 'opt_a', 'Ưu tiên rõ chữ')
    assert answered['status'] == 'answered'
    assert answered['answer']['option_id'] == 'opt_a'
    assert answered['answer']['text'] == 'Ưu tiên rõ chữ'
    assert doctor_questions.open_question(tmp_path, SLUG) is None
    assert not doctor_questions.question_path(tmp_path, SLUG).exists()

    hist = doctor_questions.history(tmp_path, SLUG)
    assert len(hist) == 1
    assert hist[0]['id'] == q['id']
    assert hist[0]['status'] == 'answered'

    # Answering the same question again fails cleanly and does not duplicate history.
    with pytest.raises(ValueError, match='đã được trả lời'):
        doctor_questions.answer(tmp_path, SLUG, q['id'], 'opt_a', '')
    assert len(doctor_questions.history(tmp_path, SLUG)) == 1


def test_product_review_stuck_creates_question_and_respects_blocking_safety(tmp_path: Path) -> None:
    from tests.workflows.test_product_review import _project, _render, _report

    # Case 1: all open issues have blocking_safety=False -> includes 3rd accept option.
    root_safe = tmp_path / 'safe'
    project = _project(root_safe)
    issue = {
        'issue_id': 'PR-01',
        'at': 'S02',
        'criterion': 'hinh_ro',
        'problem': 'Nhãn hơi nhỏ.',
        'fix': 'Tăng cỡ chữ.',
        'fixable': True,
        'blocking_safety': False,
    }
    scores = dict.fromkeys(pr.CRITERIA, 8) | {'hinh_ro': 6}
    for version in (1, 2):
        _render(project, version)
        _report(project, scores=scores, issues=[issue])
        pr.record_review(project, pr.render_hash(project))

    assert pr.next_product_action(project, root=root_safe) == 'wait_doctor'
    q = doctor_questions.open_question(root_safe, project.name)
    assert q is not None
    assert q['station'] == '12'
    assert q['kind'] == 'stuck_issue'
    labels = [opt['label'] for opt in q['options']]
    assert labels == [
        'Sửa hình các cảnh bị nêu',
        'Tách cảnh dài',
        'Chấp nhận như hiện tại và nộp bác sĩ duyệt video',
    ]

    # Case 2: an open issue has blocking_safety=True -> omits the 3rd accept option.
    root_unsafe = tmp_path / 'unsafe'
    project2 = _project(root_unsafe)
    unsafe_issue = {**issue, 'issue_id': 'PR-99', 'blocking_safety': True}
    for version in (1, 2):
        _render(project2, version)
        _report(project2, scores=scores, issues=[unsafe_issue])
        pr.record_review(project2, pr.render_hash(project2))

    assert pr.next_product_action(project2, root=root_unsafe) == 'wait_doctor'
    q2 = doctor_questions.open_question(root_unsafe, project2.name)
    assert q2 is not None
    assert [opt['label'] for opt in q2['options']] == [
        'Sửa hình các cảnh bị nêu',
        'Tách cảnh dài',
    ]

    # Real errors (non-fixable issue on first round) still raise ValueError.
    root_err = tmp_path / 'err'
    project3 = _project(root_err)
    _report(project3, score=5, fixable=False)
    pr.record_review(project3, pr.render_hash(project3))
    with pytest.raises(ValueError, match='vượt phạm vi thợ dựng'):
        pr.next_product_action(project3, root=root_err)


def test_runner_and_factory_skip_open_question_without_blocked_txt(tmp_path: Path, monkeypatch) -> None:
    from tests.workflows.test_product_review import _project, _render, _report

    add_to_queue(tmp_path, QueueEntry(
        slug=SLUG, title='Muối và huyết áp', question='Ăn mặn?', added=date(2026, 11, 20),
    ))
    project = _project(tmp_path)
    issue = {
        'issue_id': 'PR-01',
        'at': 'S02',
        'criterion': 'hinh_ro',
        'problem': 'Nhãn nhỏ.',
        'fix': 'Phóng to.',
        'fixable': True,
    }
    scores = dict.fromkeys(pr.CRITERIA, 8) | {'hinh_ro': 6}
    for version in (1, 2):
        _render(project, version)
        _report(project, scores=scores, issues=[issue])
        pr.record_review(project, pr.render_hash(project))

    invoked = []
    deps = RunDeps(
        create_project=lambda root, entry: project,
        read_state=lambda _: WorkflowState.PRODUCTION_IN_PROGRESS,
        reject_note=lambda _: None,
        python_steps={'produce': lambda _: invoked.append('produce')},
        changed_code_paths=lambda _: [],
        invoke=lambda *a, **k: (invoked.append('agent') or AgentResult('claude', True, False, tmp_path / 'x.log')),
        posts_ready=lambda _: True,
        shorts_plan_ready=lambda _: True,
        visual_review_pending=lambda _: False,
        product_review_pending=lambda _: True,
    )

    report = run_queue(tmp_path, deps, once=False)
    assert project.name in report.waiting_doctor
    assert project.name not in report.blocked
    assert invoked == []
    assert not (tmp_path / 'topics/logs' / project.name / 'blocked.txt').exists()
    assert not (tmp_path / 'topics/logs' / project.name / 'agent-retry.yaml').exists()
    assert doctor_questions.open_question(tmp_path, project.name) is not None

    # Subsequent factory pass skips cleanly, logs waiting line, and never writes blocked.txt.
    announced: list[tuple[str, str]] = []
    echoed: list[str] = []
    factory.run_factory(
        tmp_path,
        deps,
        once=True,
        notify=lambda title, event: announced.append((title, event)) or True,
        echo=echoed.append,
    )
    assert not (tmp_path / 'topics/logs' / project.name / 'blocked.txt').exists()
    assert any('chờ ý kiến bác sĩ:' in line for line in echoed)
    assert any(event.startswith('chờ ý kiến bác sĩ:') for _, event in announced)

    # _editable allows editing while factory is running when a doctor question is open.
    monkeypatch.setattr(factory, 'running_pid', lambda _: 99999)
    layout = dashboard_operations._editable(tmp_path, project.name, '001')
    assert layout.manifest.active_revision == '001'


def test_dashboard_answer_question_endpoint(tmp_path: Path, monkeypatch) -> None:
    project = create_v2_project_fixture(tmp_path / 'projects')
    monkeypatch.setattr(chat, 'start', lambda root, msg_id: None)

    q = doctor_questions.ask(
        tmp_path,
        project.name,
        station='12',
        kind='stuck_issue',
        question='Trạm 12 kẹt 2 vòng ở S04.',
        context=[{'code': 'PR-01', 'location': 'S04', 'summary': 'Chữ hơi nhỏ'}],
        options=_sample_options(),
        allow_free_text=True,
    )
    before_manifest = read_yaml(project / 'project.yaml')

    server = dashboard.DashboardServer(tmp_path, 0, token='tok-test')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        def post(path: str, payload: dict, *, token: str = 'tok-test') -> tuple[int, dict]:
            conn = HTTPConnection('127.0.0.1', port, timeout=5)
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['X-Dashboard-Token'] = token
            conn.request('POST', path, body=json.dumps(payload).encode('utf-8'), headers=headers)
            resp = conn.getresponse()
            body = json.loads(resp.read().decode('utf-8'))
            conn.close()
            return resp.status, body

        endpoint = f'/api/project/{project.name}/answer-question'

        # Missing CSRF token -> 403
        status, _ = post(endpoint, {'question_id': q['id'], 'option_id': 'opt_a', 'expected_revision': '001'}, token='')
        assert status == 403

        # PIN is never accepted -> 400
        status, body = post(endpoint, {
            'question_id': q['id'], 'option_id': 'opt_a', 'expected_revision': '001', 'pin': '1234',
        })
        assert status == 400
        assert 'PIN' in body['error']

        # Wrong question_id -> 400, nothing mutated
        status, _ = post(endpoint, {
            'question_id': 'wrong-id', 'option_id': 'opt_a', 'text': '', 'expected_revision': '001',
        })
        assert status == 400
        assert doctor_questions.open_question(tmp_path, project.name) is not None

        # Wrong revision -> 400
        status, _ = post(endpoint, {
            'question_id': q['id'], 'option_id': 'opt_a', 'text': '', 'expected_revision': '999',
        })
        assert status == 400

        # Valid answer -> 200, writes chat + standard + history, clears open file, keeps project.yaml untouched.
        status, body = post(endpoint, {
            'question_id': q['id'],
            'option_id': 'opt_a',
            'text': 'Tăng cỡ chữ thêm 20%',
            'expected_revision': '001',
        })
        assert status == 200
        assert body['ok'] is True
        assert body['answered']['status'] == 'answered'
        assert doctor_questions.open_question(tmp_path, project.name) is None
        assert len(doctor_questions.history(tmp_path, project.name)) == 1

        messages = chat.load(tmp_path, project.name)
        assert len(messages) == 1
        assert 'Quyết định Trạm 12: Phương án A. Tăng cỡ chữ thêm 20%' in messages[0]['text']

        std_entries = standards.load(tmp_path)
        assert len(std_entries) == 1
        assert std_entries[0]['kind'] == 'comment'
        assert 'Phương án A' in std_entries[0]['text']

        assert read_yaml(project / 'project.yaml') == before_manifest
        assert not (project / REV / 'reviews/video-approval.yaml').exists()

        # Duplicate answer -> 400, no extra chat or history entry.
        status, _ = post(endpoint, {
            'question_id': q['id'], 'option_id': 'opt_a', 'text': '', 'expected_revision': '001',
        })
        assert status == 400
        assert len(chat.load(tmp_path, project.name)) == 1
        assert len(doctor_questions.history(tmp_path, project.name)) == 1
    finally:
        server.shutdown()
        server.server_close()


def test_script_review_stuck_creates_question_while_cycle_limit_still_raises(tmp_path: Path) -> None:
    from tests.workflows.test_script_review import _project, _report

    project = _project(tmp_path)
    issue = {'issue_id': 'S1', 'line': 'N01', 'criterion': 'ca_tinh', 'problem': 'Cứng.', 'fix': 'Mềm hơn.'}
    scores = dict.fromkeys(sr.CRITERIA, 8) | {'ca_tinh': 6}
    _report(project, scores=scores, issues=[issue])
    sr.record_review(project, sr.script_hash(project))
    _report(project, scores=scores, issues=[issue])
    sr.record_review(project, sr.script_hash(project))

    assert sr.next_script_action(project, root=tmp_path) == 'wait_doctor'
    q = doctor_questions.open_question(tmp_path, project.name)
    assert q is not None
    assert q['station'] == '07'
    assert q['kind'] == 'stuck_issue'

    # Non-stuck cycle limit still raises ValueError.
    root2 = tmp_path / 'cycle'
    project2 = _project(root2)
    log_path = project2 / REV / sr.LOG
    write_yaml_atomic(log_path, {
        'version': 1,
        'cycles': sr.MAX_CYCLES,
        'submitted': 0,
        'cycle_start': 0,
        'rounds': [
            {
                'round': 1, 'script_sha256': sr.script_hash(project2), 'passed': False,
                'scores': scores, 'summary': 'R1', 'issues': [issue], 'issue_statuses': {'S1': 'resolved'},
            },
            {
                'round': 2, 'script_sha256': sr.script_hash(project2), 'passed': False,
                'scores': scores, 'summary': 'R2',
                'issues': [{**issue, 'issue_id': 'S2'}], 'issue_statuses': {'S2': 'still_open'},
            },
        ],
    })
    with pytest.raises(ValueError, match=sr.CYCLE_LIMIT_REASON):
        sr.next_script_action(project2, root=root2)


def test_fingerprint_dedup_and_supersede(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    q1 = doctor_questions.ask(
        tmp_path,
        SLUG,
        station='12',
        kind='stuck_issue',
        question='Trạm 12 kẹt.',
        context=[{'code': 'PR-04', 'location': 'S08', 'summary': 'Cũ'}],
        options=_sample_options(),
        fingerprint='fp-round-2',
    )
    answered = doctor_questions.answer(
        tmp_path, SLUG, q1['id'], None, 'Dựng lại rồi chấm: từ đầu',
        now=datetime(2026, 11, 21, 16, 57, tzinfo=UTC),
    )
    assert doctor_questions.answered_for_fingerprint(tmp_path, SLUG, 'fp-round-2')['id'] == q1['id']

    # Re-asking with the same fingerprint does not reopen doctor-question.yaml.
    reasked = doctor_questions.ask(
        tmp_path,
        SLUG,
        station='12',
        kind='stuck_issue',
        question='Trạm 12 kẹt.',
        context=[{'code': 'PR-04', 'location': 'S08', 'summary': 'Cũ'}],
        options=_sample_options(),
        fingerprint='fp-round-2',
    )
    assert reasked['id'] == q1['id']
    assert doctor_questions.open_question(tmp_path, SLUG) is None

    # Legacy history matching by station+kind+context respects min_answered_at.
    dup = doctor_questions.ask(
        tmp_path,
        SLUG,
        station='12',
        kind='stuck_issue',
        question='Trạm 12 kẹt.',
        context=[{'code': 'PR-04', 'location': 'S08', 'summary': 'Cũ'}],
        options=_sample_options(),
    )
    assert doctor_questions.has_matching_answered_history(
        tmp_path, SLUG, dup, min_answered_at=datetime(2026, 11, 21, 13, 0, tzinfo=UTC),
    )['id'] == answered['id']
    assert doctor_questions.has_matching_answered_history(
        tmp_path, SLUG, dup, min_answered_at=datetime(2026, 11, 21, 18, 0, tzinfo=UTC),
    ) is None

    archived = doctor_questions.supersede(tmp_path, SLUG, reason='medical_approval_newer')
    assert archived is not None and archived['status'] == 'superseded'
    assert doctor_questions.open_question(tmp_path, SLUG) is None
    assert doctor_questions.history(tmp_path, SLUG)[-1]['superseded_reason'] == 'medical_approval_newer'


def test_supersede_kind_only_clears_matching_kind(tmp_path: Path) -> None:
    q_stuck = doctor_questions.ask(
        tmp_path, SLUG, station='12', kind='stuck_issue',
        question='Trạm 12 kẹt.', options=_sample_options(),
    )
    assert doctor_questions.supersede_kind(tmp_path, SLUG, 'escalation', reason='noop') is None
    assert doctor_questions.open_question(tmp_path, SLUG)['id'] == q_stuck['id']
    doctor_questions.supersede(tmp_path, SLUG, reason='clear')

    q_esc = doctor_questions.ask(
        tmp_path, SLUG, station='repair', kind='escalation',
        question='Cần chỉ đạo sửa lỗi.', options=_sample_options(), fingerprint='esc-1',
    )
    cleared = doctor_questions.supersede_kind(tmp_path, SLUG, 'escalation', reason='resolved')
    assert cleared is not None and cleared['id'] == q_esc['id']
    assert doctor_questions.open_question(tmp_path, SLUG) is None
