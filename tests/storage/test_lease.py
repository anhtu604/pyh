from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from healthvideo.domain.lease import LeaseOwner
from healthvideo.storage.lease import (
    LeaseBusyError,
    LeaseOwnershipError,
    LeaseRecoveryError,
    acquire_write_lease,
    read_write_lease,
    recover_stale_lease,
)

NOW = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
OWNER_A = LeaseOwner(host_id="host-a", pid=101, process_start_fingerprint="a-1")
OWNER_B = LeaseOwner(host_id="host-b", pid=202, process_start_fingerprint="b-1")


def acquire(project: Path, owner: LeaseOwner = OWNER_A, *, now: datetime = NOW):
    return acquire_write_lease(
        project,
        operation="produce",
        active_revision="001",
        owner=owner,
        now=now,
        ttl_seconds=60,
    )


def test_two_contenders_have_exactly_one_winner(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    def contend(owner: LeaseOwner) -> bool:
        try:
            acquire(project, owner)
        except LeaseBusyError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(contend, [OWNER_A, OWNER_B]))

    assert sorted(outcomes) == [False, True]
    assert read_write_lease(project) is not None


def test_heartbeat_and_release_require_current_token(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    handle = acquire(project)
    impostor = handle.with_lease_id("wrong-token")

    with pytest.raises(LeaseOwnershipError):
        impostor.heartbeat(now=NOW + timedelta(seconds=10))
    with pytest.raises(LeaseOwnershipError):
        impostor.release()

    handle.heartbeat(now=NOW + timedelta(seconds=10))
    assert read_write_lease(project).heartbeat_at == NOW + timedelta(seconds=10)  # type: ignore[union-attr]
    handle.release()
    assert read_write_lease(project) is None


def test_heartbeat_cannot_move_backwards(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    handle = acquire(project)
    handle.heartbeat(now=NOW + timedelta(seconds=20))

    with pytest.raises(ValueError, match="heartbeat"):
        handle.heartbeat(now=NOW + timedelta(seconds=10))

    assert read_write_lease(project).heartbeat_at == NOW + timedelta(seconds=20)  # type: ignore[union-attr]


def test_expired_lease_is_never_removed_by_acquire(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    original = acquire(project)

    with pytest.raises(LeaseBusyError):
        acquire(project, OWNER_B, now=NOW + timedelta(minutes=2))

    assert read_write_lease(project).lease_id == original.lease_id  # type: ignore[union-attr]


def test_same_host_recovery_refuses_when_original_process_is_alive(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    acquire(project)

    with pytest.raises(LeaseRecoveryError):
        recover_stale_lease(
            project,
            requester=OWNER_A,
            process_probe=lambda pid: "a-1",
            now=NOW + timedelta(minutes=2),
            allow_foreign_host=False,
        )


def test_same_host_pid_reuse_with_different_fingerprint_can_recover(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    handle = acquire(project)

    archived = recover_stale_lease(
        project,
        requester=OWNER_A,
        process_probe=lambda pid: "new-process-same-pid",
        now=NOW + timedelta(minutes=2),
        allow_foreign_host=False,
    )

    assert handle.lease_id in archived.read_text(encoding="utf-8")
    assert read_write_lease(project) is None


def test_same_host_dead_owner_is_preserved_before_recovery(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    handle = acquire(project)

    archived = recover_stale_lease(
        project,
        requester=OWNER_A,
        process_probe=lambda pid: None,
        now=NOW + timedelta(minutes=2),
        allow_foreign_host=False,
    )

    assert handle.lease_id in archived.read_text(encoding="utf-8")
    assert archived.parent == project / ".healthvideo" / "stale-leases"
    assert read_write_lease(project) is None
    successor = acquire(project, now=NOW + timedelta(minutes=2))
    with pytest.raises(LeaseOwnershipError):
        handle.release()
    successor.release()


def test_foreign_host_recovery_is_explicit_and_preserves_record(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    handle = acquire(project, OWNER_B)
    kwargs = {
        "project_dir": project,
        "requester": OWNER_A,
        "process_probe": lambda pid: None,
        "now": NOW + timedelta(minutes=2),
    }

    with pytest.raises(LeaseRecoveryError):
        recover_stale_lease(**kwargs, allow_foreign_host=False)
    archived = recover_stale_lease(**kwargs, allow_foreign_host=True)

    assert handle.lease_id in archived.read_text(encoding="utf-8")
    assert read_write_lease(project) is None


def test_recovery_refuses_unexpired_lease_even_with_foreign_override(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    acquire(project, OWNER_B)

    with pytest.raises(LeaseRecoveryError):
        recover_stale_lease(
            project,
            requester=OWNER_A,
            process_probe=lambda pid: None,
            now=NOW + timedelta(seconds=30),
            allow_foreign_host=True,
        )
