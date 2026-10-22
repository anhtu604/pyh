"""Domain models and errors for free-source topic discovery (§5.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

SignalSource = Literal["youtube", "trends", "reddit", "pubmed"]


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: SignalSource
    url: str
    text: str
    metric: float | None = None
    fetched: datetime


class SourceFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: SignalSource
    reason: str


class TopicCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    question: str
    misconceptions: list[Signal]
    heat: float | None = None
    layers: list[str]
    pubmed_count: int | None = None


class MissingApiKey(RuntimeError):
    """Raised when a discovery source requires an API key that was not provided."""


class SourceError(RuntimeError):
    """Raised when a discovery source fails due to network, HTTP, or parse errors."""

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(f"{source}: {reason}")
        self.source = source
        self.reason = reason
