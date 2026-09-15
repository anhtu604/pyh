from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from secrets import token_hex

from healthvideo.domain.lease import LeaseOwner, ProjectLease
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.immutable import write_yaml_once

LEASE_PATH = Path(".healthvideo/write-lease.yaml")


class LeaseBusyError(RuntimeError):
    pass


class LeaseOwnershipError(RuntimeError):
    pass


class LeaseRecoveryError(RuntimeError):
    pass


def _lease_path(project_dir: Path) -> Path:
    return project_dir / LEASE_PATH


def _payload(lease: ProjectLease) -> dict[str, object]:
    return lease.model_dump(mode="json")


def read_write_lease(project_dir: Path) -> ProjectLease | None:
    path = _lease_path(project_dir)
    if not path.exists():
        return None
    return ProjectLease.model_validate(read_yaml(path))


@dataclass(frozen=True)
class WriteLeaseHandle:
    project_dir: Path
    lease_id: str

    def with_lease_id(self, lease_id: str) -> WriteLeaseHandle:
        return replace(self, lease_id=lease_id)

    def _owned(self) -> ProjectLease:
        lease = read_write_lease(self.project_dir)
        if lease is None or lease.lease_id != self.lease_id:
            raise LeaseOwnershipError("write lease is no longer owned by this handle")
        return lease

    def heartbeat(self, *, now: datetime) -> None:
        lease = self._owned()
        if now < lease.heartbeat_at:
            raise ValueError("heartbeat timestamp must not move backwards")
        updated = lease.model_copy(update={"heartbeat_at": now})
        ProjectLease.model_validate(updated.model_dump())
        write_yaml_atomic(_lease_path(self.project_dir), _payload(updated))

    def release(self) -> None:
        self._owned()
        _lease_path(self.project_dir).unlink()


def acquire_write_lease(
    project_dir: Path,
    *,
    operation: str,
    active_revision: str | None,
    owner: LeaseOwner,
    now: datetime,
    ttl_seconds: int,
) -> WriteLeaseHandle:
    lease = ProjectLease.create(
        lease_id=token_hex(16),
        owner=owner,
        operation=operation,
        active_revision=active_revision,
        now=now,
        ttl_seconds=ttl_seconds,
    )
    try:
        write_yaml_once(_lease_path(project_dir), _payload(lease))
    except FileExistsError as error:
        raise LeaseBusyError("project already has an active write lease") from error
    return WriteLeaseHandle(project_dir=project_dir, lease_id=lease.lease_id)


def recover_stale_lease(
    project_dir: Path,
    *,
    requester: LeaseOwner,
    process_probe: Callable[[int], str | None],
    now: datetime,
    allow_foreign_host: bool,
) -> Path:
    lease = read_write_lease(project_dir)
    if lease is None:
        raise LeaseRecoveryError("project has no write lease to recover")
    if now <= lease.expires_at:
        raise LeaseRecoveryError("write lease has not expired")
    if lease.host_id == requester.host_id:
        observed_start = process_probe(lease.pid)
        if observed_start == lease.process_start_fingerprint:
            raise LeaseRecoveryError("same-host lease owner process is still active")
    elif not allow_foreign_host:
        raise LeaseRecoveryError("foreign-host lease requires explicit recovery")

    archive_dir = project_dir / ".healthvideo" / "stale-leases"
    archived = archive_dir / f"{lease.lease_id}.yaml"
    write_yaml_once(archived, _payload(lease))
    current = read_write_lease(project_dir)
    if current != lease:
        raise LeaseRecoveryError("write lease changed during recovery")
    _lease_path(project_dir).unlink()
    return archived
