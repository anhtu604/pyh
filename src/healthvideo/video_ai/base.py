"""Provider-neutral contracts for optional AI video authoring."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from healthvideo.storage.files import canonical_json_hash


class VeoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str
    model: Literal["veo-3.1-fast-generate-001"] = "veo-3.1-fast-generate-001"
    aspect_ratio: Literal["9:16"] = "9:16"
    resolution: Literal["1080p"] = "1080p"
    duration_seconds: Literal[4, 6, 8]
    sample_count: Literal[1] = 1
    requested_seed: int | None = None

    @field_validator("prompt")
    @classmethod
    def _nonblank_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Veo prompt must be nonblank")
        return value


class VeoResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    video_bytes: bytes
    mime_type: Literal["video/mp4"]

    @field_validator("video_bytes")
    @classmethod
    def _nonempty_video(cls, value: bytes) -> bytes:
        if not value:
            raise ValueError("Veo returned empty video content")
        return value


class VeoTransport(Protocol):
    def generate(self, request: VeoRequest) -> VeoResult: ...


class VideoProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mime_type: Literal["video/mp4"]
    container: Literal["mp4"]
    width: int
    height: int
    source_fps: int
    duration_ms: int
    source_frame_count: int
    video_stream_count: int


def veo_request_sha256(request: VeoRequest) -> str:
    return canonical_json_hash(request.model_dump(mode="json", exclude_none=True))
