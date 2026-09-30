"""Long-form chapter plan (script/outline.yaml) and its check against the storyboard."""

from collections.abc import Set as AbstractSet
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.domain.storyboard import Storyboard

MIN_TARGET_SECONDS = 15 * 60
MAX_TARGET_SECONDS = 25 * 60


class OutlineChapter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^CH\d{2}$")
    title: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    claim_ids: tuple[str, ...] = ()
    target_seconds: int = Field(gt=0)


class Outline(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    title: str = Field(min_length=1)
    chapters: tuple[OutlineChapter, ...] = Field(min_length=5, max_length=8)

    @model_validator(mode="after")
    def _check_chapters(self) -> "Outline":
        ids = [chapter.id for chapter in self.chapters]
        if len(ids) != len(set(ids)):
            raise ValueError("outline chapter IDs must be unique")
        total = sum(chapter.target_seconds for chapter in self.chapters)
        if not MIN_TARGET_SECONDS <= total <= MAX_TARGET_SECONDS:
            raise ValueError(
                f"outline target {total} s must be between "
                f"{MIN_TARGET_SECONDS} and {MAX_TARGET_SECONDS} s"
            )
        return self


def validate_outline(outline: Outline, storyboard: Storyboard, claim_ids: AbstractSet[str]) -> None:
    """Chapters appear in storyboard order; every scene claim is planned in its chapter."""
    if storyboard.format_profile != "youtube_long":
        raise ValueError("outline requires a youtube_long storyboard")
    order: list[str] = []
    for scene in storyboard.scenes:
        if scene.chapter_id is not None and (not order or order[-1] != scene.chapter_id):
            order.append(scene.chapter_id)
    planned = [chapter.id for chapter in outline.chapters]
    if order != planned:
        raise ValueError(f"outline chapters {planned} do not match storyboard {order}")
    for chapter in outline.chapters:
        for claim_id in chapter.claim_ids:
            if claim_id not in claim_ids:
                raise ValueError(f"{chapter.id}: unknown claim {claim_id}")
    by_id = {chapter.id: chapter for chapter in outline.chapters}
    for scene in storyboard.scenes:
        if scene.claim_id and scene.claim_id not in by_id[scene.chapter_id].claim_ids:
            raise ValueError(
                f"Scene {scene.id}: claim {scene.claim_id} is not planned "
                f"in chapter {scene.chapter_id}"
            )
