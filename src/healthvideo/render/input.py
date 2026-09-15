from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.domain.visual_budget import VisualBudgetProfile

FRAMES_PER_SECOND = 30
MIN_DURATION_FRAMES = 45 * FRAMES_PER_SECOND
MAX_DURATION_FRAMES = 90 * FRAMES_PER_SECOND


class RenderInput(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "x-invariants": {
                "m6_5_chart_ref": (
                    "m6_5_v1 chart scenes contain exactly one role=chart asset"
                ),
                "m6_6_ai_clip_ref": (
                    "role=ai_clip assets appear only in ai_clip scenes, at most "
                    "once per scene and exactly once in m6_5_v1 ai_clip scenes"
                ),
            }
        },
    )

    schema_version: str = "1.0"
    title: str
    audio_file: str
    scenes: tuple[Scene, ...] = Field(default_factory=tuple)
    visual_budget_profile: VisualBudgetProfile = "legacy"
    width: Literal[1080] = 1080
    height: Literal[1920] = 1920
    fps: Literal[30] = FRAMES_PER_SECOND

    @model_validator(mode="after")
    def validate_m6_5_chart_refs(self) -> "RenderInput":
        for scene in self.scenes:
            clips = sum(asset.role == "ai_clip" for asset in scene.visual_assets)
            if clips and scene.visual != "ai_clip":
                raise ValueError(f"Scene {scene.id}: ai_clip asset only in an ai_clip scene")
            if clips > 1 or (
                clips == 0
                and scene.visual == "ai_clip"
                and self.visual_budget_profile == "m6_5_v1"
            ):
                raise ValueError(
                    f"Scene {scene.id}: ai_clip scene requires exactly one ai_clip asset"
                )
        if self.visual_budget_profile != "m6_5_v1":
            return self
        for scene in self.scenes:
            if scene.visual == "chart" and sum(
                asset.role == "chart" for asset in scene.visual_assets
            ) != 1:
                raise ValueError(
                    f"Scene {scene.id}: M6.5 chart scene requires exactly one chart asset"
                )
        return self


def build_render_input(
    storyboard: Storyboard,
    audio_file: str,
    *,
    duration_policy: Literal["v1", "v2"] = "v1",
) -> RenderInput:
    _validate_relative_posix_path(audio_file, "audio")

    expected_start = 0
    for scene in storyboard.scenes:
        if scene.start_frame != expected_start:
            if scene.start_frame < expected_start:
                raise ValueError(f"Scene {scene.id}: overlaps the previous scene")
            raise ValueError(f"Scene {scene.id}: must start at frame {expected_start}")
        if scene.evidence_highlight is not None:
            _validate_relative_posix_path(scene.evidence_highlight.image, scene.id)
        for asset in scene.visual_assets:
            _validate_relative_posix_path(asset.path, scene.id)
        expected_start += scene.duration_frames

    if not storyboard.scenes:
        raise ValueError("Scene <none>: storyboard must contain at least one scene")
    if duration_policy == "v1" and not MIN_DURATION_FRAMES <= expected_start <= MAX_DURATION_FRAMES:
        raise ValueError(
            f"Scene {storyboard.scenes[-1].id}: total duration must be between "
            f"{MIN_DURATION_FRAMES} and {MAX_DURATION_FRAMES} frames"
        )

    return RenderInput(
        title=storyboard.title,
        audio_file=audio_file,
        scenes=storyboard.scenes,
        visual_budget_profile=storyboard.visual_budget_profile,
    )


def audio_timing_qa(audio_duration_ms: int, final_frame: int) -> dict[str, int]:
    """Refuse narration beyond the last reviewed frame; report measured tail."""
    if audio_duration_ms < 0 or final_frame <= 0:
        raise ValueError("audio duration and final frame must be positive")
    if 30 * audio_duration_ms > 1000 * (final_frame + 1):
        raise ValueError("narration WAV exceeds reviewed storyboard timeline")
    composition_ms = (1000 * final_frame + 29) // 30
    return {
        "audio_duration_ms": audio_duration_ms,
        "composition_duration_ms": composition_ms,
        "trailing_visual_ms": max(0, composition_ms - audio_duration_ms),
    }


def _validate_relative_posix_path(path: str, location: str) -> None:
    normalized = PurePosixPath(path)
    parts = normalized.parts
    if (
        not path
        or not parts
        or "\\" in path
        or normalized.is_absolute()
        or ".." in parts
        or ":" in parts[0]
    ):
        raise ValueError(f"Scene {location}: media path must be relative POSIX")
