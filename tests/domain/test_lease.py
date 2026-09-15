from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from healthvideo.domain.lease import LeaseOwner, ProjectLease

NOW = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)


def owner() -> LeaseOwner:
    return LeaseOwner(host_id="host-a", pid=123, process_start_fingerprint="start-1")


def test_project_lease_is_closed_frozen_and_timezone_aware() -> None:
    lease = ProjectLease.create(
        lease_id="lease-1",
        owner=owner(),
        operation="produce",
        active_revision="001",
        now=NOW,
        ttl_seconds=60,
    )

    assert lease.host_id == "host-a"
    assert lease.expires_at == datetime(2026, 9, 15, 8, 1, tzinfo=UTC)
    with pytest.raises(ValidationError):
        lease.operation = "package"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ProjectLease.model_validate({**lease.model_dump(), "unexpected": True})


@pytest.mark.parametrize("field", ["host_id", "process_start_fingerprint"])
def test_lease_owner_rejects_blank_identity(field: str) -> None:
    payload = owner().model_dump()
    payload[field] = " "
    with pytest.raises(ValidationError):
        LeaseOwner.model_validate(payload)


@pytest.mark.parametrize("ttl", [0, 4, 3601])
def test_project_lease_rejects_ttl_outside_contract(ttl: int) -> None:
    with pytest.raises(ValidationError):
        ProjectLease.create(
            lease_id="lease-1",
            owner=owner(),
            operation="produce",
            active_revision=None,
            now=NOW,
            ttl_seconds=ttl,
        )


def test_project_lease_rejects_naive_or_reversed_timestamps() -> None:
    lease = ProjectLease.create(
        lease_id="lease-1",
        owner=owner(),
        operation="produce",
        active_revision=None,
        now=NOW,
        ttl_seconds=60,
    ).model_dump()
    for acquired, heartbeat in (
        (NOW.replace(tzinfo=None), NOW),
        (NOW, NOW.replace(tzinfo=None)),
        (NOW, datetime(2026, 9, 15, 7, 59, tzinfo=UTC)),
    ):
        with pytest.raises(ValidationError):
            ProjectLease.model_validate(
                {**lease, "acquired_at": acquired, "heartbeat_at": heartbeat}
            )
