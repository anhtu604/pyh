"""Versioned literal pronunciation choices for Vietnamese narration."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class PronunciationEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    written: str
    spoken: str
    note: str = ""

    @field_validator("written", "spoken")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("pronunciation term must not be blank")
        return value


class PronunciationLexicon(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"]
    language: Literal["vi"]
    version: str
    entries: tuple[PronunciationEntry, ...]

    @field_validator("version")
    @classmethod
    def nonblank_version(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("pronunciation version must not be blank")
        return value

    @model_validator(mode="after")
    def unique_written(self) -> "PronunciationLexicon":
        # Casefold and trim only; do not guess Vietnamese spelling equivalence.
        terms = [entry.written.strip().casefold() for entry in self.entries]
        if len(terms) != len(set(terms)):
            raise ValueError("duplicate written pronunciation term")
        return self
