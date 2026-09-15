from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LeaseOwner(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host_id: str = Field(pattern=r"\S")
    pid: int = Field(ge=1)
    process_start_fingerprint: str = Field(pattern=r"\S")


class ProjectLease(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    lease_id: str = Field(pattern=r"\S")
    host_id: str = Field(pattern=r"\S")
    pid: int = Field(ge=1)
    process_start_fingerprint: str = Field(pattern=r"\S")
    operation: str = Field(pattern=r"\S")
    active_revision: str | None = Field(default=None, pattern=r"^[0-9]{3}$")
    acquired_at: datetime
    heartbeat_at: datetime
    ttl_seconds: int = Field(ge=5, le=3600)

    @model_validator(mode="after")
    def validate_timestamps(self) -> ProjectLease:
        if self.acquired_at.tzinfo is None or self.heartbeat_at.tzinfo is None:
            raise ValueError("lease timestamps must include a timezone")
        if self.heartbeat_at < self.acquired_at:
            raise ValueError("heartbeat_at must not precede acquired_at")
        return self

    @classmethod
    def create(
        cls,
        *,
        lease_id: str,
        owner: LeaseOwner,
        operation: str,
        active_revision: str | None,
        now: datetime,
        ttl_seconds: int,
    ) -> ProjectLease:
        return cls(
            lease_id=lease_id,
            host_id=owner.host_id,
            pid=owner.pid,
            process_start_fingerprint=owner.process_start_fingerprint,
            operation=operation,
            active_revision=active_revision,
            acquired_at=now,
            heartbeat_at=now,
            ttl_seconds=ttl_seconds,
        )

    @property
    def expires_at(self) -> datetime:
        return self.heartbeat_at + timedelta(seconds=self.ttl_seconds)
