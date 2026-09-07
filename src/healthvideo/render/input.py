from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from healthvideo.domain.storyboard import Scene, Storyboard

FRAMES_PER_SECOND = 30
MIN_DURATION_FRAMES = 45 * FRAMES_PER_SECOND
MAX_DURATION_FRAMES = 90 * FRAMES_PER_SECOND


class RenderInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    title: str
    audio_file: str
    scenes: tuple[Scene, ...] = Field(default_factory=tuple)
    width: Literal[1080] = 1080
    height: Literal[1920] = 1920
    fps: Literal[30] = FRAMES_PER_SECOND


def build_render_input(storyboard: Storyboard, audio_file: str) -> RenderInput:
    _validate_relative_posix_path(audio_file, "audio")

    expected_start = 0
    for scene in storyboard.scenes:
        if scene.start_frame != expected_start:
            if scene.start_frame < expected_start:
                raise ValueError(f"Scene {scene.id}: overlaps the previous scene")
            raise ValueError(f"Scene {scene.id}: must start at frame {expected_start}")
        if scene.evidence_highlight is not None:
            _validate_relative_posix_path(scene.evidence_highlight.image, scene.id)
        expected_start += scene.duration_frames

    if not storyboard.scenes:
        raise ValueError("Scene <none>: storyboard must contain at least one scene")
    if not MIN_DURATION_FRAMES <= expected_start <= MAX_DURATION_FRAMES:
        raise ValueError(
            f"Scene {storyboard.scenes[-1].id}: total duration must be between "
            f"{MIN_DURATION_FRAMES} and {MAX_DURATION_FRAMES} frames"
        )

    return RenderInput(
        title=storyboard.title,
        audio_file=audio_file,
        scenes=storyboard.scenes,
    )


def _validate_relative_posix_path(path: str, location: str) -> None:
    normalized = PurePosixPath(path)
    if (
        not path
        or "\\" in path
        or normalized.is_absolute()
        or ".." in normalized.parts
        or ":" in normalized.parts[0]
    ):
        raise ValueError(f"Scene {location}: media path must be relative POSIX")
