import json
import os
import subprocess
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from subprocess import CompletedProcess

import pytest

from healthvideo.agents import AllAgentsExhausted
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.process import process_token
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import factory, playbook
from healthvideo.workflows import repair_service as repair
from tests.helpers import create_v2_project_fixture


@pytest.fixture
def job(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects')
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    (logs / 'blocked.txt').write_text('RuntimeError: fixture fault', encoding='utf-8')
    source = tmp_path / 'src/fault.py'
    source.parent.mkdir()
    source.write_text('broken = True\n', encoding='utf-8')
    test = tmp_path / 'tests/test_fault.py'
    test.parent.mkdir()
    test.write_text('def test_fault(): pass\n', encoding='utf-8')
    monkeypatch.setattr(repair, '_active', lambda *args: False)
    monkeypatch.setattr(playbook, 'DEFAULT_AUTO_RETRIES', 0)
    monkeypatch.setattr(repair, '_maintenance', lambda *args, **kwargs: nullcontext((
        {'src/fault.py': source.read_bytes()},
        repair._workspace_paths(tmp_path),
    )))
    released = []
    monkeypatch.setattr(repair, '_release', lambda *args: released.append(args))
    stages = []

    def ask(root, slug, role, step, *args):
        stages.append((role, step))
        if step == 'repair_diagnose':
            return repair.Diagnosis(action='repair', cause='Fixture bug', evidence=['fixture log'],
                                    files=['src/fault.py'], tests=['tests/test_fault.py'],
                                    brief='Fix the technical failure.')
        if step == 'repair':
            source.write_text('broken = False\n', encoding='utf-8')
            return repair.RepairResult(status='ready', summary='Fixture fixed')
        return repair.Acceptance(passed=True, reason='Verified test output and fix')

    monkeypatch.setattr(repair, '_ask', ask)
    return tmp_path, project, logs, source, released, stages


def test_leader_assigns_independent_engineer_and_accepts_before_retry(job):
    root, project, logs, source, released, stages = job
    commands = []

    def run(argv, **kwargs):
        commands.append(argv)
        return CompletedProcess(argv, 0, 'passed', '')

    assert repair.repair_once(root, project.name, run=run) == 'awaiting_dev'
    assert stages == [('coordinator_senior', 'repair_diagnose')]
    assert commands == []
    assert released == []
    assert 'True' in source.read_text()
    report = read_yaml(logs / repair.REPORT)
    assert report['phase'] == 'awaiting_dev'
    assert report['attempts'] == 0
    tickets = list((root / 'topics/dev-tickets').glob(f'*-{project.name}.yaml'))
    assert len(tickets) == 1
    assert 'Chờ dev lead sửa code:' in (logs / 'blocked.txt').read_text(encoding='utf-8')


def test_failed_tests_restore_original_code_and_never_release_retry(job, monkeypatch):
    root, project, logs, source, released, stages = job
    before = source.read_bytes()

    def ask_retry_declined(root, slug, role, step, *args):
        stages.append((role, step))
        if step == 'repair_diagnose':
            return repair.Diagnosis(action='retry', cause='Fixture fault', evidence=['fixture log'],
                                    brief='Verify transient recovery.')
        return repair.Acceptance(passed=False, reason='Cause still unresolved')

    monkeypatch.setattr(repair, '_ask', ask_retry_declined)
    assert repair.repair_once(root, project.name) == 'repair_failed'
    assert source.read_bytes() == before
    assert released == []
    repair.repair_once(root, project.name)
    assert repair.repair_once(root, project.name) == 'exhausted'
    assert read_yaml(logs / repair.REPORT)['attempts'] == repair.MAX_REPAIRS
    assert read_yaml(logs / repair.REPORT)['phase'] == 'needs_attention'


def test_new_block_reason_gets_repair_after_previous_budget_is_exhausted(job, monkeypatch):
    root, project, logs, _, _, stages = job
    blocked = logs / 'blocked.txt'

    def ask_retry_declined(root, slug, role, step, *args):
        stages.append((role, step))
        if step == 'repair_diagnose':
            return repair.Diagnosis(action='retry', cause='Fixture fault', evidence=['fixture log'],
                                    brief='Verify transient recovery.')
        return repair.Acceptance(passed=False, reason='Still failing')

    monkeypatch.setattr(repair, '_ask', ask_retry_declined)
    for attempt in range(repair.MAX_REPAIRS):
        blocked.write_text(f'First fault\nlog_path: attempt-{attempt}.log\n', encoding='utf-8')
        assert repair.repair_once(root, project.name) == 'repair_failed'
    blocked.write_text('First fault\nlog_path: latest.log\n', encoding='utf-8')
    assert repair.repair_once(root, project.name) == 'exhausted'

    blocked.write_text('Different fault\nlog_path: current.log\n', encoding='utf-8')
    assert repair.repair_once(root, project.name) == 'repair_failed'
    assert stages.count(('coordinator_senior', 'repair_diagnose')) == repair.MAX_REPAIRS + 1


def test_declined_acceptance_restores_code_and_keeps_hold(job, monkeypatch):
    root, project, _, source, released, _ = job

    def decline(root, slug, role, step, *args):
        if step == 'repair_diagnose':
            return repair.Diagnosis(action='retry', cause='Fixture fault', evidence=['fixture log'],
                                    brief='Verify transient recovery.')
        return repair.Acceptance(passed=False, reason='Cause still unresolved')

    monkeypatch.setattr(repair, '_ask', decline)
    before = source.read_bytes()
    assert repair.repair_once(root, project.name) == 'repair_failed'
    assert source.read_bytes() == before
    assert released == []


def test_busy_project_gets_no_repair_job(job, monkeypatch):
    root, project, logs, _, released, stages = job
    monkeypatch.setattr(repair, '_active', lambda *args: True)
    assert repair.repair_once(root, project.name) == 'busy'
    assert not (logs / repair.REPORT).exists()
    assert not stages and not released


def test_script_cycle_limit_is_left_for_doctor_without_spending_repairs(job):
    from healthvideo.workflows.script_review import CYCLE_LIMIT_REASON

    root, project, logs, _, released, _stages = job
    path = logs / repair.REPORT
    original = {'revision': '001', 'attempts': 1, 'phase': 'repair_failed'}
    write_yaml_atomic(path, original)
    detail = f'chấm kịch bản lỗi: {CYCLE_LIMIT_REASON} (6 vòng); Bác sĩ gửi hướng dẫn qua chat.'
    (logs / 'blocked.txt').write_text(detail, encoding='utf-8')
    for _ in range(2):
        assert repair.repair_once(root, project.name) == 'needs_attention'
    assert read_yaml(path)['attempts'] == original['attempts']
    assert (logs / 'blocked.txt').read_text(encoding='utf-8') == detail
    assert not released


@pytest.mark.parametrize('path', ['../outside.py', 'projects/topic/script.yaml', 'profiles/company.yaml'])
def test_repair_scope_rejects_escape_and_project_or_account_configuration(tmp_path, path):
    with pytest.raises(ValueError):
        repair._paths(tmp_path, [path])


def test_active_verifies_live_process_token_and_ignores_orphaned_markers(tmp_path):
    logs = tmp_path / 'topics/logs/topic-a'
    logs.mkdir(parents=True)
    # Orphaned .agent-running (wrong token) and orphaned .production-running (dead PID/token)
    (logs / '.agent-running').write_text(
        f"writer\n2026-11-15T10:00:00Z\n{json.dumps({'pid': os.getpid(), 'process_token': 'stale-token'})}\n",
        encoding='utf-8',
    )
    (logs / '.production-running').write_text(
        json.dumps({'pid': 999999, 'process_token': 'dead-token'}),
        encoding='utf-8',
    )
    # Orphaned .chat-step-running when factory is not running
    (logs / '.chat-step-running').touch()
    assert repair._active(tmp_path, 'topic-a') is False
    assert repair._active(tmp_path) is False

    # Live .production-running with current PID and OS process_token
    live_token = process_token(os.getpid())
    assert live_token
    (logs / '.production-running').write_text(
        json.dumps({'pid': os.getpid(), 'process_token': live_token}),
        encoding='utf-8',
    )
    assert repair._active(tmp_path, 'topic-a') is True
    assert repair._active(tmp_path) is True

    # Repair directory markers do not count as active production/topic work
    (logs / '.production-running').unlink()
    repair_logs = tmp_path / 'topics/logs/repair/topic-a/1'
    repair_logs.mkdir(parents=True)
    (repair_logs / '.agent-running').write_text(
        f"repair_engineer\n2026-11-15T10:00:00Z\n{json.dumps({'pid': os.getpid(), 'process_token': live_token})}\n",
        encoding='utf-8',
    )
    assert repair._active(tmp_path) is False


def test_agent_marker_uses_child_identity_when_factory_pid_is_still_alive(tmp_path):
    logs = tmp_path / 'topics/logs/topic-a'
    logs.mkdir(parents=True)
    token = process_token(os.getpid())
    assert token
    identity = {'job_id': 'a' * 32, 'pid': os.getpid(), 'process_token': token, 'started_at': 'now'}
    marker = logs / '.agent-running'
    marker.write_text(f"writer\nnow\n{json.dumps(identity)}\n", encoding='utf-8')
    job = logs / f".job-{identity['job_id']}.json"
    assert repair._active(tmp_path, 'topic-a')

    job.write_text(json.dumps({**identity, 'child_pid': os.getpid(),
                               'child_process_token': 'expired-token'}), encoding='utf-8')
    assert not repair._active(tmp_path, 'topic-a')

    job.write_text(json.dumps({**identity, 'child_pid': os.getpid(),
                               'child_process_token': token}), encoding='utf-8')
    assert repair._active(tmp_path, 'topic-a')


def test_maintenance_blocks_factory_start_and_crash_recovery_restores_disk_state(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects')
    src = tmp_path / 'src/mod.py'
    src.parent.mkdir(parents=True)
    src.write_text('original = 1\n', encoding='utf-8')
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    record_path = logs / repair.REPORT
    write_yaml_atomic(record_path, {'revision': '001', 'attempts': 1, 'phase': 'repairing'})

    # Simulate factory was running, then stopped for maintenance
    monkeypatch.setattr(factory, 'stop_background', lambda root: 4321)
    monkeypatch.setattr(factory, 'running_pid', lambda root: None)
    started = []
    monkeypatch.setattr(factory, 'start_background', lambda root: started.append(root) or 5678)

    with repair._maintenance(tmp_path, slug=project.name, attempt=1, assigned_files=[src]):
        # Another process trying to take FactoryLock must be rejected while maintenance holds it
        with pytest.raises(factory.FactoryAlreadyRunning), factory.FactoryLock(tmp_path):
            pass
        assert (tmp_path / repair.MAINTENANCE_STATE).is_file()

    assert started == [tmp_path]
    assert not (tmp_path / repair.MAINTENANCE_STATE).exists()

    # Now simulate a crashed repair worker that left maintenance.json + modified/new files on disk
    started.clear()
    backup_dir = tmp_path / 'cache/repair-worker/backups/crash'
    backup_dir.mkdir(parents=True)
    bak_file = backup_dir / '0000.bak'
    bak_file.write_bytes(b'original = 1\n')
    src.write_text('corrupted_by_crash = True\n', encoding='utf-8')
    rogue = tmp_path / 'src/rogue_new.py'
    rogue.write_text('rogue = True\n', encoding='utf-8')
    (tmp_path / repair.MAINTENANCE_STATE).write_text(json.dumps({
        'slug': project.name,
        'attempt': 1,
        'was_running': True,
        'pid': 999999,
        'process_token': 'dead-worker-token',
        'backup_dir': str(backup_dir),
        'backups': [{'rel': 'src/mod.py', 'backup': str(bak_file)}],
        'before_paths': ['src/mod.py'],
    }), encoding='utf-8')

    assert repair.recover_interrupted_repairs(tmp_path) is True
    assert src.read_text(encoding='utf-8') == 'original = 1\n'
    assert not rogue.exists()
    assert not (tmp_path / repair.MAINTENANCE_STATE).exists()
    assert read_yaml(record_path)['phase'] == 'repair_failed'
    assert started == [tmp_path]


def test_scope_violation_detects_new_and_out_of_scope_files_and_rolls_back(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects')
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    (logs / 'blocked.txt').write_text('RuntimeError: fault', encoding='utf-8')
    assigned = tmp_path / 'src/assigned.py'
    other = tmp_path / 'src/other.py'
    assigned.parent.mkdir(parents=True)
    assigned.write_text('v = 1\n', encoding='utf-8')
    other.write_text('uncommitted_by_other = True\n', encoding='utf-8')
    test_file = tmp_path / 'tests/test_assigned.py'
    test_file.parent.mkdir(parents=True)
    test_file.write_text('def test_ok(): pass\n', encoding='utf-8')

    before_bytes = {'src/assigned.py': assigned.read_bytes(), 'src/other.py': other.read_bytes()}
    before_paths = repair._workspace_paths(tmp_path)
    assigned.write_text('v = 2\n', encoding='utf-8')
    other.write_text('hijacked = True\n', encoding='utf-8')
    (tmp_path / 'src/rogue.py').write_text('rogue = True\n', encoding='utf-8')
    with pytest.raises(ValueError, match='ngoài phạm vi'):
        repair._check_scope(tmp_path, [assigned], before_bytes, before_paths)
    repair._restore_workspace(tmp_path, before_bytes, before_paths)
    assert assigned.read_text(encoding='utf-8') == 'v = 1\n'
    assert other.read_text(encoding='utf-8') == 'uncommitted_by_other = True\n'
    assert not (tmp_path / 'src/rogue.py').exists()

    monkeypatch.setattr(repair, '_active', lambda *args: False)

    def ask_repair(root, slug, role, step, *args):
        if step == 'repair_diagnose':
            return repair.Diagnosis(action='repair', cause='Bug', evidence=['log'],
                                    files=['src/assigned.py'], tests=['tests/test_assigned.py'],
                                    brief='Fix assigned.py only')
        pytest.fail('repair_engineer must not be invoked')

    monkeypatch.setattr(repair, '_ask', ask_repair)
    assert repair.repair_once(tmp_path, project.name) == 'awaiting_dev'
    assert assigned.read_text(encoding='utf-8') == 'v = 1\n'
    assert other.read_text(encoding='utf-8') == 'uncommitted_by_other = True\n'


def test_retry_requested_requires_actual_retry_and_passing_validator_before_validated(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    # retry_requested_at is strictly after fixture creation
    future_req = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
    write_yaml_atomic(logs / repair.REPORT, {
        'revision': '001',
        'attempts': 1,
        'phase': 'retry_requested',
        'state_before': WorkflowState.DRAFT_READY.value,
        'retry_requested_at': future_req,
    })
    monkeypatch.setattr(repair, '_active', lambda *args: False)

    # 1. blocked.txt is gone, but no retry has run yet -> must NOT mark validated
    assert repair.repair_once(tmp_path, project.name) == 'waiting_retry'
    assert read_yaml(logs / repair.REPORT)['phase'] == 'retry_requested'

    # 2. Retry advances state to AWAITING_MEDICAL_REVIEW, but script_review has NOT passed -> still not validated
    def fail_review(proj):
        raise ValueError('Chưa qua script_review')

    monkeypatch.setattr(repair.script_review, 'require_passed_review', fail_review)
    manifest = read_yaml(project / 'project.yaml')
    manifest['state'] = WorkflowState.AWAITING_MEDICAL_REVIEW.value
    write_yaml_atomic(project / 'project.yaml', manifest)
    assert repair.repair_once(tmp_path, project.name) == 'waiting_retry'
    assert 'script_review' in read_yaml(logs / repair.REPORT)['validation_error']

    # 3. Now script_review passes -> transitions to validated with evidence
    monkeypatch.setattr(repair.script_review, 'require_passed_review', lambda proj: None)
    assert repair.repair_once(tmp_path, project.name) == 'validated'
    report = read_yaml(logs / repair.REPORT)
    assert report['phase'] == 'validated'
    assert report['validated_evidence']['state_after'] == WorkflowState.AWAITING_MEDICAL_REVIEW.value


def test_writer_handoff_cannot_validate_before_script_critic_passes(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    layout = repair.resolve_project_layout(project)
    monkeypatch.setattr(repair, '_has_post_retry_activity', lambda *args: True)
    record = {'state_before': 'draft_ready', 'delegation': {'role': 'writer'}}

    def fail_review(_):
        raise ValueError('Trạm 07 chưa đạt')

    monkeypatch.setattr(repair.script_review, 'require_passed_review', fail_review)
    ok, error, _ = repair._verify_retry_validated(tmp_path, project.name, layout, tmp_path, record)
    assert not ok
    assert 'Trạm 07 chưa đạt' in error


def test_leader_delegates_content_issues_to_writer_expert_editor_respecting_gates(tmp_path, monkeypatch):
    monkeypatch.setattr(repair, '_active', lambda *args: False)
    released = []
    monkeypatch.setattr(repair, '_release', lambda root, slug: released.append((root, slug)))

    # Case A: writer in DRAFT_READY -> creates edit_script change request & releases hold
    root_a = tmp_path / 'case_a'
    proj_a = create_v2_project_fixture(root_a / 'projects', state=WorkflowState.DRAFT_READY)
    logs_a = root_a / 'topics/logs' / proj_a.name
    logs_a.mkdir(parents=True)
    (logs_a / 'blocked.txt').write_text('Script rejected by critic', encoding='utf-8')
    monkeypatch.setattr(
        repair, '_ask',
        lambda *args: repair.Diagnosis(
            action='delegate', delegate_role='writer', cause='Missing hook',
            evidence=['critic log'], brief='Rewrite hook for clarity',
        ),
    )
    assert repair.repair_once(root_a, proj_a.name) == 'retry_requested'
    assert released == [(root_a, proj_a.name)]
    assert list((proj_a / 'revisions/001/reviews/changes').glob('*-requested.yaml'))

    # Case B: medical_expert in DRAFT_READY -> appends open WriterQuestion & releases hold
    root_b = tmp_path / 'case_b'
    proj_b = create_v2_project_fixture(root_b / 'projects', state=WorkflowState.DRAFT_READY)
    logs_b = root_b / 'topics/logs' / proj_b.name
    logs_b.mkdir(parents=True)
    (logs_b / 'blocked.txt').write_text('Missing PMID', encoding='utf-8')
    monkeypatch.setattr(
        repair, '_ask',
        lambda *args: repair.Diagnosis(
            action='delegate', delegate_role='medical_expert', cause='Unverified claim',
            evidence=['evidence log'], brief='Verify PMID for claim C01',
        ),
    )
    assert repair.repair_once(root_b, proj_b.name) == 'retry_requested'
    q_data = read_yaml(proj_b / 'revisions/001/script/questions.yaml')
    assert len(q_data['questions']) == 1 and q_data['questions'][0]['ask'] == 'Verify PMID for claim C01'

    # Case C: medical_expert AFTER medical gate -> must NOT revoke approval, holds as needs_attention
    root_c = tmp_path / 'case_c'
    proj_c = create_v2_project_fixture(root_c / 'projects', state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    logs_c = root_c / 'topics/logs' / proj_c.name
    logs_c.mkdir(parents=True)
    (logs_c / 'blocked.txt').write_text('Medical claim question', encoding='utf-8')
    assert repair.repair_once(root_c, proj_c.name) == 'needs_attention'
    rep_c = read_yaml(logs_c / repair.REPORT)
    assert rep_c['delegation']['requires_doctor_reopen'] is True

    # Case D: editor in PRODUCTION_IN_PROGRESS receives a scoped presentation repair before review.
    root_d = tmp_path / 'case_d'
    proj_d = create_v2_project_fixture(root_d / 'projects', state=WorkflowState.DRAFT_READY)
    manifest_d = read_yaml(proj_d / 'project.yaml')
    manifest_d['state'] = WorkflowState.PRODUCTION_IN_PROGRESS.value
    write_yaml_atomic(proj_d / 'project.yaml', manifest_d)
    logs_d = root_d / 'topics/logs' / proj_d.name
    logs_d.mkdir(parents=True)
    (logs_d / 'blocked.txt').write_text('Storyboard timing mismatch', encoding='utf-8')
    monkeypatch.setattr(
        repair, '_ask',
        lambda *args: repair.Diagnosis(
            action='delegate', delegate_role='editor', cause='Scene pacing issue',
            evidence=['render log'], brief='Adjust S02 timing',
        ),
    )
    assert repair.repair_once(root_d, proj_d.name) == 'retry_requested'
    assert read_yaml(proj_d / 'project.yaml')['state'] == WorkflowState.PRODUCTION_IN_PROGRESS.value
    assert read_yaml(logs_d / 'leader-guidance.yaml')['step'] == 'revise_product'


def test_quota_and_timeout_enter_cooldown_without_burning_attempts(job, monkeypatch):
    root, project, logs, source, released, _ = job
    before = source.read_bytes()

    def ask_quota(root, slug, role, step, *args):
        raise AllAgentsExhausted(datetime.now(UTC) + timedelta(minutes=5))

    monkeypatch.setattr(repair, '_ask', ask_quota)
    assert repair.repair_once(root, project.name) == 'cooldown'
    report = read_yaml(logs / repair.REPORT)
    assert report['attempts'] == 0
    assert report['transient_failures'] == 1
    assert source.read_bytes() == before
    assert released == []
    # Immediate retry respects cooldown
    assert repair.repair_once(root, project.name) == 'cooldown'

    # Timeout during acceptance also enters cooldown without burning attempts
    write_yaml_atomic(logs / repair.REPORT, {'revision': '001', 'attempts': 0})

    def ask_timeout(root, slug, role, step, *args):
        if step == 'repair_diagnose':
            return repair.Diagnosis(action='retry', cause='Bug', evidence=['log'],
                                    brief='Verify transient fix')
        raise subprocess.TimeoutExpired(['codex'], 600)

    monkeypatch.setattr(repair, '_ask', ask_timeout)
    assert repair.repair_once(root, project.name) == 'cooldown'
    assert source.read_bytes() == before


def test_isolated_smoke_chain_leader_engineer_test_accept_retry_validated(tmp_path, monkeypatch):
    """End-to-end isolated smoke fixture: Leader retry -> accept -> retry -> validated."""
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    (logs / 'blocked.txt').write_text('ZeroDivisionError in helper', encoding='utf-8')

    monkeypatch.setattr(factory, 'stop_background', lambda root: None)
    monkeypatch.setattr(factory, 'running_pid', lambda root: None)
    monkeypatch.setattr(repair, '_release', lambda root, slug: (logs / 'blocked.txt').unlink(missing_ok=True))

    def ask_smoke(root, slug, role, step, *args):
        if step == 'repair_diagnose':
            return repair.Diagnosis(
                action='retry', cause='Transient glitch resolved', evidence=['blocked.txt'],
                brief='Retry step after transient fix',
            )
        return repair.Acceptance(passed=True, reason='Verified ready to retry')

    monkeypatch.setattr(repair, '_ask', ask_smoke)

    assert repair.repair_once(tmp_path, project.name) == 'retry_requested'
    assert not (logs / 'blocked.txt').exists()
    assert repair.repair_once(tmp_path, project.name) == 'waiting_retry'

    # Simulate factory executing retry and advancing state + passing script_review
    manifest = read_yaml(project / 'project.yaml')
    manifest['state'] = WorkflowState.AWAITING_MEDICAL_REVIEW.value
    write_yaml_atomic(project / 'project.yaml', manifest)
    monkeypatch.setattr(repair.script_review, 'require_passed_review', lambda proj: None)
    assert repair.repair_once(tmp_path, project.name) == 'validated'
    assert read_yaml(logs / repair.REPORT)['validated_evidence']['state_after'] == WorkflowState.AWAITING_MEDICAL_REVIEW.value


def test_restore_and_crash_recovery_never_touch_projects_topics_docs_or_runtime_profiles(tmp_path):
    project = create_v2_project_fixture(tmp_path / 'projects')
    proj_yaml = project / 'project.yaml'
    proj_before = proj_yaml.read_bytes()
    queue_yaml = tmp_path / 'topics/queue.yaml'
    queue_yaml.parent.mkdir(parents=True)
    queue_yaml.write_text('version: 1\nentries: []\n', encoding='utf-8')
    docs_progress = tmp_path / 'docs/progress.yaml'
    docs_progress.parent.mkdir(parents=True)
    docs_progress.write_text('items: []\n', encoding='utf-8')
    feedback = tmp_path / 'profiles/doctor-feedback.yaml'
    pin_file = tmp_path / 'profiles/review-pin.yaml'
    secret_file = tmp_path / 'profiles/youtube-token.json'
    feedback.parent.mkdir(parents=True)
    feedback.write_text('notes: [keep]\n', encoding='utf-8')
    pin_file.write_text('hash: keep\n', encoding='utf-8')
    secret_file.write_text('{"token": "keep"}\n', encoding='utf-8')

    src = tmp_path / 'src/app.py'
    src.parent.mkdir(parents=True)
    src.write_text('x = 1\n', encoding='utf-8')
    rogue_code = tmp_path / 'src/rogue.py'
    rogue_code.write_text('rogue = True\n', encoding='utf-8')

    # 1. _restore_workspace must preserve projects, topics, docs, and runtime profile files
    repair._restore_workspace(tmp_path, {'src/app.py': b'x = 1\n'}, {'src/app.py'})
    assert not rogue_code.exists()
    assert proj_yaml.read_bytes() == proj_before
    assert queue_yaml.read_text(encoding='utf-8') == 'version: 1\nentries: []\n'
    assert docs_progress.read_text(encoding='utf-8') == 'items: []\n'
    assert feedback.read_text(encoding='utf-8') == 'notes: [keep]\n'
    assert pin_file.read_text(encoding='utf-8') == 'hash: keep\n'
    assert secret_file.read_text(encoding='utf-8') == '{"token": "keep"}\n'

    # 2. recover_interrupted_repairs with missing/empty before_paths must NOT unlink docs/README
    src.write_text('x = 999\n', encoding='utf-8')
    backup_dir = tmp_path / 'cache/repair-worker/backups/crash2'
    backup_dir.mkdir(parents=True)
    bak = backup_dir / '0000.bak'
    bak.write_bytes(b'x = 1\n')
    (tmp_path / repair.MAINTENANCE_STATE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / repair.MAINTENANCE_STATE).write_text(json.dumps({
        'slug': project.name,
        'attempt': 1,
        'was_running': False,
        'pid': 999999,
        'process_token': 'dead-token',
        'backup_dir': str(backup_dir),
        'backups': [{'rel': 'src/app.py', 'backup': str(bak)}],
    }), encoding='utf-8')

    assert repair.recover_interrupted_repairs(tmp_path) is True
    assert src.read_text(encoding='utf-8') == 'x = 1\n'
    assert docs_progress.read_text(encoding='utf-8') == 'items: []\n'
    assert proj_yaml.read_bytes() == proj_before
    assert queue_yaml.exists() and feedback.exists() and pin_file.exists() and secret_file.exists()


def test_stop_background_leaves_repair_to_finish_current_round(tmp_path, monkeypatch):
    monkeypatch.setattr(factory, 'running_pid', lambda root: 1234)
    def forbidden_stop(pid):
        pytest.fail('Repair or its agent was forcibly stopped')
    monkeypatch.setattr(factory, 'stop_background', forbidden_stop)
    monkeypatch.setattr(repair, 'terminate_process_tree', forbidden_stop, raising=False)
    assert repair.stop_background(tmp_path, wait_seconds=0.0) is None

    # Live maintenance in current process must block forced stop
    state_path = tmp_path / repair.MAINTENANCE_STATE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        'pid': os.getpid(),
        'process_token': process_token(os.getpid()),
    }), encoding='utf-8')
    with pytest.raises(RuntimeError, match='maintenance'):
        repair.stop_background(tmp_path, wait_seconds=0.0)


@pytest.mark.parametrize('token', ['parent-identity', None])
def test_ensure_background_prepends_source_root_to_pythonpath_and_returns_immediately(tmp_path, monkeypatch, token):
    monkeypatch.setattr(factory, 'running_pid', lambda root: None)
    monkeypatch.setattr(repair, 'process_token', lambda pid: token)
    captured = {}

    class DummyProc:
        pid = 9876

    def fake_popen(argv, **kwargs):
        captured['argv'] = argv
        captured['env'] = kwargs['env']
        return DummyProc()

    monkeypatch.setattr(subprocess, 'Popen', fake_popen)
    assert repair.ensure_background(tmp_path) == 9876
    expected_src = str(repair.Path(repair.__file__).resolve().parents[2])
    pythonpath_parts = captured['env']['PYTHONPATH'].split(os.pathsep)
    assert pythonpath_parts[0] == expected_src
    if token:
        assert captured['argv'][-4:] == ['--parent-pid', str(os.getpid()), '--parent-token', token]
    else:
        assert '--parent-pid' not in captured['argv']
        assert '--parent-token' not in captured['argv']


def test_main_exits_cleanly_when_factory_stops_after_being_seen(tmp_path, monkeypatch):
    import sys

    pids = iter([1111, 1111, None])
    monkeypatch.setattr(factory, 'running_pid', lambda root: next(pids, None))
    monkeypatch.setattr(factory, 'projects', lambda root: [])
    monkeypatch.setattr(repair.time, 'sleep', lambda s: None)
    monkeypatch.setattr(sys, 'argv', ['repair_service', '--root', str(tmp_path)])
    repair.main()
    assert not (tmp_path / 'cache/repair-worker/topics/.xuong.lock').read_text(encoding='utf-8')


def test_recover_interrupted_diagnoses_refunds_attempt_and_cleans_dead_markers(job):
    root, project, logs, _, _, _ = job
    attempt_dir = root / 'topics/logs/repair' / project.name / '1'
    attempt_dir.mkdir(parents=True)
    log_file = attempt_dir / '20261115T120000-codex.log'
    log_file.write_text('partial log\n', encoding='utf-8')
    dead_agent = attempt_dir / '.agent-running'
    dead_job = attempt_dir / '.job-deadbeef.json'
    dead_agent.write_text(
        f"coordinator_senior\n2026-11-15T12:00:00Z\n{json.dumps({'pid': 999999, 'process_token': 'dead'})}\n",
        encoding='utf-8',
    )
    dead_job.write_text(
        json.dumps({'child_pid': 999998, 'child_process_token': 'dead-child'}),
        encoding='utf-8',
    )
    record_path = logs / repair.REPORT
    write_yaml_atomic(record_path, {'revision': '001', 'attempts': 1, 'phase': 'diagnosing'})

    assert repair.recover_interrupted_repairs(root) is True
    assert not dead_agent.exists()
    assert not dead_job.exists()
    assert log_file.exists()
    recovered = read_yaml(record_path)
    assert recovered['attempts'] == 0
    assert recovered['phase'] == 'interrupted'

    # Subsequent repair_once can run normally (action=repair opens dev ticket)
    assert repair.repair_once(root, project.name) == 'awaiting_dev'


def test_repair_once_returns_busy_when_diagnosing_attempt_is_live(job):
    root, project, logs, _, _, _ = job
    attempt_dir = root / 'topics/logs/repair' / project.name / '1'
    attempt_dir.mkdir(parents=True)
    live_token = process_token(os.getpid())
    assert live_token
    (attempt_dir / '.agent-running').write_text(
        f"coordinator_senior\n2026-11-15T12:00:00Z\n{json.dumps({'pid': os.getpid(), 'process_token': live_token})}\n",
        encoding='utf-8',
    )
    write_yaml_atomic(logs / repair.REPORT, {'revision': '001', 'attempts': 1, 'phase': 'diagnosing'})
    assert repair._repair_attempt_live(root, project.name, 1) is True
    assert repair.repair_once(root, project.name) == 'busy'


def test_repair_once_skips_paused_project(job):
    root, project, logs, _, _, stages = job
    write_yaml_atomic(logs / 'paused.yaml', {'paused_at': '2026-11-15T20:00:00Z'})
    assert repair.repair_once(root, project.name) == 'paused'
    assert stages == []

def test_main_exits_if_starting_worker_died_before_first_observation(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(factory, 'running_pid', lambda root: None)
    def unexpected_sleep(seconds):
        pytest.fail('Repair waited forever for a worker that already died')
    monkeypatch.setattr(repair.time, 'sleep', unexpected_sleep)
    monkeypatch.setattr(sys, 'argv', ['repair_service', '--root', str(tmp_path),
                                    '--parent-pid', str(os.getpid()),
                                    '--parent-token', 'expired-identity'])
    repair.main()


@pytest.mark.parametrize('token', [None, 'parent-identity'])
def test_main_finishes_current_repair_then_exits_when_worker_stops(tmp_path, monkeypatch, token):
    import sys

    alive = True
    completed = []
    monkeypatch.setattr(factory, 'running_pid', lambda root: 1111 if alive else None)
    monkeypatch.setattr(repair, 'is_same_process', lambda pid, token: alive)
    monkeypatch.setattr(repair, 'recover_interrupted_repairs', lambda root: None)
    monkeypatch.setattr(factory, 'projects', lambda root: [(tmp_path / 'first', None), (tmp_path / 'second', None)])
    def repair_round(root, slug, **kwargs):
        nonlocal alive
        alive = False  # Worker stops while this repair's agent is running.
        assert repair.stop_background(root, wait_seconds=0) is None
        completed.append(slug)
    monkeypatch.setattr(repair, 'repair_once', repair_round)
    def unexpected_sleep(seconds):
        pytest.fail('Repair did not exit after finishing the current round')
    monkeypatch.setattr(repair.time, 'sleep', unexpected_sleep)
    argv = ['repair_service', '--root', str(tmp_path), '--parent-pid', '1111']
    if token:
        argv.extend(['--parent-token', token])
    monkeypatch.setattr(sys, 'argv', argv)
    repair.main()
    assert completed == ['first']


def test_maintenance_restarts_factory_when_setup_fails_after_stop(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects')
    src = tmp_path / 'src/mod.py'
    src.parent.mkdir(parents=True)
    src.write_text('x = 1\n', encoding='utf-8')
    monkeypatch.setattr(factory, 'stop_background', lambda root: 13064)
    monkeypatch.setattr(factory, 'running_pid', lambda root: None)
    started = []
    monkeypatch.setattr(factory, 'start_background', lambda root: started.append(root) or 23064)
    monkeypatch.setattr(
        repair,
        '_lock_factory_for_maintenance',
        lambda root: (_ for _ in ()).throw(factory.FactoryAlreadyRunning('Xưởng đang chạy (PID đang khởi động).')),
    )

    with (
        pytest.raises(factory.FactoryAlreadyRunning),
        repair._maintenance(tmp_path, slug=project.name, attempt=1, assigned_files=[src]),
    ):
        pytest.fail('Maintenance body must not run when locking fails')

    assert started == [tmp_path]
    assert not (tmp_path / repair.MAINTENANCE_STATE).exists()


def test_lock_factory_for_maintenance_retries_windows_kernel_teardown_then_succeeds(tmp_path, monkeypatch):
    if os.name != 'nt':
        pytest.skip('Windows msvcrt locking path')
    import msvcrt

    monkeypatch.setattr(factory, 'running_pid', lambda root: None)
    sleeps = []
    monkeypatch.setattr(repair.time, 'sleep', lambda s: sleeps.append(s))
    real_locking = msvcrt.locking
    calls = 0

    def flaky_locking(fd, mode, nbytes):
        nonlocal calls
        if mode == msvcrt.LK_NBLCK:
            calls += 1
            if calls <= 3:
                raise PermissionError(13, 'Permission denied')
        return real_locking(fd, mode, nbytes)

    monkeypatch.setattr(msvcrt, 'locking', flaky_locking)
    stream = repair._lock_factory_for_maintenance(tmp_path, timeout=5.0)
    try:
        assert calls == 4
        assert len(sleeps) == 3
        payload = json.loads(factory.lock_path(tmp_path).read_text(encoding='utf-8'))
        assert payload['maintenance'] is True
    finally:
        repair._unlock_factory_maintenance(stream)


def test_lock_factory_for_maintenance_fails_fast_if_live_pid_or_timeout_expired(tmp_path, monkeypatch):
    if os.name != 'nt':
        pytest.skip('Windows msvcrt locking path')
    import msvcrt

    def always_locked(*args):
        raise PermissionError(13, 'Permission denied')

    monkeypatch.setattr(msvcrt, 'locking', always_locked)

    # 1. Live PID present -> fail immediately with zero sleeps.
    sleeps = []
    monkeypatch.setattr(repair.time, 'sleep', lambda s: sleeps.append(s))
    monkeypatch.setattr(factory, 'running_pid', lambda root: 4242)
    with pytest.raises(factory.FactoryAlreadyRunning, match='4242'):
        repair._lock_factory_for_maintenance(tmp_path, timeout=5.0)
    assert sleeps == []

    # 2. No live PID -> retry up to timeout budget then raise.
    clock = {'now': 0.0}
    monkeypatch.setattr(factory, 'running_pid', lambda root: None)
    monkeypatch.setattr(repair.time, 'monotonic', lambda: clock['now'])
    monkeypatch.setattr(repair.time, 'sleep', lambda s: clock.__setitem__('now', clock['now'] + s))
    with pytest.raises(factory.FactoryAlreadyRunning, match='đang khởi động'):
        repair._lock_factory_for_maintenance(tmp_path, timeout=1.0)
    assert clock['now'] == pytest.approx(1.0)


def test_repair_once_does_not_burn_max_repairs_when_maintenance_infrastructure_fails(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects')
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    (logs / 'blocked.txt').write_text('ValueError: sha256 mismatch', encoding='utf-8')
    src = tmp_path / 'src/fix.py'
    src.parent.mkdir(parents=True)
    src.write_text('ok = False\n', encoding='utf-8')
    test_file = tmp_path / 'tests/test_fix.py'
    test_file.parent.mkdir(parents=True)
    test_file.write_text('def test_fix(): pass\n', encoding='utf-8')

    monkeypatch.setattr(repair, '_active', lambda *args: False)
    monkeypatch.setattr(factory, 'stop_background', lambda root: 13064)
    monkeypatch.setattr(factory, 'running_pid', lambda root: None)
    restarted = []
    monkeypatch.setattr(factory, 'start_background', lambda root: restarted.append(root) or 13065)
    monkeypatch.setattr(
        repair,
        '_lock_factory_for_maintenance',
        lambda root: (_ for _ in ()).throw(factory.FactoryAlreadyRunning('Xưởng đang chạy (PID đang khởi động).')),
    )

    def ask_repair(root, slug, role, step, *args):
        if step == 'repair_diagnose':
            return repair.Diagnosis(
                action='repair',
                cause='Fixture fault',
                evidence=['blocked.txt'],
                files=['src/fix.py'],
                tests=['tests/test_fix.py'],
                brief='Fix fault',
            )
        pytest.fail('repair_engineer must not run when _maintenance failed')

    monkeypatch.setattr(repair, '_ask', ask_repair)
    assert repair.repair_once(tmp_path, project.name) == 'awaiting_dev'
    report = read_yaml(logs / repair.REPORT)
    assert report['attempts'] == 0
    assert report.get('transient_failures', 0) == 0
    assert restarted == []
    assert list((tmp_path / 'topics/dev-tickets').glob(f'*-{project.name}.yaml'))


def test_main_updates_parent_identity_and_survives_maintenance_restart(tmp_path, monkeypatch):
    import sys

    state = {'pid': 1111, 'calls': 0}
    tokens = {1111: 'tok-1111', 2222: 'tok-2222'}

    monkeypatch.setattr(factory, 'running_pid', lambda root: state['pid'])
    monkeypatch.setattr(repair, 'process_token', lambda pid: tokens.get(pid))
    monkeypatch.setattr(repair, 'is_same_process', lambda pid, token: state['pid'] == pid and tokens.get(pid) == token)
    monkeypatch.setattr(repair, 'recover_interrupted_repairs', lambda root: False)
    monkeypatch.setattr(factory, 'projects', lambda root: [(tmp_path / 'proj', None)])

    def fake_repair_once(root, slug, **kwargs):
        state['calls'] += 1
        if state['calls'] == 1:
            # Simulate _maintenance stopping 1111 and starting 2222 with a brief startup window.
            repair._mark_factory_restarting(root, grace_seconds=15.0)
            state['pid'] = None
            return 'repair_failed'
        state['pid'] = None  # Normal factory shutdown after observing 2222.
        return 'idle'

    sleeps = {'count': 0}

    def fake_sleep(_seconds):
        sleeps['count'] += 1
        if state['pid'] is None and sleeps['count'] == 1:
            state['pid'] = 2222

    monkeypatch.setattr(repair, 'repair_once', fake_repair_once)
    monkeypatch.setattr(repair.time, 'sleep', fake_sleep)
    monkeypatch.setattr(sys, 'argv', [
        'repair_service', '--root', str(tmp_path),
        '--parent-pid', '1111', '--parent-token', 'tok-1111',
    ])

    repair.main()
    assert state['calls'] == 2
    assert sleeps['count'] >= 1
    assert not (tmp_path / repair.RESTARTING_STATE).exists()


@pytest.mark.parametrize('error', [ConnectionError('offline'), TimeoutError('late'),
                                 PermissionError('sharing violation')])
def test_temporary_infrastructure_failure_refunds_repair_with_total_cap(job, monkeypatch, error):
    root, project, logs, source, released, _ = job

    def fail(*args):
        raise error

    monkeypatch.setattr(repair, '_ask', fail)
    for index in range(repair.MAX_TRANSIENT_FAILURES):
        assert repair.repair_once(root, project.name) == 'cooldown'
        record = read_yaml(logs / repair.REPORT)
        assert record['attempts'] == 0
        assert record['transient_failures'] == index + 1
        record['retry_after'] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        write_yaml_atomic(logs / repair.REPORT, record)
    assert repair.repair_once(root, project.name) == 'exhausted'
    assert not released
    assert source.read_text(encoding='utf-8') == 'broken = True\n'


def _make_v2_project_in_state(projects_root, state: WorkflowState):
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.workflows.gate_review import approve_gate, reject_gate
    from tests.helpers import advance_v2_project_to_video_review

    now = datetime.now(UTC)
    if state in {WorkflowState.DRAFT_READY, WorkflowState.AWAITING_MEDICAL_REVIEW}:
        return create_v2_project_fixture(projects_root, state=state)
    if state == WorkflowState.NEEDS_MEDICAL_REVISION:
        proj = create_v2_project_fixture(projects_root, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
        reject_gate(
            proj, GateKind.MEDICAL, reviewer='Doc', reason='Fix storyboard',
            resume_state=WorkflowState.DRAFT_READY, now=now,
        )
        return proj
    if state in {WorkflowState.MEDICALLY_APPROVED, WorkflowState.PRODUCTION_IN_PROGRESS}:
        proj = create_v2_project_fixture(projects_root, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
        approve_gate(proj, GateKind.MEDICAL, reviewer='Doc', now=now)
        if state == WorkflowState.PRODUCTION_IN_PROGRESS:
            manifest = read_yaml(proj / 'project.yaml')
            manifest['state'] = WorkflowState.PRODUCTION_IN_PROGRESS.value
            write_yaml_atomic(proj / 'project.yaml', manifest)
        return proj
    proj = create_v2_project_fixture(projects_root, state=WorkflowState.DRAFT_READY)
    advance_v2_project_to_video_review(proj, now=now)
    if state == WorkflowState.AWAITING_VIDEO_REVIEW:
        return proj
    if state == WorkflowState.NEEDS_PRODUCTION_REVISION:
        reject_gate(
            proj, GateKind.VIDEO, reviewer='Doc', reason='Fix clip',
            resume_state=WorkflowState.PRODUCTION_IN_PROGRESS, now=now,
        )
        return proj
    if state == WorkflowState.VIDEO_APPROVED:
        approve_gate(proj, GateKind.VIDEO, reviewer='Doc', now=now)
        return proj
    raise AssertionError(f'Unsupported helper state: {state}')


def test_normalize_incident_reason_preserves_cooldown_and_max_repairs(job, monkeypatch):
    root, project, logs, _source, released, stages = job
    blocked = logs / 'blocked.txt'
    base_reason = 'agent không làm đổi trạng thái (revise_medical, trạng thái needs_medical_revision): giữ nguyên'
    variants = [
        f'{base_reason}\nlog_path: attempt-1.log\n',
        f'bước revise_medical: cần sửa đầu vào hoặc cấu hình; ValueError: {base_reason}',
        f'Bước produce: đang chờ thử lại lúc 2026-11-20T08:00:00Z; RuntimeError: {base_reason}',
        f'visual_review lỗi: ValueError: {base_reason}',
    ]
    assert {repair._normalize_incident_reason(text) for text in variants} == {base_reason}

    def ask_retry_declined(root, slug, role, step, *args):
        stages.append((role, step))
        if step == 'repair_diagnose':
            return repair.Diagnosis(action='retry', cause='Fixture fault', evidence=['fixture log'],
                                    brief='Verify transient recovery.')
        return repair.Acceptance(passed=False, reason='Still failing')

    monkeypatch.setattr(repair, '_ask', ask_retry_declined)
    blocked.write_text(variants[0], encoding='utf-8')
    assert repair.repair_once(root, project.name, respect_cooldown=True) == 'repair_failed'

    # Runner ticks wrap the same reason with a hold prefix and drop log_path: cooldown & budget stay intact.
    blocked.write_text(variants[1], encoding='utf-8')
    assert repair.repair_once(root, project.name, respect_cooldown=True) == 'cooldown'
    assert repair.repair_once(root, project.name, respect_cooldown=False) == 'repair_failed'
    assert repair.repair_once(root, project.name, respect_cooldown=False) == 'exhausted'
    assert stages.count(('coordinator_senior', 'repair_diagnose')) == repair.MAX_REPAIRS
    assert not released


def test_paths_and_repair_once_support_video_tests_vitest_and_typecheck(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects')
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    (logs / 'blocked.txt').write_text('SourceCardScene semicolon split bug', encoding='utf-8')

    tsx = tmp_path / 'video/src/scenes/SourceCardScene.tsx'
    tsx.parent.mkdir(parents=True)
    tsx.write_text('export const ok = false;\n', encoding='utf-8')
    tsx_test = tmp_path / 'video/src/scenes/SourceCardScene.test.tsx'
    tsx_test.write_text('test("ok", () => {});\n', encoding='utf-8')
    non_test = tmp_path / 'video/src/scenes/Helper.ts'
    non_test.write_text('export const x = 1;\n', encoding='utf-8')
    bad_test = tmp_path / 'tests/notes.txt'
    bad_test.parent.mkdir(parents=True)
    bad_test.write_text('not python\n', encoding='utf-8')
    (tmp_path / 'profiles').mkdir()
    (tmp_path / 'profiles/company.yaml').write_text('tiers: {}\n', encoding='utf-8')

    assert repair._paths(tmp_path, ['video/src/scenes/SourceCardScene.test.tsx'], tests=True) == [tsx_test.resolve()]
    for invalid in (
        'video/src/scenes/Helper.ts',
        'tests/notes.txt',
        'pnpm --dir video test',
        'profiles/company.yaml',
        f'projects/{project.name}/project.yaml',
    ):
        with pytest.raises(ValueError):
            repair._paths(tmp_path, [invalid], tests=True)

    monkeypatch.setattr(repair, '_active', lambda *args: False)
    monkeypatch.setattr(playbook, 'DEFAULT_AUTO_RETRIES', 0)
    released = []
    monkeypatch.setattr(repair, '_release', lambda *args: released.append(args))

    def ask(root, slug, role, step, *args):
        if step == 'repair_diagnose':
            return repair.Diagnosis(
                action='repair',
                cause='Semicolon boundary',
                evidence=['blocked.txt'],
                files=['video/src/scenes/SourceCardScene.tsx'],
                tests=['video/src/scenes/SourceCardScene.test.tsx'],
                brief='Split on semicolon.',
            )
        pytest.fail('repair_engineer must not be invoked')

    monkeypatch.setattr(repair, '_ask', ask)
    commands = []

    def run_ok(argv, **kwargs):
        commands.append(argv)
        return CompletedProcess(argv, 0, f'ok {argv[-1]}\n', '')

    assert repair.repair_once(tmp_path, project.name, run=run_ok) == 'awaiting_dev'
    assert commands == []
    assert released == []
    assert tsx.read_text(encoding='utf-8') == 'export const ok = false;\n'
    tickets = list((tmp_path / 'topics/dev-tickets').glob(f'*-{project.name}.yaml'))
    assert len(tickets) == 1
    ticket = read_yaml(tickets[0])
    assert ticket['files'] == ['video/src/scenes/SourceCardScene.tsx']
    assert ticket['tests'] == ['video/src/scenes/SourceCardScene.test.tsx']


def test_delegate_content_fix_routes_new_roles_writes_leader_guidance_and_respects_gates(tmp_path, monkeypatch):
    monkeypatch.setattr(repair, '_active', lambda *args: False)
    released = []
    monkeypatch.setattr(repair, '_release', lambda root, slug: released.append((root, slug)))

    # 1. editor and storyboard_director at NEEDS_MEDICAL_REVISION -> leader-guidance.yaml (revise_medical), keep state
    for role in ('editor', 'storyboard_director'):
        root = tmp_path / f'med_rev_{role}'
        proj = _make_v2_project_in_state(root / 'projects', WorkflowState.NEEDS_MEDICAL_REVISION)
        logs = root / 'topics/logs' / proj.name
        logs.mkdir(parents=True)
        (logs / 'blocked.txt').write_text('agent không làm đổi trạng thái', encoding='utf-8')
        monkeypatch.setattr(
            repair, '_ask',
            lambda *args, _role=role: repair.Diagnosis(
                action='delegate', delegate_role=_role, cause='Need storyboard fix',
                evidence=['log'], brief=f'Fix storyboard as {_role}',
            ),
        )
        assert repair.repair_once(root, proj.name) == 'retry_requested'
        assert read_yaml(proj / 'project.yaml')['state'] == WorkflowState.NEEDS_MEDICAL_REVISION.value
        guidance = read_yaml(logs / 'leader-guidance.yaml')
        assert guidance['revision'] == '001'
        assert guidance['role'] == role
        assert guidance['step'] == 'revise_medical'
        assert guidance['brief'] == f'Fix storyboard as {role}'
        assert guidance['at']
        assert (root, proj.name) in released

    # 2. DRAFT_READY routes storyboard_director -> storyboard_design and voice_director -> voice_prep
    for role, expected_step in (('storyboard_director', 'storyboard_design'), ('voice_director', 'voice_prep')):
        root = tmp_path / f'draft_{role}'
        proj = _make_v2_project_in_state(root / 'projects', WorkflowState.DRAFT_READY)
        logs = root / 'topics/logs' / proj.name
        logs.mkdir(parents=True)
        (logs / 'blocked.txt').write_text('Draft artifact invalid', encoding='utf-8')
        monkeypatch.setattr(
            repair, '_ask',
            lambda *args, _role=role, _step=expected_step: repair.Diagnosis(
                action='delegate', delegate_role=_role, cause='Artifact issue',
                evidence=['log'], brief=f'Fix {_step}',
            ),
        )
        assert repair.repair_once(root, proj.name) == 'retry_requested'
        assert read_yaml(logs / 'leader-guidance.yaml')['step'] == expected_step

    # 3. PRODUCTION_IN_PROGRESS with shorts_producer -> leader-guidance.yaml (shorts_plan)
    root_s = tmp_path / 'prod_shorts'
    proj_s = _make_v2_project_in_state(root_s / 'projects', WorkflowState.PRODUCTION_IN_PROGRESS)
    logs_s = root_s / 'topics/logs' / proj_s.name
    logs_s.mkdir(parents=True)
    (logs_s / 'blocked.txt').write_text('Invalid shorts-plan.yaml', encoding='utf-8')
    monkeypatch.setattr(
        repair, '_ask',
        lambda *args: repair.Diagnosis(
            action='delegate', delegate_role='shorts_producer', cause='Clip bounds mismatch',
            evidence=['log'], brief='Rebuild shorts-plan within bounds',
        ),
    )
    assert repair.repair_once(root_s, proj_s.name) == 'retry_requested'
    assert read_yaml(logs_s / 'leader-guidance.yaml')['step'] == 'shorts_plan'
    assert read_yaml(proj_s / 'project.yaml')['state'] == WorkflowState.PRODUCTION_IN_PROGRESS.value

    # 4. Protected work still requires the doctor after approval or at the video gate.
    for role, state in (
        ('writer', WorkflowState.MEDICALLY_APPROVED),
        ('medical_expert', WorkflowState.MEDICALLY_APPROVED),
        ('storyboard_director', WorkflowState.PRODUCTION_IN_PROGRESS),
        ('voice_director', WorkflowState.NEEDS_PRODUCTION_REVISION),
        ('shorts_producer', WorkflowState.AWAITING_VIDEO_REVIEW),
    ):
        root_g = tmp_path / f'gate_{role}_{state.value}'
        proj_g = _make_v2_project_in_state(root_g / 'projects', state)
        logs_g = root_g / 'topics/logs' / proj_g.name
        logs_g.mkdir(parents=True)
        (logs_g / 'blocked.txt').write_text('Post-gate issue', encoding='utf-8')
        monkeypatch.setattr(
            repair, '_ask',
            lambda *args, _role=role: repair.Diagnosis(
                action='delegate', delegate_role=_role, cause='Requires doctor',
                evidence=['log'], brief='Needs reopen',
                requires_doctor='gate' if _role == 'storyboard_director' else None,
            ),
        )
        assert repair.repair_once(root_g, proj_g.name) == 'needs_attention'
        delegation = read_yaml(logs_g / repair.REPORT)['delegation']
        assert delegation['requires_doctor_reopen'] is True
        assert delegation['status'] == 'awaiting_doctor_reopen'
        assert not (logs_g / 'leader-guidance.yaml').exists()

    # 5. If _release raises, newly created leader-guidance.yaml is cleaned up
    root_r = tmp_path / 'release_fail'
    proj_r = _make_v2_project_in_state(root_r / 'projects', WorkflowState.NEEDS_MEDICAL_REVISION)
    logs_r = root_r / 'topics/logs' / proj_r.name
    logs_r.mkdir(parents=True)
    (logs_r / 'blocked.txt').write_text('Release check error', encoding='utf-8')
    monkeypatch.setattr(repair, '_release', lambda *args: (_ for _ in ()).throw(ValueError('release blocked')))
    monkeypatch.setattr(
        repair, '_ask',
        lambda *args: repair.Diagnosis(
            action='delegate', delegate_role='editor', cause='Storyboard issue',
            evidence=['log'], brief='Fix storyboard',
        ),
    )
    assert repair.repair_once(root_r, proj_r.name) == 'repair_failed'
    assert not (logs_r / 'leader-guidance.yaml').exists()


def test_retry_project_allow_repair_release_and_orphaned_chat_step_marker(tmp_path, monkeypatch):
    from healthvideo.workflows import chat, dashboard_operations, production_retry

    project = _make_v2_project_in_state(tmp_path / 'projects', WorkflowState.MEDICALLY_APPROVED)
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    monkeypatch.setattr(dashboard_operations.factory, 'running_pid', lambda _: None)
    monkeypatch.setattr(dashboard_operations, '_retry_api', lambda: production_retry)
    production_retry.record_failure(
        tmp_path, project, WorkflowState.MEDICALLY_APPROVED, ValueError('visual budget failed'),
    )
    (logs / 'blocked.txt').write_text('visual budget failed', encoding='utf-8')

    # Without allow_repair_release, unchanged validation failure stays held.
    with pytest.raises(ValueError, match='visual budget failed'):
        dashboard_operations.retry_project(tmp_path, project.name, expected_revision='001')

    # Empty .chat-step-running marker still blocks retry.
    step_marker = logs / chat.STEP_MARKER
    step_marker.touch()
    with pytest.raises(ValueError, match='Bước đang chạy'):
        dashboard_operations.retry_project(
            tmp_path, project.name, expected_revision='001', allow_repair_release=True,
        )

    # Live .chat-step-running marker still blocks retry.
    live_token = process_token(os.getpid())
    assert live_token
    step_marker.write_text(
        json.dumps({'pid': os.getpid(), 'process_token': live_token}), encoding='utf-8',
    )
    with pytest.raises(ValueError, match='Bước đang chạy'):
        dashboard_operations.retry_project(
            tmp_path, project.name, expected_revision='001', allow_repair_release=True,
        )

    # Orphaned .chat-step-running with dead PID is cleaned up and allow_repair_release releases the hold.
    step_marker.write_text(
        json.dumps({'pid': 999999, 'process_token': 'dead-token'}), encoding='utf-8',
    )
    result = dashboard_operations.retry_project(
        tmp_path, project.name, expected_revision='001', allow_repair_release=True,
    )
    assert not step_marker.exists()
    assert not (logs / 'blocked.txt').exists()
    assert not (logs / 'production-retry.yaml').exists()
    assert result['retry_status']['allowed'] is True


def test_station12_stop_video_qa_error_yaml_resilience_and_fingerprints(tmp_path, monkeypatch):
    from healthvideo.workflows import dashboard, production_retry, telegram_bot

    project = _make_v2_project_in_state(tmp_path / 'projects', WorkflowState.PRODUCTION_IN_PROGRESS)
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)

    # 1. 'Trạm 12 chưa đạt' stops at needs_attention after default auto-retries are exhausted
    monkeypatch.setattr(playbook, 'DEFAULT_AUTO_RETRIES', 0)
    called = []
    monkeypatch.setattr(repair, '_ask', lambda *args: called.append(args))
    (logs / 'blocked.txt').write_text('Trạm 12 chưa đạt sau các vòng sửa; cần xử lý nhận xét.', encoding='utf-8')
    assert repair.repair_once(tmp_path, project.name) == 'needs_attention'
    assert len(called) <= 1

    # 2. _verify_retry_validated rejects video-qa.json with status == 'error'
    (logs / 'blocked.txt').unlink()
    qa_path = project / 'revisions/001/renders/video-qa.json'
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    qa_path.write_text(json.dumps({'status': 'error'}), encoding='utf-8')
    layout = repair.resolve_project_layout(project)
    monkeypatch.setattr(repair, '_has_post_retry_activity', lambda *args: True)
    monkeypatch.setattr(repair.script_review, 'require_passed_review', lambda *args: None)
    monkeypatch.setattr(repair.product_review, 'require_passed_review', lambda *args: None)
    ok, err, _ = repair._verify_retry_validated(tmp_path, project.name, layout, logs, {'state_before': 'draft_ready'})
    assert not ok
    assert 'video-qa.json báo lỗi' in err

    # 3. Corrupt YAML in leader-repair.yaml does not crash repair_once
    (logs / repair.REPORT).write_text('bad: [yaml', encoding='utf-8')
    assert repair.repair_once(tmp_path, project.name) == 'repair_failed'

    # 4. production_fingerprint & agent_fingerprint track tools/*.py and leader-guidance.yaml
    tool_file = tmp_path / 'tools/helper.py'
    tool_file.parent.mkdir(parents=True)
    tool_file.write_text('x = 1\n', encoding='utf-8')
    prod_fp0 = production_retry.production_fingerprint(tmp_path, project, WorkflowState.PRODUCTION_IN_PROGRESS)
    agent_fp0 = production_retry.agent_fingerprint(tmp_path, project, 'revise_production', 'brief')
    tool_file.write_text('x = 2\n', encoding='utf-8')
    assert production_retry.production_fingerprint(tmp_path, project, WorkflowState.PRODUCTION_IN_PROGRESS) != prod_fp0
    assert production_retry.agent_fingerprint(tmp_path, project, 'revise_production', 'brief') != agent_fp0
    prod_fp1 = production_retry.production_fingerprint(tmp_path, project, WorkflowState.PRODUCTION_IN_PROGRESS)
    agent_fp1 = production_retry.agent_fingerprint(tmp_path, project, 'revise_production', 'brief')
    (logs / 'leader-guidance.yaml').write_text("revision: '001'\nstep: revise_production\n", encoding='utf-8')
    assert production_retry.production_fingerprint(tmp_path, project, WorkflowState.PRODUCTION_IN_PROGRESS) != prod_fp1
    assert production_retry.agent_fingerprint(tmp_path, project, 'revise_production', 'brief') != agent_fp1

    # 5. dashboard default_actions.start and telegram /xuong_start ensure repair_service
    ensured = []
    monkeypatch.setattr(factory, 'start_background', lambda root: 4242)
    monkeypatch.setattr(repair, 'ensure_background', lambda root: ensured.append(root) or 5252)
    srv = dashboard.DashboardServer(tmp_path, 0, token='tok', agents=list)
    try:
        actions = dashboard.default_actions(srv)
        assert '4242' in actions['factory/start']()
        assert ensured == [tmp_path]
    finally:
        srv.server_close()

    sent = []
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'tok')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', '555001')
    state = telegram_bot.load_state(tmp_path)
    telegram_bot.handle_update(
        tmp_path,
        state,
        {'update_id': 1, 'message': {'message_id': 1, 'chat': {'id': 555001}, 'text': '/xuong_start'}},
        send_fn=lambda text, **kw: sent.append(text),
        typing=False,
    )
    assert ensured == [tmp_path, tmp_path]
    assert '4242' in sent[-1]


def test_factory_package_writes_and_clears_blocked_and_resists_yaml_errors(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    project = _make_v2_project_in_state(tmp_path / 'projects', WorkflowState.VIDEO_APPROVED)
    bad_proj = tmp_path / 'projects/corrupt-topic'
    bad_proj.mkdir(parents=True)
    (bad_proj / 'project.yaml').write_text('bad: [yaml', encoding='utf-8')
    assert [p.name for p, _ in factory.projects(tmp_path)] == [project.name]

    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    monkeypatch.setattr(factory, 'run_queue', lambda *a, **kw: SimpleNamespace(waiting_model=[], blocked=[]))
    monkeypatch.setattr(factory, 'notify', lambda *a, **kw: True)
    monkeypatch.setattr(factory, 'package_project', lambda p: (_ for _ in ()).throw(ValueError('missing mp4')))
    factory.run_factory(tmp_path, SimpleNamespace(), once=True, echo=lambda *_: None)
    assert 'bị chặn đóng gói: missing mp4' in (logs / 'blocked.txt').read_text(encoding='utf-8')

    monkeypatch.setattr(factory, 'package_project', lambda p: p)
    factory.run_factory(tmp_path, SimpleNamespace(), once=True, echo=lambda *_: None)
    assert not (logs / 'blocked.txt').exists()

    # repair_service.main() catches yaml.YAMLError from factory.projects(root) without crashing.
    pids = iter([1111, 1111, None])
    monkeypatch.setattr(factory, 'running_pid', lambda root: next(pids, None))
    monkeypatch.setattr(repair.time, 'sleep', lambda s: None)
    (tmp_path / 'topics/queue.yaml').write_text('bad: [yaml', encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['repair_service', '--root', str(tmp_path)])
    repair.main()


def test_repair_waiting_idle_reuses_diagnosis_and_escalates_on_stops(tmp_path, monkeypatch):
    from healthvideo.workflows import doctor_questions

    project = _make_v2_project_in_state(tmp_path / 'projects', WorkflowState.MEDICALLY_APPROVED)
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    blocked = logs / 'blocked.txt'
    blocked.write_text('bước produce lỗi: timeout', encoding='utf-8')
    target_src = tmp_path / 'src/healthvideo/workflows/sample.py'
    target_test = tmp_path / 'tests/workflows/test_sample.py'
    target_src.parent.mkdir(parents=True, exist_ok=True)
    target_test.parent.mkdir(parents=True, exist_ok=True)
    target_src.write_text('x = 1\n', encoding='utf-8')
    target_test.write_text('def test_ok(): assert True\n', encoding='utf-8')
    (tmp_path / 'tests/workflows/test_script_review.py').write_text('def test_sr(): assert True\n', encoding='utf-8')
    (tmp_path / 'tests/workflows/test_product_review.py').write_text('def test_pr(): assert True\n', encoding='utf-8')

    active = {'value': True}
    monkeypatch.setattr(repair, '_active', lambda root, slug=None: active['value'] and slug is None)

    steps_called: list[str] = []

    def fake_ask(root, slug, role, step, ctx, out_path, model_cls, invoke):
        steps_called.append(step)
        if step == 'repair_diagnose':
            return repair.Diagnosis(
                action='repair',
                cause='Lỗi timeout nhỏ',
                evidence=['blocked.txt: timeout'],
                files=['src/healthvideo/workflows/sample.py'],
                tests=['tests/workflows/test_sample.py'],
                brief='Sửa timeout',
            )
        if step == 'repair':
            return repair.RepairResult(status='ready', summary='Đã sửa')
        return repair.Acceptance(passed=True, reason='Đạt')

    monkeypatch.setattr(repair, '_ask', fake_ask)
    monkeypatch.setattr(repair, '_check_scope', lambda *a, **k: [])

    # action=repair opens a dev ticket immediately without waiting for idle or running repair_engineer
    assert repair.repair_once(tmp_path, project.name) == 'awaiting_dev'
    assert doctor_questions.open_question(tmp_path, project.name) is None
    assert steps_called == ['repair_diagnose']
    assert list((tmp_path / 'topics/dev-tickets').glob(f'*-{project.name}.yaml'))

    # Second call stays awaiting_dev without re-diagnosing
    active['value'] = False
    assert repair.repair_once(tmp_path, project.name) == 'awaiting_dev'
    assert steps_called == ['repair_diagnose']

    # When exhausted (with default auto-retries disabled) -> escalates with kind='escalation' and 3 options
    monkeypatch.setattr(playbook, 'DEFAULT_AUTO_RETRIES', 0)
    blocked.write_text('bước produce lỗi: timeout', encoding='utf-8')
    rec = read_yaml(logs / repair.REPORT)
    rec['phase'] = 'repair_failed'
    rec['incident'] = {
        'state': read_yaml(project / 'project.yaml')['state'],
        'reason': repair._normalize_incident_reason('bước produce lỗi: timeout'),
    }
    rec['attempts'] = rec['attempts_before_incident'] + repair.MAX_REPAIRS
    write_yaml_atomic(logs / repair.REPORT, rec)
    assert repair.repair_once(tmp_path, project.name) == 'exhausted'
    esc = doctor_questions.open_question(tmp_path, project.name)
    assert esc is not None and esc['kind'] == 'escalation'
    assert [opt['id'] for opt in esc['options']] == [
        'retry_repair_cycle', 'reopen_or_delegate', 'pause_project',
    ]

    blocked.unlink()
    assert repair.repair_once(tmp_path, project.name) == 'idle'
    assert doctor_questions.open_question(tmp_path, project.name) is None


def test_delegate_post_product_review_routes_to_revise_product_and_escapes_needs_production_revision(
    tmp_path, monkeypatch
):
    from healthvideo.workflows import change_request, product_review

    monkeypatch.setattr(repair, '_active', lambda *args: False)
    released = []
    monkeypatch.setattr(repair, '_release', lambda root, slug: released.append((root, slug)))

    for idx, (start_state, role) in enumerate([
        (WorkflowState.PRODUCTION_IN_PROGRESS, 'storyboard_director'),
        (WorkflowState.PRODUCTION_IN_PROGRESS, 'editor'),
        (WorkflowState.NEEDS_PRODUCTION_REVISION, 'editor'),
        (WorkflowState.MEDICALLY_APPROVED, 'storyboard_director'),
        (WorkflowState.MEDICALLY_APPROVED, 'editor'),
    ]):
        root = tmp_path / f'post_pr_{idx}'
        entry_state = (WorkflowState.PRODUCTION_IN_PROGRESS
                       if start_state == WorkflowState.NEEDS_PRODUCTION_REVISION else start_state)
        proj = _make_v2_project_in_state(root / 'projects', entry_state)
        write_yaml_atomic(proj / 'revisions/001' / product_review.LOG, {'version': 1, 'submitted': 0, 'rounds': []})
        if start_state == WorkflowState.NEEDS_PRODUCTION_REVISION:
            change_request.request_change(
                proj,
                'edit_production',
                'Restore outro',
                {'source': 'leader-repair', 'revision': '001'},
                now=datetime.now(UTC),
            )
            assert read_yaml(proj / 'project.yaml')['state'] == WorkflowState.NEEDS_PRODUCTION_REVISION.value

        logs = root / 'topics/logs' / proj.name
        logs.mkdir(parents=True, exist_ok=True)
        (logs / 'blocked.txt').write_text('ValueError: M6.4 final scene must be nonmedical brand_outro', encoding='utf-8')
        monkeypatch.setattr(
            repair, '_ask',
            lambda *args, _role=role: repair.Diagnosis(
                action='delegate',
                delegate_role=_role,
                cause='S36 changed from brand_outro to whiteboard',
                evidence=['blocked.txt'],
                brief='Khoi phuc S36 ve brand_outro theo M6.4.',
            ),
        )
        assert repair.repair_once(root, proj.name) == 'retry_requested'
        assert read_yaml(proj / 'project.yaml')['state'] == entry_state.value
        guidance = read_yaml(logs / 'leader-guidance.yaml')
        assert guidance['step'] == 'revise_product'
        assert guidance['role'] == 'editor'
        assert 'S36' in guidance['brief']
        assert not change_request.pending(proj)
        assert (root, proj.name) in released


def test_escalation_fingerprint_changes_after_answered_cycle_even_without_leader_repair(tmp_path, monkeypatch):
    from healthvideo.workflows import doctor_questions

    project = _make_v2_project_in_state(tmp_path / 'projects', WorkflowState.PRODUCTION_IN_PROGRESS)
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    (logs / 'blocked.txt').write_text('bước produce lỗi: M6.4 final scene must be nonmedical brand_outro', encoding='utf-8')
    monkeypatch.setattr(repair, '_active', lambda *args: False)
    monkeypatch.setattr(
        repair, '_ask',
        lambda *args: repair.Diagnosis(
            action='hold',
            cause='Cần quyết định.',
            evidence=['blocked.txt'],
            brief='Can chi dao.',
            requires_doctor='gate',
            doctor_options=[
                repair.DoctorOption(
                    label='Sửa lại brand_outro',
                    detail='Giao thợ dựng khôi phục cảnh kết.',
                    action='delegate',
                    delegate_role='editor',
                    direction='Khôi phục S36 về brand_outro.',
                ),
                repair.DoctorOption(
                    label='Giữ nguyên và chạy lại',
                    detail='Chạy lại kiểm tra một vòng nữa.',
                    action='retry_cycle',
                    direction='Kiểm tra lại cảnh kết S36.',
                ),
            ],
        ),
    )

    assert repair.repair_once(tmp_path, project.name) == 'needs_attention'
    q1 = doctor_questions.open_question(tmp_path, project.name)
    assert q1 is not None

    doctor_questions.answer(tmp_path, project.name, q1['id'], option_id='opt-1')
    (logs / repair.REPORT).unlink(missing_ok=True)

    assert repair.repair_once(tmp_path, project.name) == 'needs_attention'
    q2 = doctor_questions.open_question(tmp_path, project.name)
    assert q2 is not None and q2['id'] != q1['id']
    assert q2['fingerprint'] != q1['fingerprint']


def test_r5_diagnosis_cannot_restart_sixty_times(job, monkeypatch):
    root, project, logs, _source, released, stages = job
    revision = project / 'revisions/001'
    write_yaml_atomic(revision / 'workflow/standards.yaml',
                      {'quality_standard': {'profile': 'r5_v1'}})

    def ask_retry_declined(root, slug, role, step, *args):
        stages.append((role, step))
        if step == 'repair_diagnose':
            return repair.Diagnosis(action='retry', cause='Fixture fault', evidence=['fixture log'],
                                    brief='Verify transient recovery.')
        return repair.Acceptance(passed=False, reason='Still failing')

    monkeypatch.setattr(repair, '_ask', ask_retry_declined)
    for _ in range(60):
        # Simulate recovery/reset of the old ephemeral incident counter.
        (logs / repair.REPORT).unlink(missing_ok=True)
        repair.repair_once(root, project.name)
    assert sum(step == 'repair_diagnose' for _, step in stages) == 2
    assert released == []
