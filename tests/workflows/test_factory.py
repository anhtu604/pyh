"""Regression tests for factory lock cleanup and background stop edge cases."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from healthvideo.workflows import factory


def test_factory_lock_ignores_orphan_dead_pid_and_closes_stream_on_unlock_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = factory.lock_path(tmp_path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps({"pid": 999999, "started_at": "2026-11-19T08:27:33+00:00", "process_token": "dead"}),
        encoding="utf-8",
    )
    assert factory.running_pid(tmp_path) is None

    guard = factory.FactoryLock(tmp_path)
    guard.__enter__()
    assert factory.running_pid(tmp_path) == os.getpid()
    if os.name == "nt":
        import msvcrt

        real_locking = msvcrt.locking

        def fail_unlock(fd, mode, nbytes):
            if mode == msvcrt.LK_UNLCK:
                raise OSError("unlock failed")
            return real_locking(fd, mode, nbytes)

        monkeypatch.setattr(msvcrt, "locking", fail_unlock)
        with pytest.raises(OSError, match="unlock failed"):
            guard.__exit__(None, None, None)
        assert guard.stream.closed
        monkeypatch.undo()
    else:
        guard.__exit__(None, None, None)

    with factory.FactoryLock(tmp_path):
        assert factory.running_pid(tmp_path) == os.getpid()


def test_stop_background_handles_race_when_process_already_exited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pids = iter([13064, None])
    monkeypatch.setattr(factory, "running_pid", lambda root: next(pids, None))

    def fail_kill(pid, sig):
        raise ProcessLookupError(3, "No such process")

    monkeypatch.setattr(factory.os, "kill", fail_kill)
    assert factory.stop_background(tmp_path) is None

    monkeypatch.setattr(factory, "running_pid", lambda root: 13064)
    monkeypatch.setattr(factory.os, "kill", lambda pid, sig: (_ for _ in ()).throw(PermissionError("denied")))
    with pytest.raises(PermissionError, match="denied"):
        factory.stop_background(tmp_path)


@pytest.mark.parametrize('hook_fails', [False, True])
def test_packaging_hook_runs_only_on_transition_and_failure_is_isolated(tmp_path, monkeypatch, hook_fails):
    from healthvideo.storage.files import read_yaml
    from healthvideo.workflows import auto_publish
    from healthvideo.workflows.runner import RunReport
    from tests.workflows.test_package import _v2_video_approved_project

    project = _v2_video_approved_project(tmp_path / 'projects')
    monkeypatch.setattr(factory, 'run_queue', lambda *a, **k: RunReport())
    calls = []
    def hook(root, slug):
        assert read_yaml(project / 'project.yaml')['state'] == 'packaged'
        calls.append((root, slug))
        if hook_fails:
            raise RuntimeError('secret-do-not-log')
    monkeypatch.setattr(auto_publish, 'on_packaged', hook)
    factory.run_factory(tmp_path, object(), once=True, notify=lambda *a: None, echo=lambda *a: None)
    factory.run_factory(tmp_path, object(), once=True, notify=lambda *a: None, echo=lambda *a: None)
    assert calls == [(tmp_path, project.name)]
    assert read_yaml(project / 'project.yaml')['state'] == 'packaged'
    assert not (tmp_path / 'topics/logs' / project.name / 'blocked.txt').exists()
    assert 'secret-do-not-log' not in (tmp_path / 'topics/logs/xuong.log').read_text(encoding='utf-8')
