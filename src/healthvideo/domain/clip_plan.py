"""Vertical clip plan (script/clip-plan.yaml): clips cut from the approved long-form script.

A clip only points at existing storyboard scenes, so it cannot carry new wording;
``extra="forbid"`` keeps free text, and therefore new claims, out of the plan.
"""

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.storyboard import Scene, Storyboard

FPS = 30
CLIP_MIN_FRAMES = 30 * FPS
CLIP_MAX_FRAMES = 90 * FPS


class ClipSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^CL\d{2}$")
    title: str = Field(min_length=1, max_length=100)  # internal label, never rendered
    first_scene_id: str
    last_scene_id: str
    hook_scene_id: str | None = None
    outro_scene_id: str | None = None


class ClipPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    clips: tuple[ClipSpec, ...] = Field(min_length=3, max_length=6)

    @model_validator(mode="after")
    def _unique_ids(self) -> "ClipPlan":
        ids = [clip.id for clip in self.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("clip IDs must be unique")
        return self


def resolve_clip_scenes(clip: ClipSpec, storyboard: Storyboard) -> tuple[Scene, ...]:
    """Return hook + contiguous range + outro scenes, in that order."""
    index = {scene.id: position for position, scene in enumerate(storyboard.scenes)}
    wanted = (clip.first_scene_id, clip.last_scene_id, clip.hook_scene_id, clip.outro_scene_id)
    for scene_id in wanted:
        if scene_id is not None and scene_id not in index:
            raise ValueError(f"{clip.id}: unknown scene {scene_id}")
    first, last = index[clip.first_scene_id], index[clip.last_scene_id]
    if first > last:
        raise ValueError(f"{clip.id}: first scene must not come after last scene")
    for scene_id in (clip.hook_scene_id, clip.outro_scene_id):
        if scene_id is not None and first <= index[scene_id] <= last:
            raise ValueError(f"{clip.id}: scene {scene_id} is already inside the clip range")
    hook = [storyboard.scenes[index[clip.hook_scene_id]]] if clip.hook_scene_id else []
    outro = [storyboard.scenes[index[clip.outro_scene_id]]] if clip.outro_scene_id else []
    return tuple(hook + list(storyboard.scenes[first : last + 1]) + outro)


def validate_clip_plan(
    plan: ClipPlan, storyboard: Storyboard, claims: Mapping[str, EvidenceClaim]
) -> dict[str, tuple[Scene, ...]]:
    """Block clips that run too short/long, cite unknown claims, or drop a caveat."""
    if storyboard.format_profile != "youtube_long":
        raise ValueError("clip plan requires a youtube_long storyboard")
    resolved: dict[str, tuple[Scene, ...]] = {}
    for clip in plan.clips:
        scenes = resolve_clip_scenes(clip, storyboard)
        frames = sum(scene.duration_frames for scene in scenes)
        if not CLIP_MIN_FRAMES <= frames <= CLIP_MAX_FRAMES:
            raise ValueError(
                f"{clip.id}: duration {frames} frames must be between "
                f"{CLIP_MIN_FRAMES} and {CLIP_MAX_FRAMES}"
            )
        present = {scene.claim_id for scene in scenes if scene.claim_id}
        for claim_id in sorted(present):
            claim = claims.get(claim_id)
            if claim is None:
                raise ValueError(f"{clip.id}: claim {claim_id} is not in the ledger")
            for caveat_id in claim.caveat_claim_ids:
                if caveat_id not in claims:
                    raise ValueError(
                        f"{clip.id}: caveat {caveat_id} of claim {claim_id} is not in the ledger"
                    )
                if caveat_id not in present:
                    raise ValueError(
                        f"{clip.id}: claim {claim_id} requires caveat {caveat_id} in the clip"
                    )
        resolved[clip.id] = scenes
    return resolved
