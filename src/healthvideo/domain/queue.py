"""Domain models for the topic queue."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class QueueError(ValueError):
    """Raised when a topic queue operation violates queue constraints."""


class QueueEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str = Field(pattern=r"^[a-z0-9-]{3,80}$")
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)
    doctor_note: str | None = None
    added: date
