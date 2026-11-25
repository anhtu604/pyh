"""Tests for factory playbook: stable signatures, append-only rules, transient backoff, auto-apply, learning, and safety guards."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import (
    change_request,
    chat,
    dashboard,
    doctor_questions,
    factory,
    playbook,
    repair_service,
    review_budget,
)
from tests.helpers import create_v2_project_fixture


def test_repo_seed_playbook_validates_and_matches_known_signatures():
    repo_root = Path(__file__).resolve().parents[2]
    pb = playbook.load_playbook(repo_root)
    assert pb.schema_version == '1.0'
    ids = [r.id for r in playbook.active_rules(pb)]
    assert ids[:3] == ['PB-001', 'PB-002', 'PB-003']

    r1 = playbook.match_rule(
        repo_root,
        station='repair',
        signature=playbook.incident_signature('repair', 'RuntimeError: OA retrieval failed'),
    )
    assert r1 is not None and r1.id == 'PB-001' and r1.delegate_role == 'medical_expert'

    r2 = playbook.match_rule(
        repo_root,
        station='repair',
        signature=playbook.incident_signature('repair', 'Trạm 07 chưa đạt sau 3 chu kỳ (6 vòng)'),
    )
    assert r2 is not None and r2.id == 'PB-002' and r2.delegate_role == 'writer'

    r3 = playbook.match_rule(
        repo_root,
        station='repair',
        signature=playbook.incident_signature('repair', 'Trạm 12 cần hướng dẫn: bố cục brand_outro'),
    )
    assert r3 is not None and r3.id == 'PB-003' and r3.delegate_role == 'editor'


def test_incident_signature_is_stable_across_projects_paths_timestamps_and_counts():
    detail_a = (
        'bước draft lỗi: ValueError: Missing citation at '
        r'E:\Protect Your Health\projects\topic-alpha\revisions\001\script\script.yaml '
        'at 2026-11-24T08:15:30+07:00 hash deadbeef1234 attempt 1 (2/2)\n'
        'log_path: topics/logs/topic-alpha/attempt-1.log\n'
    )
    detail_b = (
        'bước draft lỗi: ValueError: Missing citation at '
        '/workspace/projects/topic-beta/revisions/004/script/script.yaml '
        'at 2026-11-25T21:44:01Z hash cafe98765432 attempt 3 (3/3)\n'
        'log_path: topics/logs/topic-beta/attempt-9.log\n'
    )
    sig_a = playbook.incident_signature('repair', detail_a)
    sig_b = playbook.incident_signature('repair', detail_b)
    assert sig_a == sig_b
    assert 'topic-alpha' not in sig_a
    assert 'deadbeef' not in sig_a

    # Canonical research fulltext signatures match across different phrasings
    assert (
        playbook.incident_signature('repair', 'chưa có evidence/expert-brief.md ở projects/a/revisions/001')
        == playbook.incident_signature('repair', 'RuntimeError: OA retrieval failed\nlog_path: x.log')
    )


def test_playbook_is_append_only_and_disables_turns_off_rule(tmp_path):
    r1 = playbook.append_rule(
        tmp_path,
        source='seed',
        station='repair',
        signature='repair:valueerror:missing_foo',
        action='retry_cycle',
        direction='Thử lại lần đầu.',
        created='2026-11-25',
    )
    assert r1.id == 'PB-001'
    raw_after_1 = read_yaml(playbook.playbook_path(tmp_path))['rules']

    # Adding a duplicate signature rule keeps old entry verbatim and newest rule wins
    r2 = playbook.append_rule(
        tmp_path,
        source='doctor',
        station='repair',
        signature='repair:valueerror:missing_foo',
        action='delegate',
        delegate_role='writer',
        direction='Giao biên kịch sửa phần thiếu.',
        question_id='dq-111',
        slug='topic-a',
        created='2026-11-25',
    )
    assert r2.id == 'PB-002'
    raw_after_2 = read_yaml(playbook.playbook_path(tmp_path))['rules']
    assert raw_after_2[0] == raw_after_1[0]
    matched = playbook.match_rule(tmp_path, station='repair', signature='repair:valueerror:missing_foo')
    assert matched is not None and matched.id == 'PB-002'

    # Disable PB-002 -> falls back to PB-001; disable PB-001 -> no active match
    d1 = playbook.disable_rule(tmp_path, 'PB-002', created='2026-11-25')
    assert d1.id == 'PB-003'
    raw_after_3 = read_yaml(playbook.playbook_path(tmp_path))['rules']
    assert raw_after_3[:2] == raw_after_2
    matched_after_d1 = playbook.match_rule(tmp_path, station='repair', signature='repair:valueerror:missing_foo')
    assert matched_after_d1 is not None and matched_after_d1.id == 'PB-001'

    playbook.disable_rule(tmp_path, 'PB-001', created='2026-11-25')
    assert playbook.match_rule(tmp_path, station='repair', signature='repair:valueerror:missing_foo') is None


@pytest.mark.parametrize(
    'error_text',
    [
        'TimeoutError: request timed out',
        'URLError: <urlopen error [Errno 11001]>',
        'ConnectionResetError: [WinError 10054] ConnectionReset',
        'HTTP 429 Too Many Requests',
        'HTTP 503 Service Unavailable',
        'RuntimeError: OA retrieval failed',
    ],
)
def test_transient_network_errors_backoff_then_escalate_without_diagnose(tmp_path, monkeypatch, error_text):
    project = create_v2_project_fixture(tmp_path / 'projects')
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    blocked = logs / 'blocked.txt'
    blocked.write_text(error_text, encoding='utf-8')

    monkeypatch.setattr(repair_service, '_active', lambda *args: False)
    monkeypatch.setattr(playbook, 'DEFAULT_AUTO_RETRIES', 0)
    released = []
    monkeypatch.setattr(repair_service, '_release', lambda root, slug: released.append((root, slug)))
    ask_calls = []
    monkeypatch.setattr(repair_service, '_ask', lambda *args, **kwargs: ask_calls.append(args))

    expected_delays = playbook.TRANSIENT_BACKOFF_SECONDS
    for idx, expected_delay in enumerate(expected_delays, start=1):
        before = datetime.now(UTC)
        assert repair_service.repair_once(tmp_path, project.name) == 'cooldown'
        rec = read_yaml(logs / repair_service.REPORT)
        assert rec['transient_failures'] == idx
        assert rec['transient_retry_pending'] is True
        retry_after = datetime.fromisoformat(rec['retry_after'])
        delta = (retry_after - before).total_seconds()
        assert expected_delay - 5 <= delta <= expected_delay + 5
        assert doctor_questions.open_question(tmp_path, project.name) is None
        assert ask_calls == []

        # Still in cooldown -> stays cooldown
        assert repair_service.repair_once(tmp_path, project.name) == 'cooldown'

        # Expire cooldown -> releases project for retry
        rec['retry_after'] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        write_yaml_atomic(logs / repair_service.REPORT, rec)
        assert repair_service.repair_once(tmp_path, project.name) == 'retry_requested'
        assert len(released) == idx
        assert ask_calls == []

    # 4th failure after MAX_TRANSIENT_FAILURES -> escalates to doctor (no playbook rule in tmp_path)
    assert repair_service.repair_once(tmp_path, project.name) == 'exhausted'
    assert ask_calls == []
    q = doctor_questions.open_question(tmp_path, project.name)
    assert q is not None and q['kind'] == 'escalation'
    assert q['signature'] == playbook.incident_signature('repair', error_text)


def test_matching_playbook_rule_applies_without_doctor_question_logs_chat_and_respects_budget(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    rev = project / 'revisions/001'
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    detail = 'Review budget exhausted: script; 2/2; issues=[style-01].'
    (logs / 'blocked.txt').write_text(detail, encoding='utf-8')

    # Exhaust script review budget cleanly
    (rev / 'reviews/script-review-log.yaml').unlink(missing_ok=True)
    for idx in range(2):
        ev = f'ev-{idx}'
        review_budget.consume_review_budget(rev, 'script', ev)
        review_budget.record_evidence(rev, 'script', ev, {'issues': [{'issue_id': 'style-01', 'fix': 'Rewrite'}]})
    assert review_budget.review_budget_status(rev, 'script')['exhausted'] is True

    playbook.append_rule(
        tmp_path,
        source='seed',
        station='repair',
        signature='repair:station07_review_budget_style',
        action='delegate',
        delegate_role='writer',
        direction='Sửa đúng các issue critic nêu, giữ nguyên claim và nguồn.',
        max_auto_per_incident=1,
        created='2026-11-25',
    )

    monkeypatch.setattr(repair_service, '_active', lambda *args: False)
    monkeypatch.setattr(playbook, 'DEFAULT_AUTO_RETRIES', 0)
    released = []
    monkeypatch.setattr(repair_service, '_release', lambda root, slug: released.append((root, slug)))
    monkeypatch.setattr(factory, 'wake_background', lambda root: None)

    delegate_calls = []
    orig_delegate = repair_service.apply_reopen_or_delegate

    def spy_delegate(*args, **kwargs):
        delegate_calls.append(kwargs)
        return orig_delegate(*args, **kwargs)

    monkeypatch.setattr(repair_service, 'apply_reopen_or_delegate', spy_delegate)

    # First hit: playbook applies automatically, no doctor question, grants 1 extra round, posts chat
    assert repair_service.repair_once(tmp_path, project.name) == 'retry_requested'
    assert doctor_questions.open_question(tmp_path, project.name) is None
    assert len(delegate_calls) == 1
    assert delegate_calls[0]['rule_id'] == 'PB-001'
    assert len(released) == 1
    assert change_request.pending(project)

    budget_status = review_budget.review_budget_status(rev, 'script')
    assert budget_status['exhausted'] is False
    assert budget_status['limit'] == 3
    assert budget_status['grants'][0]['source'] == 'playbook PB-001'

    messages = chat.load(tmp_path, project.name)
    assert any('Xưởng tự xử lý theo định hướng PB-001 (ngày 2026-11-25):' in m['text'] for m in messages)

    # Durable counter in leader-repair.yaml: 2nd hit exceeds max_auto_per_incident=1 -> asks doctor
    assert repair_service.repair_once(tmp_path, project.name) == 'needs_attention'
    q = doctor_questions.open_question(tmp_path, project.name)
    assert q is not None and q['kind'] == 'escalation'
    assert q['signature'] == 'repair:station07_review_budget_style'


def test_doctor_answer_learns_rule_and_auto_applies_next_time(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    detail = 'ValueError: Custom renderer layout overflow on caption box'
    (logs / 'blocked.txt').write_text(detail, encoding='utf-8')

    # Pre-exhaust repair attempts and default auto-retries so it escalates to doctor
    sig = playbook.incident_signature('repair', detail)
    write_yaml_atomic(logs / repair_service.REPORT, {
        'revision': '001',
        'attempts': repair_service.MAX_REPAIRS,
        'attempts_before_incident': 0,
        'playbook_auto_counts': {f'default:{sig}': playbook.DEFAULT_AUTO_RETRIES},
        'incident': {'state': WorkflowState.DRAFT_READY.value, 'reason': repair_service._normalize_incident_reason(detail)},
        'diagnosis': {'action': 'hold', 'cause': 'Layout overflow', 'evidence': ['log'], 'delegate_role': 'writer', 'brief': 'Check caption'},
    })

    monkeypatch.setattr(repair_service, '_active', lambda *args: False)
    monkeypatch.setattr(playbook, 'DEFAULT_AUTO_RETRIES', 0)
    released = []
    monkeypatch.setattr(repair_service, '_release', lambda root, slug: released.append((root, slug)))
    monkeypatch.setattr(factory, 'wake_background', lambda root: None)
    monkeypatch.setattr(chat, 'start', lambda *args, **kwargs: None)

    assert repair_service.repair_once(tmp_path, project.name) == 'exhausted'
    q = doctor_questions.open_question(tmp_path, project.name)
    assert q is not None and q['signature']

    # Doctor answers with reopen_or_delegate + direction -> learns PB-001
    dashboard.answer_doctor_question(
        tmp_path,
        project.name,
        {
            'question_id': q['id'],
            'option_id': 'reopen_or_delegate',
            'text': 'Rút ngắn dòng chú thích dưới 12 từ rồi chạy lại.',
            'expected_revision': '001',
        },
    )
    learned = playbook.match_rule(tmp_path, station='repair', signature=q['signature'])
    assert learned is not None
    assert learned.source == 'doctor'
    assert learned.action == 'delegate'
    assert learned.delegate_role == 'writer'
    assert learned.question_id == q['id']
    assert learned.slug == project.name
    assert '12 từ' in (learned.direction or '')

    # Same incident in a SECOND project auto-applies the learned rule without asking the doctor!
    import shutil

    project2 = tmp_path / 'projects/second-topic'
    shutil.copytree(project, project2)
    (project2 / 'chat.jsonl').unlink(missing_ok=True)
    for ch in (project2 / 'revisions/001/reviews/changes').glob('*'):
        ch.unlink(missing_ok=True)
    logs2 = tmp_path / 'topics/logs' / project2.name
    logs2.mkdir(parents=True)
    (logs2 / 'blocked.txt').write_text(detail, encoding='utf-8')
    write_yaml_atomic(logs2 / repair_service.REPORT, {
        'revision': '001',
        'attempts': repair_service.MAX_REPAIRS,
        'attempts_before_incident': 0,
        'incident': {'state': WorkflowState.DRAFT_READY.value, 'reason': repair_service._normalize_incident_reason(detail)},
    })
    assert repair_service.repair_once(tmp_path, project2.name) == 'retry_requested'
    assert doctor_questions.open_question(tmp_path, project2.name) is None
    assert any(learned.id in m['text'] for m in chat.load(tmp_path, project2.name))


def test_doctor_pause_project_never_learns_rule(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    q = doctor_questions.ask(
        tmp_path,
        project.name,
        station='repair',
        kind='escalation',
        question='Sự cố cần chỉ đạo',
        options=[
            {'id': 'retry_repair_cycle', 'label': 'Thử lại'},
            {'id': 'reopen_or_delegate', 'label': 'Giao lại'},
            {'id': 'pause_project', 'label': 'Tạm dừng'},
        ],
        signature='repair:valueerror:some_fault',
    )
    monkeypatch.setattr(factory, 'wake_background', lambda root: None)
    monkeypatch.setattr(chat, 'start', lambda *args, **kwargs: None)

    dashboard.answer_doctor_question(
        tmp_path,
        project.name,
        {
            'question_id': q['id'],
            'option_id': 'pause_project',
            'text': 'Để bác sĩ xem sau.',
            'expected_revision': '001',
        },
    )
    assert playbook.load_playbook(tmp_path).rules == []


def test_safety_guards_never_auto_handle_pronunciation_pin_account_or_blocking_safety(tmp_path, monkeypatch):
    # 1. Non-escalation kinds are always forbidden
    assert playbook.is_auto_forbidden(kind='pronunciation', detail='anything') is True
    assert playbook.is_auto_forbidden(kind='tts_qa', detail='anything') is True
    assert playbook.is_auto_forbidden(kind='stuck_issue', detail='anything') is True

    # 2. PIN / account / reopen / blocking_safety keywords in detail are forbidden;
    #    free-form "không cần PIN" in diagnosis.cause is NOT forbidden when requires_doctor is None,
    #    while structured requires_doctor='pin' IS forbidden.
    assert playbook.is_auto_forbidden(kind='escalation', detail='Cần bác sĩ nhập PIN để mở cổng y khoa') is True
    assert playbook.is_auto_forbidden(
        kind='escalation',
        detail='Lỗi đồng bộ dữ liệu',
        record={'diagnosis': {'cause': 'Lỗi này không cần PIN và không cần mở cổng', 'requires_doctor': None}},
    ) is False
    assert playbook.is_auto_forbidden(
        kind='escalation',
        detail='Lỗi đồng bộ dữ liệu',
        record={'diagnosis': {'cause': 'Cần xác nhận', 'requires_doctor': 'pin'}},
    ) is True
    assert playbook.is_auto_forbidden(
        kind='escalation',
        detail='Lỗi đồng bộ dữ liệu',
        record={'diagnosis': {'cause': 'Cần OAuth', 'requires_doctor': 'account'}},
    ) is True

    # 3. End-to-end: blocking_safety in script-review-log.yaml blocks seed rule PB-002 from auto-applying
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    rev = project / 'revisions/001'
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    (logs / 'blocked.txt').write_text('Trạm 07 chưa đạt sau 3 chu kỳ (6 vòng)', encoding='utf-8')
    write_yaml_atomic(rev / 'reviews/script-review-log.yaml', {
        'rounds': [{
            'passed': False,
            'issues': [{'line': 'N02', 'criterion': 'dung_yeu_cau', 'problem': 'Sai liều', 'fix': 'Sửa', 'blocking_safety': True}],
        }],
    })
    playbook.append_rule(
        tmp_path,
        source='seed',
        station='repair',
        signature='repair:station07_review_budget_style',
        action='delegate',
        delegate_role='writer',
        direction='Sửa văn phong.',
        created='2026-11-25',
    )
    monkeypatch.setattr(repair_service, '_active', lambda *args: False)
    monkeypatch.setattr(playbook, 'DEFAULT_AUTO_RETRIES', 0)
    released = []
    monkeypatch.setattr(repair_service, '_release', lambda root, slug: released.append((root, slug)))

    assert repair_service.repair_once(tmp_path, project.name) == 'needs_attention'
    assert released == []
    assert not (rev / 'reviews/medical-approval.yaml').exists()
    q = doctor_questions.open_question(tmp_path, project.name)
    assert q is not None and q['kind'] == 'escalation'


def test_repair_diagnose_prompt_mentions_transient_auto_retry(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects')
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    (logs / 'blocked.txt').write_text('ValueError: deterministic bug', encoding='utf-8')
    monkeypatch.setattr(repair_service, '_active', lambda *args: False)
    prompts = []

    def fake_ask(root, slug, role, step, prompt, report, model, invoke):
        prompts.append(prompt)
        return repair_service.Diagnosis(
            action='hold',
            cause='Needs review',
            evidence=['log'],
            brief='Hold',
            requires_doctor='gate',
            doctor_options=[
                repair_service.DoctorOption(
                    label='Sửa kịch bản theo lỗi',
                    detail='Giao biên kịch chỉnh lại đoạn lỗi.',
                    action='delegate',
                    delegate_role='writer',
                    direction='Sửa đúng đoạn gây lỗi.',
                ),
                repair_service.DoctorOption(
                    label='Giữ nguyên và thử lại cấu hình',
                    detail='Chạy lại quy trình một chu kỳ.',
                    action='retry_cycle',
                    direction='Chạy lại sau khi kiểm tra cấu hình.',
                ),
            ],
        )

    monkeypatch.setattr(repair_service, '_ask', fake_ask)
    repair_service.repair_once(tmp_path, project.name)
    assert prompts
    assert 'Lỗi mạng tạm thời đã được xưởng tự thử lại; không chọn hold chỉ vì thiếu bằng chứng lỗi đã hết.' in prompts[0]
    assert 'doctor_options' in prompts[0]
    assert 'requires_doctor' in prompts[0]


def test_default_auto_retries_twice_without_playbook_rule_then_asks_doctor_with_options(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    rev = project / 'revisions/001'
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    detail = 'Review budget exhausted: script; 2/2; issues=[style-09].'
    (logs / 'blocked.txt').write_text(detail, encoding='utf-8')
    (rev / 'reviews/script-review-log.yaml').unlink(missing_ok=True)
    for idx in range(2):
        ev = f'ev-{idx}'
        review_budget.consume_review_budget(rev, 'script', ev)
        review_budget.record_evidence(rev, 'script', ev, {'issues': [{'issue_id': 'style-09', 'fix': 'Shorten'}]})

    monkeypatch.setattr(repair_service, '_active', lambda *args: False)
    released = []
    monkeypatch.setattr(repair_service, '_release', lambda root, slug: released.append((root, slug)))
    monkeypatch.setattr(factory, 'wake_background', lambda root: None)

    diag_calls = []

    def fake_ask(root, slug, role, step, prompt, report, model, invoke):
        diag_calls.append(step)
        return repair_service.Diagnosis(
            action='hold',
            cause='Kịch bản kẹt độ dài sau 2 lần tự chạy lại.',
            evidence=['script-review-log.yaml'],
            brief='Cần bác sĩ chọn phương án cắt gọn.',
            doctor_options=[
                repair_service.DoctorOption(
                    label='Cắt bớt phần cơ chế xuống dưới 45 giây',
                    detail='Giao biên kịch rút gọn phần giải thích cơ chế.',
                    action='delegate',
                    delegate_role='writer',
                    direction='Rút gọn phần cơ chế xuống dưới 45 giây, giữ nguyên claim.',
                ),
                repair_service.DoctorOption(
                    label='Tách thành 2 video ngắn hơn',
                    detail='Giao biên kịch viết lại theo bố cục tập 1.',
                    action='delegate',
                    delegate_role='writer',
                    direction='Tách nội dung thành tập 1 tập trung 1 ý chính.',
                ),
            ],
        )

    monkeypatch.setattr(repair_service, '_ask', fake_ask)

    # Attempt 1 & 2: default auto-retry applies without playbook file, posts chat, grants extra round
    assert repair_service.repair_once(tmp_path, project.name) == 'retry_requested'
    assert doctor_questions.open_question(tmp_path, project.name) is None
    assert not playbook.playbook_path(tmp_path).exists()
    assert diag_calls == []

    assert repair_service.repair_once(tmp_path, project.name) == 'retry_requested'
    assert doctor_questions.open_question(tmp_path, project.name) is None
    assert not playbook.playbook_path(tmp_path).exists()
    assert len(released) == 2

    msgs = [m['text'] for m in chat.load(tmp_path, project.name)]
    assert any('Xưởng tự chạy lại lần 1/2:' in t for t in msgs)
    assert any('Xưởng tự chạy lại lần 2/2:' in t for t in msgs)

    # Attempt 3: default retries exhausted -> runs editorial diagnosis and asks with concrete opt-1/opt-2 (no retry_repair_cycle)
    assert repair_service.repair_once(tmp_path, project.name) == 'needs_attention'
    assert diag_calls == ['repair_diagnose']
    q = doctor_questions.open_question(tmp_path, project.name)
    assert q is not None and q['kind'] == 'escalation'
    opt_ids = [o['id'] for o in q['options']]
    assert opt_ids == ['opt-1', 'opt-2', 'pause_project']
    assert 'retry_repair_cycle' not in opt_ids
    assert q['options'][0]['action'] == 'delegate'
    assert q['options'][0]['delegate_role'] == 'writer'
    assert '45 giây' in q['options'][0]['direction']


def test_selecting_doctor_option_opt_n_applies_action_and_learns_rule(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    sig = 'repair:research_missing_fulltext'
    q = doctor_questions.ask(
        tmp_path,
        project.name,
        station='repair',
        kind='escalation',
        question='Thiếu toàn văn mở cho nguồn E03',
        options=[
            {
                'id': 'opt-1',
                'label': 'Dùng abstract và ghi rõ giới hạn',
                'detail': 'Chuyên gia y khoa chỉ trích đúng phần abstract nói.',
                'action': 'delegate',
                'delegate_role': 'medical_expert',
                'direction': 'Dùng abstract cho đúng phần abstract nói, ghi rõ giới hạn.',
            },
            {
                'id': 'opt-2',
                'label': 'Bác sĩ đã bỏ PDF vào cache/fulltext/inbox',
                'detail': 'Chạy lại bước nghiên cứu để đọc PDF cục bộ.',
                'action': 'retry_cycle',
                'direction': 'Đọc PDF trong cache/fulltext/inbox rồi chạy lại.',
            },
            {
                'id': 'pause_project',
                'label': 'Tạm dừng dự án này',
                'detail': 'Tạm dừng để xem sau.',
            },
        ],
        signature=sig,
    )
    monkeypatch.setattr(repair_service, '_release', lambda root, slug: None)
    monkeypatch.setattr(factory, 'wake_background', lambda root: None)
    monkeypatch.setattr(chat, 'start', lambda *args, **kwargs: None)

    dashboard.answer_doctor_question(
        tmp_path,
        project.name,
        {
            'question_id': q['id'],
            'option_id': 'opt-1',
            'text': 'Ưu tiên nguồn Europe PMC trước',
            'expected_revision': '001',
        },
    )
    learned = playbook.match_rule(tmp_path, station='repair', signature=sig)
    assert learned is not None
    assert learned.source == 'doctor'
    assert learned.action == 'delegate'
    assert learned.delegate_role == 'medical_expert'
    assert 'Dùng abstract cho đúng phần abstract nói' in (learned.direction or '')
    assert 'Ưu tiên nguồn Europe PMC trước' in (learned.direction or '')
    assert change_request.pending(project)

