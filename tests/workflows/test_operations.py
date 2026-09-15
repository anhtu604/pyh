from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.lease import LeaseOwner
from healthvideo.storage.lease import LeaseBusyError, read_write_lease
from healthvideo.workflows import operations

NOW = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
OWNER = LeaseOwner(host_id="host-a", pid=11, process_start_fingerprint="start-a")


def test_mutation_lease_releases_after_success_and_failure(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(operations, "current_lease_owner", lambda: OWNER)
    monkeypatch.setattr(operations, "current_time", lambda: NOW)

    with operations.mutation_lease(project, "produce"):
        assert read_write_lease(project).operation == "produce"  # type: ignore[union-attr]
    assert read_write_lease(project) is None

    with (
        pytest.raises(RuntimeError, match="boom"),
        operations.mutation_lease(project, "package"),
    ):
        raise RuntimeError("boom")
    assert read_write_lease(project) is None


def test_mutation_lease_reports_busy_without_mutating_project(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(operations, "current_lease_owner", lambda: OWNER)
    monkeypatch.setattr(operations, "current_time", lambda: NOW)

    with operations.mutation_lease(project, "holder"):
        with (
            pytest.raises(LeaseBusyError),
            operations.mutation_lease(project, "contender"),
        ):
            raise AssertionError("unreachable")

        assert read_write_lease(project).operation == "holder"  # type: ignore[union-attr]


def test_current_owner_fallback_fingerprint_is_stable(monkeypatch) -> None:
    monkeypatch.setattr(operations, "process_start_fingerprint", lambda pid: None)

    first = operations.current_lease_owner()
    second = operations.current_lease_owner()

    assert first == second
