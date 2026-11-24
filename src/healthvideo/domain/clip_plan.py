"""Vertical clip plan (script/clip-plan.yaml): clips cut from the approved long-form script.

A clip only points at existing storyboard scenes, so it cannot carry new wording;
``extra="forbid"`` keeps free text, and therefore new claims, out of the plan.
"""

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.storyboard import Scene, Storyboard

FPS = 30
CLIP_MIN_FRAMES = 60 * FPS
CLIP_MAX_FRAMES = 180 * FPS
CLIP_CTA_FRAMES = 3 * FPS
STYLE_A_MASCOT_MAX_WIDTH_PERCENT = 28.0
STYLE_A_SUBTITLE_POSITION = "bottom_center"
STYLE_A_HOOK_MAX_SECONDS = 2.0


class ClipSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^CL\d{2}$")
    title: str = Field(min_length=1, max_length=100)  # internal label, never rendered
    first_scene_id: str
    last_scene_id: str
    hook_scene_id: str | None = None
    outro_scene_id: str | None = None
    mascot_max_width_percent: float | None = Field(
        default=None,
        gt=0,
        le=STYLE_A_MASCOT_MAX_WIDTH_PERCENT,
        allow_inf_nan=False,
        exclude_if=lambda v: v is None,
    )
    subtitle_position: Literal["bottom_center"] | None = Field(
        default=None,
        exclude_if=lambda v: v is None,
    )
    hook_window_seconds: float | None = Field(
        default=None,
        gt=0,
        le=STYLE_A_HOOK_MAX_SECONDS,
        allow_inf_nan=False,
        exclude_if=lambda v: v is None,
    )


class ClipPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    clips: tuple[ClipSpec, ...] = Field(min_length=1, max_length=6)

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


def validate_style_a_vertical_clip(clip: ClipSpec) -> None:
    """Require Style A §6 (Trạm 15) 9:16 layout metadata on a vertical clip."""
    if clip.mascot_max_width_percent is None or clip.mascot_max_width_percent > STYLE_A_MASCOT_MAX_WIDTH_PERCENT:
        raise ValueError(
            f"{clip.id}: chuẩn A 9:16 yêu cầu mascot_max_width_percent <= {STYLE_A_MASCOT_MAX_WIDTH_PERCENT:g}%"
        )
    if clip.subtitle_position != STYLE_A_SUBTITLE_POSITION:
        raise ValueError(
            f"{clip.id}: chuẩn A 9:16 yêu cầu subtitle_position={STYLE_A_SUBTITLE_POSITION!r}"
        )
    if clip.hook_window_seconds is None or clip.hook_window_seconds > STYLE_A_HOOK_MAX_SECONDS:
        raise ValueError(
            f"{clip.id}: chuẩn A 9:16 yêu cầu hook_window_seconds <= {STYLE_A_HOOK_MAX_SECONDS:g}s"
        )


def vertical_clip_storyboard(storyboard: Storyboard, scenes: Sequence[Scene]) -> Storyboard:
    """Build and validate the same retimed vertical storyboard used for rendering."""
    retimed: list[Scene] = []
    start = 0
    for scene in scenes:
        retimed.append(scene.model_copy(update={"start_frame": start, "chapter_id": None}))
        start += scene.duration_frames
    return Storyboard(
        title=storyboard.title,
        quality_profile=storyboard.quality_profile,
        r5_contract=storyboard.r5_contract,
        scenes=tuple(retimed),
        visual_budget_profile=storyboard.visual_budget_profile,
        format_profile="vertical_clip",
    )


def validate_clip_plan(
    plan: ClipPlan, storyboard: Storyboard, claims: Mapping[str, EvidenceClaim],
    *, min_frames: int = CLIP_MIN_FRAMES, max_frames: int = CLIP_MAX_FRAMES,
    require_style_a: bool = False,
) -> dict[str, tuple[Scene, ...]]:
    """Block clips that run too short/long, cite unknown claims, or drop a caveat."""
    if storyboard.format_profile != "youtube_long":
        raise ValueError("clip plan requires a youtube_long storyboard")
    resolved: dict[str, tuple[Scene, ...]] = {}
    for clip in plan.clips:
        if require_style_a:
            validate_style_a_vertical_clip(clip)
        scenes = resolve_clip_scenes(clip, storyboard)
        try:
            vertical_clip_storyboard(storyboard, scenes)
        except ValueError as error:
            subjects = ", ".join(
                f"{scene.id}={scene.anatomy.subject if scene.anatomy else 'không có anatomy'}"
                for scene in scenes
            )
            reason = str(error)
            if "vertical_clip requires at least 2 anatomy.subject values" in reason:
                reason = (
                    "clip dọc cần chọn khoảng cảnh có ít nhất 2 anatomy.subject khác nhau "
                    "(hoặc có ít hơn 2 cảnh cơ chế)"
                )
            raise ValueError(f"{clip.id}: {reason}; chủ thể từng cảnh: {subjects}") from error
        frames = sum(scene.duration_frames for scene in scenes) + CLIP_CTA_FRAMES
        if not min_frames <= frames <= max_frames:
            raise ValueError(
                f"{clip.id}: duration {frames} frames must be between "
                f"{min_frames} and {max_frames}"
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
