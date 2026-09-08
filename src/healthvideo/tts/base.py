from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field


class TTSRequest(BaseModel):
    """Narration and optional delivery data passed to a TTS provider."""

    text: str
    language: str
    speed: float = Field(default=1.0, gt=0)
    delivery_beats: tuple[dict[str, object], ...] = ()


class WordTimestamp(BaseModel, frozen=True):
    word: str
    start_ms: int
    end_ms: int


class TTSResult(BaseModel):
    provider: str
    audio_file: Path
    duration_ms: int
    word_timestamps: tuple[WordTimestamp, ...] = ()


class TTSProvider(Protocol):
    """A replaceable provider that writes audio to the supplied output path."""

    def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
        """Synthesize ``request`` into ``output`` and return its metadata."""


def word_timestamps(
    words: Sequence[str], duration_ms: int
) -> tuple[WordTimestamp, ...]:
    """Allocate deterministic, evenly distributed timestamps for word captions."""
    if not words:
        return ()
    return tuple(
        WordTimestamp(
            word=word,
            start_ms=round(index * duration_ms / len(words)),
            end_ms=round((index + 1) * duration_ms / len(words)),
        )
        for index, word in enumerate(words)
    )
