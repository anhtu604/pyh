"""Pre-TTS Vietnamese medical pronunciation & pacing prep (`voice_prep`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.domain.pronunciation import PronunciationEntry, PronunciationLexicon
from healthvideo.domain.script import Script
from healthvideo.storage.files import canonical_json_hash, read_yaml, write_yaml_atomic
from healthvideo.storage.revision_lock import revision_lock
from healthvideo.workflows.draft import _project

VOICE_PREP_ARTIFACT = "script/voice-prep.yaml"


class VoicePrepSheet(BaseModel):
    """Per-project pronunciation extensions and delivery pacing notes before TTS."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    script_hash: str = ""
    pronunciations: tuple[PronunciationEntry, ...] = ()
    pacing_notes: tuple[str | dict[str, Any], ...] = ()
    notes: str = Field(default="")

    @model_validator(mode="after")
    def _unique_written(self) -> VoicePrepSheet:
        seen: set[str] = set()
        for entry in self.pronunciations:
            key = entry.written.strip().casefold()
            if key in seen:
                raise ValueError(f"duplicate voice_prep pronunciation term: {entry.written}")
            seen.add(key)
        return self


def _current_script_hash(revision: Path) -> str:
    script_path = revision / "script/script.yaml"
    if not script_path.is_file():
        raise ValueError("voice_prep requires script/script.yaml")
    data = read_yaml(script_path)
    Script.model_validate(data)
    return canonical_json_hash(data)


def save_voice_prep(project_dir: Path, file_path: Path) -> Path:
    """Validate and save ``script/voice-prep.yaml`` stamped to current script_hash."""
    project = _project(project_dir)
    revision = project_dir / "revisions" / project.active_revision
    with revision_lock(revision):
        script_hash = _current_script_hash(revision)
        sheet = VoicePrepSheet.model_validate(read_yaml(file_path)).model_copy(
            update={"script_hash": script_hash}
        )
        target = revision / VOICE_PREP_ARTIFACT
        target.parent.mkdir(parents=True, exist_ok=True)
        write_yaml_atomic(target, sheet.model_dump(mode="json"))
        return target


def voice_prep_ready(project_dir: Path) -> bool:
    """Return True when active revision has a valid voice-prep sheet for the current script."""
    if not (project_dir / "project.yaml").is_file():
        return False
    try:
        project = _project(project_dir)
        revision = project_dir / "revisions" / project.active_revision
        script_hash = _current_script_hash(revision)
        target = revision / VOICE_PREP_ARTIFACT
        if not target.is_file():
            return False
        sheet = VoicePrepSheet.model_validate(read_yaml(target))
    except (OSError, TypeError, ValueError):
        return False
    return sheet.script_hash == script_hash


def load_voice_prep_lexicon(
    revision: Path, base_lexicon: PronunciationLexicon
) -> PronunciationLexicon:
    """Merge project ``script/voice-prep.yaml`` entries atop the shared base lexicon."""
    target = revision / VOICE_PREP_ARTIFACT
    if not target.is_file():
        return base_lexicon
    sheet = VoicePrepSheet.model_validate(read_yaml(target))
    if not sheet.pronunciations:
        return base_lexicon
    merged: list[PronunciationEntry] = list(base_lexicon.entries)
    index_by_key = {entry.written.strip().casefold(): idx for idx, entry in enumerate(merged)}
    for entry in sheet.pronunciations:
        key = entry.written.strip().casefold()
        if key in index_by_key:
            merged[index_by_key[key]] = entry
        else:
            index_by_key[key] = len(merged)
            merged.append(entry)
    return PronunciationLexicon(
        schema_version=base_lexicon.schema_version,
        language=base_lexicon.language,
        version=f"{base_lexicon.version}+voiceprep",
        entries=tuple(merged),
    )
