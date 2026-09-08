from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceHighlight(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "x-invariants": {
                "x_plus_width": "x + width <= 1",
                "y_plus_height": "y + height <= 1",
            }
        },
    )

    schema_version: str = "1.0"
    image: str = Field(json_schema_extra={"pattern": r"\S"})
    quote: str = Field(json_schema_extra={"pattern": r"\S"})
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(ge=0, le=1)
    height: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_highlight(self) -> "EvidenceHighlight":
        if not self.image.strip():
            raise ValueError("Evidence highlight image is required")
        if not self.quote.strip():
            raise ValueError("Evidence highlight quote is required")
        if self.x + self.width > 1:
            raise ValueError("Evidence highlight x + width must be at most 1")
        if self.y + self.height > 1:
            raise ValueError("Evidence highlight y + height must be at most 1")
        return self


class Scene(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    id: str
    start_frame: int = Field(json_schema_extra={"minimum": 0})
    duration_frames: int = Field(json_schema_extra={"exclusiveMinimum": 0})
    narration: str
    claim_id: str | None = None
    source_marker: str | None = Field(
        default=None, json_schema_extra={"pattern": r"\S"}
    )
    visual: Literal["whiteboard", "chart", "evidence_highlight", "ai_clip"]
    evidence_highlight: EvidenceHighlight | None = None

    @model_validator(mode="after")
    def validate_scene(self) -> "Scene":
        if self.start_frame < 0:
            raise ValueError(f"Scene {self.id}: start_frame must be at least 0")
        if self.duration_frames <= 0:
            raise ValueError(f"Scene {self.id}: duration_frames must be greater than 0")
        if self.visual == "evidence_highlight":
            if not self.source_marker or not self.source_marker.strip():
                raise ValueError(
                    f"Scene {self.id}: evidence_highlight requires a source_marker"
                )
            if self.evidence_highlight is None:
                raise ValueError(
                    f"Scene {self.id}: evidence_highlight requires image and quote"
                )
        return self


class Storyboard(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    title: str
    scenes: tuple[Scene, ...] = Field(default_factory=tuple)
