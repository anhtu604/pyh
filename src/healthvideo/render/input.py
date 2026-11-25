from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.domain.format_profile import FORMAT_SPECS, FormatProfile
from healthvideo.domain.long_form import long_form_storyboard
from healthvideo.domain.quality_standards import QualityProfile, R5Contract
from healthvideo.domain.storyboard import Scene, Storyboard, VisualStyle
from healthvideo.domain.visual_budget import VisualBudgetProfile

FRAMES_PER_SECOND = 30
MIN_DURATION_FRAMES = 45 * FRAMES_PER_SECOND
MAX_DURATION_FRAMES = 180 * FRAMES_PER_SECOND
MAX_TRAILING_VISUAL_MS = 1500
MAX_SCENE_DRIFT_MS = 120


class R5RevisionAsset(BaseModel):
    """Verified, revision-local provenance, shared with the R5 renderer."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"\S")
    path: str
    title: str = Field(pattern=r"\S")
    author: str = Field(pattern=r"\S")
    repository: str = Field(pattern=r"\S")
    license: Literal["Public Domain", "CC0", "CC BY 3.0", "CC BY 4.0"]
    license_url: str | None
    source_page: str = Field(pattern=r"^https://\S+$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def safe_provenance(self) -> "R5RevisionAsset":
        _validate_relative_posix_path(self.path, "R5 asset")
        if self.license_url is not None and not self.license_url.startswith("https://"):
            raise ValueError("R5 asset license_url requires HTTPS")
        if self.license.startswith("CC BY") and not self.license_url:
            raise ValueError("R5 attribution license requires license_url")
        return self


class YouTubeCTA(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(pattern=r"\S")
    mascot_path: str = "clips/cta/welcome.svg"
    logo_path: str = "clips/cta/logo.svg"
    duration_frames: Literal[90] = 90

    @model_validator(mode="after")
    def validate_path(self) -> "YouTubeCTA":
        _validate_relative_posix_path(self.mascot_path, "YouTube CTA")
        _validate_relative_posix_path(self.logo_path, "YouTube CTA logo")
        return self


class RenderInput(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "x-invariants": {
                "m6_5_chart_ref": (
                    "m6_5_v1 chart scenes contain exactly one role=chart asset"
                ),
            }
        },
    )

    schema_version: str = "1.0"
    title: str
    quality_profile: QualityProfile | None = Field(default=None, exclude_if=lambda v: v is None)
    r5_contract: R5Contract | None = Field(default=None, exclude_if=lambda v: v is None)
    r5_assets: tuple[R5RevisionAsset, ...] = Field(default=(), exclude_if=lambda v: not v)
    visual_style: VisualStyle | None = Field(default=None, exclude_if=lambda v: v is None)
    youtube_cta: YouTubeCTA | None = None
    audio_file: str
    scenes: tuple[Scene, ...] = Field(default_factory=tuple)
    visual_budget_profile: VisualBudgetProfile = "explain_first_v1"
    format_profile: FormatProfile = "vertical_clip"
    width: Literal[1080, 1920] = 1080
    height: Literal[1920, 1080] = 1920
    fps: Literal[30] = FRAMES_PER_SECOND

    @model_validator(mode="after")
    def validate_r5_activation(self) -> "RenderInput":
        if self.quality_profile is None and (
            self.r5_contract is not None or self.r5_assets or any(s.shots or s.resolved_shots for s in self.scenes)
        ):
            raise ValueError("R5 data requires quality_profile=r5_v1")
        if self.quality_profile == "r5_v1" and self.r5_contract is None:
            raise ValueError("quality_profile=r5_v1 requires r5_contract")
        if self.quality_profile == "r5_v1":
            by_path = {asset.path: asset for asset in self.r5_assets}
            if len(by_path) != len(self.r5_assets) or len({a.id for a in self.r5_assets}) != len(self.r5_assets):
                raise ValueError("R5 asset metadata requires unique id/path")
            for scene in self.scenes:
                if not scene.resolved_shots:
                    raise ValueError(f"Scene {scene.id}: R5 requires resolved shots")
                for shot in scene.resolved_shots:
                    for path in shot.asset_paths:
                        if path not in by_path:
                            raise ValueError(f"Scene {scene.id} shot {shot.id} asset {path}: missing metadata")
        return self

    @model_validator(mode="after")
    def validate_m6_5_chart_refs(self) -> "RenderInput":
        from healthvideo.render.beats import visual_rhythm_qa
        from healthvideo.render.word_timing import entrance_timing_qa

        for scene in self.scenes:
            entrance_timing_qa(scene)
            if self.quality_profile is None:
                visual_rhythm_qa(scene)
        spec = FORMAT_SPECS[self.format_profile]
        if (self.width, self.height) != (spec.width, spec.height):
            raise ValueError(
                f"{self.format_profile} requires {spec.width}x{spec.height}"
            )
        if self.youtube_cta is not None:
            final_frame = max(
                (scene.start_frame + scene.duration_frames for scene in self.scenes), default=0
            ) + self.youtube_cta.duration_frames
            if self.format_profile != "vertical_clip" or not 1800 <= final_frame <= 5400:
                raise ValueError("YouTube CTA clip duration must be between 1800 and 5400 frames")
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
    r5_assets: tuple[R5RevisionAsset, ...] | list[dict[str, Any]] = (),
) -> RenderInput:
    _validate_relative_posix_path(audio_file, "audio")
    storyboard = long_form_storyboard(storyboard)

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
    spec = FORMAT_SPECS[storyboard.format_profile]
    if (
        storyboard.format_profile == "youtube_long"
        and not spec.min_frames <= expected_start <= spec.max_frames
    ):
        raise ValueError(
            f"Scene {storyboard.scenes[-1].id}: total duration must be between "
            f"{spec.min_frames} and {spec.max_frames} frames"
        )

    from healthvideo.render.beats import resolve_scene_beats

    return RenderInput(
        title=storyboard.title,
        quality_profile=storyboard.quality_profile,
        r5_contract=storyboard.r5_contract,
        r5_assets=r5_assets,
        visual_style=storyboard.visual_style,
        audio_file=audio_file,
        scenes=(storyboard.scenes if storyboard.quality_profile == "r5_v1"
                else tuple(resolve_scene_beats(scene) for scene in storyboard.scenes)),
        visual_budget_profile=storyboard.visual_budget_profile,
        format_profile=storyboard.format_profile,
        width=spec.width,
        height=spec.height,
    )


def audio_timing_qa(
    audio_duration_ms: int, final_frame: int, *,
    timing_record: Mapping[str, Any] | None = None,
) -> dict[str, int]:
    """Refuse narration beyond the last reviewed frame; report measured tail."""
    if audio_duration_ms < 0 or final_frame <= 0:
        raise ValueError("audio duration and final frame must be positive")
    if 30 * audio_duration_ms > 1000 * (final_frame + 1):
        raise ValueError("narration WAV exceeds reviewed storyboard timeline")
    composition_ms = (1000 * final_frame + 29) // 30
    trailing_ms = max(0, composition_ms - audio_duration_ms)
    drift_ms = 0
    if timing_record is not None:
        alignment = timing_record["audio_alignment"]
        if not alignment:
            raise ValueError("Scene audio alignment is required")
        speech_ends: list[int] = []
        for item in alignment:
            audio_start, video_start = item["audio_start_ms"], item["video_start_ms"]
            if any(type(value) is not int or value < 0 for value in (audio_start, video_start)):
                raise ValueError("Invalid scene audio alignment")
            drift_ms = max(drift_ms, abs(audio_start - video_start))
            speech_end = item["speech_end_ms"]
            if speech_end is not None:
                if type(speech_end) is not int or speech_end < video_start or speech_end > audio_duration_ms:
                    raise ValueError("Invalid scene speech end")
                speech_ends.append(speech_end)
        intentional_frames = timing_record.get("intentional_tail_frames", 0)
        if type(intentional_frames) is not int or not 0 <= intentional_frames <= final_frame:
            raise ValueError("Invalid intentional tail frames")
        trailing_ms = max(0, composition_ms - max(speech_ends, default=0)
                          - round(intentional_frames * 1000 / 30))
    if trailing_ms > MAX_TRAILING_VISUAL_MS:
        raise ValueError(f"trailing visual silence {trailing_ms} ms exceeds {MAX_TRAILING_VISUAL_MS} ms")
    if drift_ms > MAX_SCENE_DRIFT_MS:
        raise ValueError(f"scene audio drift {drift_ms} ms exceeds {MAX_SCENE_DRIFT_MS} ms")
    return {
        "audio_duration_ms": audio_duration_ms,
        "composition_duration_ms": composition_ms,
        "trailing_visual_ms": trailing_ms,
        "max_scene_drift_ms": drift_ms,
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
