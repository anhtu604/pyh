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
from healthvideo.workflows import factory
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
        assert kwargs['shell'] is False
        assert not released
        commands.append(argv)
        return CompletedProcess(argv, 0, 'passed', '')

    assert repair.repair_once(root, project.name, run=run) == 'retry_requested'
    assert stages == [('coordinator_senior', 'repair_diagnose'), ('repair_engineer', 'repair'),
                      ('coordinator_senior', 'repair_accept')]
    assert len(commands) == 2
    assert any('test_script_review.py' in str(part) for part in commands[0])
    assert released == [(root, project.name)]
    assert 'False' in source.read_text()
    assert read_yaml(logs / repair.REPORT)['acceptance']['passed'] is True


def test_failed_tests_restore_original_code_and_never_release_retry(job):
    root, project, logs, source, released, stages = job
    before = source.read_bytes()
    run = lambda argv, **kwargs: CompletedProcess(argv, 1, '', 'failed regression')
    assert repair.repair_once(root, project.name, run=run) == 'repair_failed'
    assert source.read_bytes() == before
    assert released == []
    assert not any(step == 'repair_accept' for _, step in stages)
    repair.repair_once(root, project.name, run=run)
    assert repair.repair_once(root, project.name, run=run) == 'exhausted'
    assert read_yaml(logs / repair.REPORT)['attempts'] == repair.MAX_REPAIRS
    assert read_yaml(logs / repair.REPORT)['phase'] == 'needs_attention'


def test_new_block_reason_gets_repair_after_previous_budget_is_exhausted(job):
    root, project, logs, _, _, stages = job
    blocked = logs / 'blocked.txt'
    run = lambda argv, **kwargs: CompletedProcess(argv, 1, '', 'failed regression')
    for attempt in range(repair.MAX_REPAIRS):
        blocked.write_text(f'First fault\nlog_path: attempt-{attempt}.log\n', encoding='utf-8')
        assert repair.repair_once(root, project.name, run=run) == 'repair_failed'
    blocked.write_text('First fault\nlog_path: latest.log\n', encoding='utf-8')
    assert repair.repair_once(root, project.name, run=run) == 'exhausted'

    blocked.write_text('Different fault\nlog_path: current.log\n', encoding='utf-8')
    assert repair.repair_once(root, project.name, run=run) == 'repair_failed'
    assert stages.count(('coordinator_senior', 'repair_diagnose')) == repair.MAX_REPAIRS + 1


def test_declined_acceptance_restores_code_and_keeps_hold(job, monkeypatch):
    root, project, _, source, released, _ = job
    ask = repair._ask

    def decline(root, slug, role, step, *args):
        if step == 'repair_accept':
            return repair.Acceptance(passed=False, reason='Cause still unresolved')
        return ask(root, slug, role, step, *args)

    monkeypatch.setattr(repair, '_ask', decline)
    before = source.read_bytes()
    assert repair.repair_once(root, project.name, run=lambda argv, **kw:
                              CompletedProcess(argv, 0, 'passed', '')) == 'repair_failed'
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

    root, project, logs, _, released, stages = job
    path = logs / repair.REPORT
    original = {'revision': '001', 'attempts': 1, 'phase': 'repair_failed'}
    write_yaml_atomic(path, original)
    detail = f'chấm kịch bản lỗi: {CYCLE_LIMIT_REASON} (6 vòng); Bác sĩ gửi hướng dẫn qua chat.'
    (logs / 'blocked.txt').write_text(detail, encoding='utf-8')
    for _ in range(2):
        assert repair.repair_once(root, project.name) == 'needs_attention'
    assert read_yaml(path) == original
    assert (logs / 'blocked.txt').read_text(encoding='utf-8') == detail
    assert not stages and not released


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

    monkeypatch.setattr(repair, '_active', lambda *args: False)
    monkeypatch.setattr(factory, 'stop_background', lambda root: None)
    monkeypatch.setattr(factory, 'running_pid', lambda root: None)

    def ask_out_of_scope(root, slug, role, step, *args):
        if step == 'repair_diagnose':
            return repair.Diagnosis(action='repair', cause='Bug', evidence=['log'],
                                    files=['src/assigned.py'], tests=['tests/test_assigned.py'],
                                    brief='Fix assigned.py only')
        # Engineer modifies assigned.py AND touches other.py AND creates rogue.py
        assigned.write_text('v = 2\n', encoding='utf-8')
        other.write_text('hijacked = True\n', encoding='utf-8')
        (tmp_path / 'src/rogue.py').write_text('rogue = True\n', encoding='utf-8')
        return repair.RepairResult(status='ready', summary='Done')

    monkeypatch.setattr(repair, '_ask', ask_out_of_scope)
    assert repair.repair_once(tmp_path, project.name) == 'repair_failed'
    assert assigned.read_text(encoding='utf-8') == 'v = 1\n'
    assert other.read_text(encoding='utf-8') == 'uncommitted_by_other = True\n'
    assert not (tmp_path / 'src/rogue.py').exists()
    assert 'ngoài phạm vi' in read_yaml(logs / repair.REPORT)['error']


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

    # Case D: editor in PRODUCTION_IN_PROGRESS -> transitions to NEEDS_PRODUCTION_REVISION, preserves medical gate
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
            evidence=['render log'], brief='Adjust scene 2 timing',
        ),
    )
    assert repair.repair_once(root_d, proj_d.name) == 'retry_requested'
    assert read_yaml(proj_d / 'project.yaml')['state'] == WorkflowState.NEEDS_PRODUCTION_REVISION.value


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

    # Timeout during repair also rolls back and enters cooldown
    write_yaml_atomic(logs / repair.REPORT, {'revision': '001', 'attempts': 0})

    def ask_timeout(root, slug, role, step, *args):
        if step == 'repair_diagnose':
            return repair.Diagnosis(action='repair', cause='Bug', evidence=['log'],
                                    files=['src/fault.py'], tests=['tests/test_fault.py'],
                                    brief='Fix it')
        source.write_text('partial = True\n', encoding='utf-8')
        raise subprocess.TimeoutExpired(['codex'], 600)

    monkeypatch.setattr(repair, '_ask', ask_timeout)
    assert repair.repair_once(root, project.name) == 'cooldown'
    assert source.read_bytes() == before


