import json
import os
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner, _NamedTextIOWrapper

from healthvideo import cli
from healthvideo.approver_pin import set_pin
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import factory
from healthvideo.workflows.runner import RunReport
from tests.helpers import create_v2_project_fixture


@pytest.fixture
def operator(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    pin = tmp_path / 'config' / 'approver-pin.json'
    set_pin('918273', path=pin)
    monkeypatch.setattr(cli, 'pin_path', lambda: pin)
    monkeypatch.setattr(_NamedTextIOWrapper, 'isatty', lambda self: True)
    monkeypatch.setattr(cli.getpass, 'getpass', lambda _: '918273')
    monkeypatch.setattr(factory, 'open_packet', lambda _: None)
    monkeypatch.setattr(factory, 'running_pid', lambda _: 123)
    return tmp_path, project, pin.parent / 'operator.yaml'


def invoke(operator, text):
    return CliRunner().invoke(cli.app, ['duyet', '--root', str(operator[0])], input=text)


def test_duyet_approve_flow(operator):
    result = invoke(operator, 'Doctor\nA\n\n')
    assert result.exit_code == 0, result.output
    assert read_yaml(operator[1] / 'project.yaml')['state'] == 'medically_approved'
    packet = next((operator[0] / 'cache/review').glob('*.html'))
    assert '<base href="file:' in packet.read_text(encoding='utf-8')


@pytest.mark.parametrize('pin,accepted', [('wrong', False), ('918273', True)])
def test_duyet_pronunciation_acceptance_requires_pin(operator, monkeypatch, pin, accepted):
    import json

    from tests.helpers import advance_v2_project_to_video_review

    project = operator[1]
    # The helper creates normal approval/render artifacts from the draft fixture.
    data = read_yaml(project / 'project.yaml')
    data['state'] = 'draft_ready'
    write_yaml_atomic(project / 'project.yaml', data)
    advance_v2_project_to_video_review(project, now=datetime.now(UTC))
    revision = project / 'revisions/001'
    (revision / 'reviews/pronunciation-qa.json').write_text(json.dumps({
        'flags': [{'line': 'LN01', 'script_word': 'gút', 'heard': 'gao',
                   'start': 0, 'end': 1, 'priority': 'term',
                   'severity': 'block', 'suggestion': 'Nghe lại'}],
    }), encoding='utf-8')
    monkeypatch.setattr(cli.getpass, 'getpass', lambda _: pin)
    result = invoke(operator, 'Doctor\nP\nĐã nghe, chấp nhận\n')
    approval = revision / 'reviews/video-approval.yaml'
    assert approval.exists() is accepted, result.output
    assert (result.exit_code == 0) is accepted, result.output
    if accepted:
        assert read_yaml(approval)['pronunciation_acceptance']


def test_duyet_reject_default_resume_medical(operator):
    result = invoke(operator, 'Doctor\nR\nCần sửa\n\n')
    assert result.exit_code == 0, result.output
    data = read_yaml(operator[1] / 'project.yaml')
    assert data['state'] == 'needs_medical_revision'
    assert data['side_state']['resume_state'] == 'draft_ready'


def test_duyet_reject_video_semantic_uses_reason_code(operator):
    path = operator[1] / 'project.yaml'
    data = read_yaml(path)
    data['state'] = 'awaiting_video_review'
    write_yaml_atomic(path, data)
    result = invoke(operator, 'Doctor\nR\nSai nội dung\n2\n')
    assert result.exit_code == 0, result.output
    data = read_yaml(path)
    assert data['side_state']['resume_state'] == 'draft_ready'
    assert data['side_state']['reason_code'] == 'semantic_issue'
    rejection = next((operator[1] / 'revisions/001/reviews/video').glob('*rejected.yaml'))
    assert read_yaml(rejection)['reason'] == 'Sai nội dung'


def test_semantic_rejection_creates_revision_and_can_be_approved_again(operator, monkeypatch):
    from healthvideo.workflows.draft import submit_medical_review
    from healthvideo.workflows.factory_deps import reject_note
    from tests.workflows.test_package import _v2_awaiting_video_review_project

    project = _v2_awaiting_video_review_project(operator[0] / 'projects')
    revision = project / 'revisions/001'
    old_approval = (revision / 'reviews/medical-approval.yaml').read_bytes()
    assert invoke(operator, 'Doctor\nR\nSai nội dung\n2\n').exit_code == 0
    def run(root, deps):
        assert read_yaml(project / 'project.yaml')['state'] == 'draft_ready'
        assert read_yaml(project / 'project.yaml')['active_revision'] == '002'
        assert 'Sai nội dung' in reject_note(project)
        assert not (project / 'revisions/002/reviews/medical-approval.yaml').exists()
        assert (project / 'revisions/002/explainer/explainer.yaml').read_bytes() == (revision / 'explainer/explainer.yaml').read_bytes()
        # The fake drafting agent rebinds copied assets to the new source revision.
        for filename, key in [('asset-manifest.yaml', 'assets'), ('license-ledger.yaml', 'entries')]:
            asset_path = project / 'revisions/002/assets' / filename
            data = read_yaml(asset_path)
            for entry in data[key]:
                entry['revision'] = '002'
            write_yaml_atomic(asset_path, data)
        submit_medical_review(project)
        return RunReport(at_gate=[project.name])
    monkeypatch.setattr(factory, 'run_queue', run)
    factory.run_factory(operator[0], object(), once=True, notify=lambda *a: None)
    result = invoke(operator, 'A\n\n')
    assert result.exit_code == 0, result.output
    assert read_yaml(project / 'project.yaml')['state'] == 'medically_approved'
    assert (revision / 'reviews/medical-approval.yaml').read_bytes() == old_approval
    assert (project / 'revisions/002/reviews/medical-approval.yaml').is_file()


def test_semantic_resume_failure_is_retried_before_queue_runs(operator, monkeypatch):
    from tests.workflows.test_package import _v2_awaiting_video_review_project

    project = _v2_awaiting_video_review_project(operator[0] / 'projects')
    assert invoke(operator, 'Doctor\nR\nSai nội dung\n2\n').exit_code == 0
    real_resume = factory.resume_gate
    def fail(*args, **kwargs):
        raise OSError('temporary failure')
    monkeypatch.setattr(factory, 'resume_gate', fail)
    calls = []
    monkeypatch.setattr(factory, 'run_queue', lambda *a: calls.append(a) or RunReport())
    factory.run_factory(operator[0], object(), once=True, notify=lambda *a: None)
    assert calls == []
    pending = operator[0] / 'topics/logs' / project.name / 'pending-semantic-revision.yaml'
    assert pending.exists()
    monkeypatch.setattr(factory, 'resume_gate', real_resume)
    factory.run_factory(operator[0], object(), once=True, notify=lambda *a: None)
    assert len(calls) == 1
    assert not pending.exists()
    assert read_yaml(project / 'project.yaml')['state'] == 'draft_ready'
    assert read_yaml(project / 'project.yaml')['active_revision'] == '002'
    assert not (project / 'revisions/003').exists()


def test_semantic_revision_recovers_interrupted_manifest_switch(operator, monkeypatch):
    from healthvideo.storage import revisions
    from tests.workflows.test_package import _v2_awaiting_video_review_project

    project = _v2_awaiting_video_review_project(operator[0] / 'projects')
    assert invoke(operator, 'Doctor\nR\nSai nội dung\n2\n').exit_code == 0
    original = revisions.write_yaml_atomic
    def fail(path, data):
        if path == project / 'project.yaml':
            raise OSError('interrupted manifest switch')
        original(path, data)
    monkeypatch.setattr(revisions, 'write_yaml_atomic', fail)
    monkeypatch.setattr(factory, 'run_queue', lambda *a: RunReport())
    factory.run_factory(operator[0], object(), once=True, notify=lambda *a: None)
    assert read_yaml(project / 'project.yaml')['active_revision'] == '001'
    assert (project / 'revisions/002/workflow.yaml').is_file()
    monkeypatch.setattr(revisions, 'write_yaml_atomic', original)
    factory.run_factory(operator[0], object(), once=True, notify=lambda *a: None)
    assert read_yaml(project / 'project.yaml')['active_revision'] == '002'
    assert read_yaml(project / 'project.yaml')['state'] == 'draft_ready'


def test_duyet_skip(operator):
    before = (operator[1] / 'project.yaml').read_bytes()
    assert invoke(operator, 'Doctor\nB\n').exit_code == 0
    assert (operator[1] / 'project.yaml').read_bytes() == before


def test_duyet_saves_reviewer_once(operator):
    assert invoke(operator, 'Doctor\nB\n').exit_code == 0
    result = invoke(operator, 'B\n')
    assert result.exit_code == 0, result.output
    assert read_yaml(operator[2]) == {'reviewer': 'Doctor'}
    assert 'Tên bác sĩ' not in result.output


@pytest.mark.parametrize('action', ['A\n\n', 'R\nSửa\n\n'])
def test_duyet_wrong_pin_never_mutates(operator, monkeypatch, action):
    monkeypatch.setattr(cli.getpass, 'getpass', lambda _: 'wrong')
    before = (operator[1] / 'project.yaml').read_bytes()
    assert invoke(operator, 'Doctor\n' + action).exit_code != 0
    assert (operator[1] / 'project.yaml').read_bytes() == before


@pytest.mark.parametrize('tty,pin', [(False, '918273'), (True, 'wrong')])
def test_legacy_reject_requires_pin(operator, monkeypatch, tty, pin):
    monkeypatch.setattr(_NamedTextIOWrapper, 'isatty', lambda _: tty)
    monkeypatch.setattr(cli.getpass, 'getpass', lambda _: pin)
    before = (operator[1] / 'project.yaml').read_bytes()
    result = CliRunner().invoke(cli.app, ['review', 'reject', str(operator[1]),
        '--gate', 'medical', '--reviewer', 'Doctor', '--reason', 'Fix',
        '--resume-to', 'draft_ready', '--yes'])
    assert result.exit_code != 0
    assert (operator[1] / 'project.yaml').read_bytes() == before


def test_xuong_once_packages_video_approved(tmp_path, monkeypatch):
    from tests.workflows.test_package import _v2_video_approved_project

    project = _v2_video_approved_project(tmp_path / 'projects')
    monkeypatch.setattr(factory, 'run_queue', lambda *a: RunReport())
    factory.run_factory(tmp_path, object(), once=True, notify=lambda *a: None)
    assert read_yaml(project / 'project.yaml')['state'] == 'packaged'
    assert (project / 'revisions/001/publish/manifest.json').is_file()
    assert factory.running_pid(tmp_path) is None


def test_xuong_lock_prevents_second_instance(tmp_path):
    with factory.FactoryLock(tmp_path):
        assert factory.running_pid(tmp_path) == os.getpid()
        with pytest.raises(factory.FactoryAlreadyRunning), factory.FactoryLock(tmp_path):
            pass


def test_xuong_stale_lock_cleared(tmp_path):
    path = tmp_path / 'topics/.xuong.lock'
    path.parent.mkdir()
    path.write_text(json.dumps({'pid': 99999999, 'started_at': datetime.now(UTC).isoformat()}))
    with factory.FactoryLock(tmp_path):
        assert factory.running_pid(tmp_path) == os.getpid()


def test_xuong_notifies_only_on_change(tmp_path, monkeypatch):
    create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    reports = iter([RunReport(), RunReport(), KeyboardInterrupt()])
    def run(*a):
        report = next(reports)
        if isinstance(report, BaseException):
            raise report
        return report
    monkeypatch.setattr(factory, 'run_queue', run)
    notifications = []
    factory.run_factory(tmp_path, object(), sleep=lambda _: None,
                        notify=lambda *a: notifications.append(a))
    assert len(notifications) == 1


def test_xuong_waits_on_exhausted(tmp_path, monkeypatch):
    monkeypatch.setattr(factory, 'run_queue', lambda *a: RunReport(exhausted=True))
    waits = []
    def sleep(seconds):
        waits.append(seconds)
        raise KeyboardInterrupt
    factory.run_factory(tmp_path, object(), sleep=sleep, notify=lambda *a: None)
    assert waits == [1800]


def test_xuong_handles_exhausted_exception(tmp_path, monkeypatch):
    from healthvideo.agents import AllAgentsExhausted

    def run(*a):
        raise AllAgentsExhausted('quota')
    monkeypatch.setattr(factory, 'run_queue', run)
    waits = []
    def sleep(seconds):
        waits.append(seconds)
        raise KeyboardInterrupt
    factory.run_factory(tmp_path, object(), sleep=sleep)
    assert waits == [1800]


def test_status_includes_worker_and_waiting_count(operator):
    result = CliRunner().invoke(cli.app, ['status', '--root', str(operator[0])])
    assert result.exit_code == 0, result.output
    assert 'PID 123' in result.output
    assert 'Đang chờ bác sĩ: 1' in result.output


def test_duyet_starts_factory_on_yes(operator, monkeypatch):
    monkeypatch.setattr(factory, 'running_pid', lambda _: None)
    calls = []
    monkeypatch.setattr(factory, 'start_background', lambda root: calls.append(root) or 456)
    result = invoke(operator, 'Doctor\nB\n\n')
    assert result.exit_code == 0, result.output
    assert calls == [operator[0]]
    assert '456' in result.output


def test_xuong_background_start_and_stop(tmp_path):
    import time

    pid = factory.start_background(tmp_path, interval=1)
    try:
        assert factory.running_pid(tmp_path) == pid
        assert factory.start_background(tmp_path) == pid
    finally:
        factory.stop_background(tmp_path)
    for _ in range(100):
        if factory.running_pid(tmp_path) is None:
            break
        time.sleep(0.05)
    assert factory.running_pid(tmp_path) is None


def test_stop_ignores_recycled_pid(tmp_path):
    path = factory.lock_path(tmp_path)
    path.parent.mkdir()
    path.write_text(json.dumps({'pid': os.getpid(), 'process_token': 'wrong-start-time'}))
    assert factory.stop_background(tmp_path) is None


def test_queue_projects_precede_other_projects(tmp_path):
    from healthvideo.storage.queue import load_queue

    project = create_v2_project_fixture(tmp_path / 'projects')
    queue = tmp_path / 'topics/queue.yaml'
    write_yaml_atomic(queue, {'version': 1, 'entries': [{'slug': project.name, 'title': 'Test',
                                         'question': 'Test?', 'added': '2026-10-23'}]})
    assert load_queue(tmp_path)[0].slug == project.name
    assert [p for p, _ in factory.projects(tmp_path)] == [project]


def test_pin_never_in_argv_env_or_files(operator, monkeypatch):
    import subprocess

    from healthvideo.agents import AgentCli
    from healthvideo.agents import invoke as agent_invoke
    calls = []
    monkeypatch.setenv('HEALTHVIDEO_PIN', 'secret-env-pin')
    def run(argv, **kwargs):
        calls.append((argv, kwargs.get('env', {})))
        return subprocess.CompletedProcess(argv, 0, '', '')
    assert invoke(operator, 'Doctor\nA\n\n').exit_code == 0
    agent_invoke(AgentCli('test', ('test',), True), 'prompt', cwd=operator[0],
                 log_dir=operator[0] / 'logs', runner=run)
    factory.notify_windows('Tiêu đề', 'medical', runner=run, platform='win32')
    assert len(calls) == 2
    for argv, env in calls:
        assert '918273' not in str(argv) + str(env)
        assert not any('pin' in key.lower() for key in env)
    for path in operator[0].rglob('*'):
        if path.is_file():
            assert b'918273' not in path.read_bytes()


def test_projects_skips_invalid_manifest(tmp_path, capsys):
    from healthvideo.workflows.factory import projects

    bad = tmp_path / "projects" / "cu" / "project.yaml"
    bad.parent.mkdir(parents=True)
    bad.write_text("schema_version: '2.0'\nslug: cu\ncontent_profile: legacy\n", encoding="utf-8")
    assert list(projects(tmp_path)) == []
    assert "Bỏ qua cu" in capsys.readouterr().err


def test_xuong_holds_validation_failure_without_duplicate_notifications(tmp_path):
    from healthvideo.domain.project_v2 import WorkflowState
    from healthvideo.workflows.runner import RunDeps

    project = create_v2_project_fixture(
        tmp_path / "projects", state="awaiting_medical_review"
    )
    manifest = read_yaml(project / "project.yaml")
    manifest["state"] = WorkflowState.MEDICALLY_APPROVED.value
    write_yaml_atomic(project / "project.yaml", manifest)
    write_yaml_atomic(
        tmp_path / "topics/queue.yaml",
        {
            "version": 1,
            "entries": [
                {
                    "slug": project.name,
                    "title": "Gút cấp",
                    "question": "Vì sao tinh thể urat gây viêm khớp?",
                    "added": "2026-10-25",
                }
            ],
        },
    )
    produce_calls = []
    notifications = []
    cycles = {"count": 0}

    def fake_produce(_project_dir):
        produce_calls.append("produce")
        raise ValueError("visual budget failed: chart_crop")

    deps = RunDeps(
        create_project=lambda *_: project,
        read_state=lambda _: WorkflowState.MEDICALLY_APPROVED,
        reject_note=lambda _: None,
        python_steps={"produce": fake_produce},
        changed_code_paths=lambda _: [],
        visual_review_pending=lambda _: False,
    )

    def sleep(_seconds):
        cycles["count"] += 1
        if cycles["count"] >= 3:
            raise KeyboardInterrupt

    factory.run_factory(
        tmp_path,
        deps,
        sleep=sleep,
        notify=lambda *a: notifications.append(a),
        echo=lambda *_: None,
    )
    assert produce_calls == ["produce"]
    assert len(notifications) == 1
