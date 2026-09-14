"""Typed provenance for reviewed AI-generated video assets."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SHA256_HEX_PATTERN = r"^[0-9a-f]{64}$"
_VALID_MEDIA_CONTRACTS = {
    ("video/mp4", "mp4", 1080, 1920, 24, 4000, 96),
    ("video/mp4", "mp4", 1080, 1920, 24, 6000, 144),
    ("video/mp4", "mp4", 1080, 1920, 24, 8000, 192),
}


class AIClipProvenance(BaseModel):
    """Provider request identity and measured media properties for one clip."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    provider: Literal["google_vertex_ai"]
    model: str
    prompt: str
    requested_seed: int | None = None
    generated_at: datetime
    request_sha256: str = Field(pattern=_SHA256_HEX_PATTERN)
    output_sha256: str = Field(pattern=_SHA256_HEX_PATTERN)
    mime_type: Literal["video/mp4"]
    container: Literal["mp4"]
    width: Literal[1080]
    height: Literal[1920]
    source_fps: Literal[24]
    duration_ms: Literal[4000, 6000, 8000]
    source_frame_count: Literal[96, 144, 192]

    @field_validator("model", "prompt")
    @classmethod
    def _require_visible_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("AI clip model and prompt must be nonblank")
        return value

    @field_validator("generated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("AI clip generated_at must include a timezone")
        return value

    @model_validator(mode="after")
    def _validate_duration_frames(self) -> "AIClipProvenance":
        validate_ai_clip_media_contract(self)
        return self


def validate_ai_clip_media_contract(provenance: AIClipProvenance) -> None:
    """Reject declared or measured metadata outside the reviewed clip contract."""

    media_contract = (
        provenance.mime_type,
        provenance.container,
        provenance.width,
        provenance.height,
        provenance.source_fps,
        provenance.duration_ms,
        provenance.source_frame_count,
    )
    if media_contract not in _VALID_MEDIA_CONTRACTS:
        raise ValueError("AI clip media contract does not match a reviewed profile")
