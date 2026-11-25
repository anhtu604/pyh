"""Long-form chapter plan (script/outline.yaml) and its check against the storyboard."""

from collections.abc import Set as AbstractSet
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.domain.long_form import long_form_storyboard
from healthvideo.domain.storyboard import Storyboard

MIN_TARGET_SECONDS = 10 * 60
MAX_TARGET_SECONDS = 25 * 60
FLEXIBLE_MIN_TARGET_SECONDS = 45
FLEXIBLE_MAX_TARGET_SECONDS = 30 * 60


class OutlineChapter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^CH\d{2}$")
    title: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    claim_ids: tuple[str, ...] = ()
    target_seconds: int = Field(gt=0)
    mood: str | None = Field(default=None, min_length=1)


class Outline(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    format_profile: Literal["youtube_long", "flexible_v1"] = "youtube_long"
    title: str = Field(min_length=1)
    mood: str | None = Field(default=None, min_length=1)
    chapters: tuple[OutlineChapter, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _check_chapters(self) -> "Outline":
        if self.format_profile == "youtube_long" and len(self.chapters) < 4:
            raise ValueError("outline requires at least 4 chapters for youtube_long")
        ids = [chapter.id for chapter in self.chapters]
        if len(ids) != len(set(ids)):
            raise ValueError("outline chapter IDs must be unique")
        total = sum(chapter.target_seconds for chapter in self.chapters)
        min_s, max_s = (
            (MIN_TARGET_SECONDS, MAX_TARGET_SECONDS)
            if self.format_profile == "youtube_long"
            else (FLEXIBLE_MIN_TARGET_SECONDS, FLEXIBLE_MAX_TARGET_SECONDS)
        )
        if not min_s <= total <= max_s:
            raise ValueError(
                f"outline target {total} s must be between "
                f"{min_s} and {max_s} s"
            )
        return self


def validate_outline(outline: Outline, storyboard: Storyboard, claim_ids: AbstractSet[str]) -> None:
    """Chapters appear in storyboard order; every scene claim is planned in its chapter."""
    storyboard = long_form_storyboard(storyboard)
    if outline.format_profile == "youtube_long" and storyboard.format_profile != "youtube_long":
        raise ValueError("outline requires a youtube_long storyboard")
    if outline.format_profile == "flexible_v1" and storyboard.format_profile not in {"youtube_long", "vertical_clip"}:
        raise ValueError("flexible outline requires a youtube_long or vertical_clip storyboard")
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