def test_isolated_smoke_chain_leader_engineer_test_accept_retry_validated(tmp_path, monkeypatch):
    """End-to-end isolated smoke fixture: Leader -> engineer -> real pytest -> Leader accept -> retry -> validated."""
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    logs = tmp_path / 'topics/logs' / project.name
    logs.mkdir(parents=True)
    (logs / 'blocked.txt').write_text('ZeroDivisionError in helper', encoding='utf-8')

    src = tmp_path / 'src/calc.py'
    src.parent.mkdir(parents=True)
    src.write_text('def ratio(a, b):\n    return a / b\n', encoding='utf-8')

    unit_test = tmp_path / 'tests/test_calc.py'
    unit_test.parent.mkdir(parents=True)
    unit_test.write_text(
        'import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))\n'
        'from calc import ratio\n\ndef test_ratio():\n    assert ratio(4, 2) == 2\n    assert ratio(4, 0) == 0\n',
        encoding='utf-8',
    )
    gate_dir = tmp_path / 'tests/workflows'
    gate_dir.mkdir(parents=True)
    (gate_dir / 'test_script_review.py').write_text('def test_gate_s(): pass\n', encoding='utf-8')
    (gate_dir / 'test_product_review.py').write_text('def test_gate_p(): pass\n', encoding='utf-8')

    monkeypatch.setattr(factory, 'stop_background', lambda root: None)
    monkeypatch.setattr(factory, 'running_pid', lambda root: None)
    monkeypatch.setattr(repair, '_release', lambda root, slug: (logs / 'blocked.txt').unlink(missing_ok=True))

    def ask_smoke(root, slug, role, step, *args):
        if step == 'repair_diagnose':
            return repair.Diagnosis(
                action='repair', cause='Division by zero', evidence=['blocked.txt'],
                files=['src/calc.py'], tests=['tests/test_calc.py'],
                brief='Handle b == 0 in ratio()',
            )
        if step == 'repair':
            src.write_text('def ratio(a, b):\n    return 0 if b == 0 else a / b\n', encoding='utf-8')
            return repair.RepairResult(status='ready', summary='Handled zero divisor')
        return repair.Acceptance(passed=True, reason='Real pytest passed')

    monkeypatch.setattr(repair, '_ask', ask_smoke)

    def run_pytest_only(argv, **kwargs):
        if 'ruff' in argv:
            return CompletedProcess(argv, 0, '', '')
        return subprocess.run(argv, check=False, **kwargs)

    assert repair.repair_once(tmp_path, project.name, run=run_pytest_only) == 'retry_requested'
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

    # Subsequent repair_once can run normally
    assert repair.repair_once(root, project.name, run=lambda argv, **kw: CompletedProcess(argv, 0, 'ok', '')) == 'retry_requested'


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
