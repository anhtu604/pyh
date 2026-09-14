from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from healthvideo.domain.brand import MascotPose
from healthvideo.domain.visual_budget import VisualBudgetOverride, VisualBudgetProfile


class VisualAssetRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    role: Literal["whiteboard", "mascot", "brand", "chart"]
    pose: MascotPose | None = None

    @model_validator(mode="after")
    def _validate_reference(self) -> "VisualAssetRef":
        path = PurePosixPath(self.path)
        if (
            not self.path
            or not self.path.strip()
            or self.path in {".", "./"}
            or not path.parts
            or "\\" in self.path
            or path.is_absolute()
            or ".." in path.parts
            or ":" in path.parts[0]
        ):
            raise ValueError("visual asset path must be safe relative POSIX")
        if self.role == "mascot" and self.pose is None:
            raise ValueError("mascot visual asset requires pose")
        if self.role in {"whiteboard", "brand", "chart"} and self.pose is not None:
            raise ValueError(f"{self.role} visual asset cannot have pose")
        return self


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
    source_id: str | None = None
    page: int | None = Field(default=None, ge=1)
    crop_x: float | None = Field(default=None, ge=0, le=1)
    crop_y: float | None = Field(default=None, ge=0, le=1)
    crop_width: float | None = Field(default=None, gt=0, le=1)
    crop_height: float | None = Field(default=None, gt=0, le=1)
    crop_pixel_width: int | None = Field(default=None, gt=0)
    crop_pixel_height: int | None = Field(default=None, gt=0)
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
        if (self.source_id is None) != (self.page is None):
            raise ValueError("Evidence highlight source_id and page must be paired")
        if self.source_id is not None and not self.source_id.strip():
            raise ValueError("Evidence highlight source_id must be nonblank")
        if self.x + self.width > 1:
            raise ValueError("Evidence highlight x + width must be at most 1")
        if self.y + self.height > 1:
            raise ValueError("Evidence highlight y + height must be at most 1")
        crop = (
            self.crop_x,
            self.crop_y,
            self.crop_width,
            self.crop_height,
            self.crop_pixel_width,
            self.crop_pixel_height,
        )
        if any(value is not None for value in crop):
            if any(value is None for value in crop):
                raise ValueError("Evidence highlight crop rectangle must be complete")
            assert self.crop_x is not None and self.crop_y is not None
            assert self.crop_width is not None and self.crop_height is not None
            if self.source_id is None or self.page is None:
                raise ValueError("Evidence highlight crop needs source_id and page")
            if (
                self.crop_x + self.crop_width > 1
                or self.crop_y + self.crop_height > 1
                or self.x < self.crop_x
                or self.y < self.crop_y
                or self.x + self.width > self.crop_x + self.crop_width + 1e-9
                or self.y + self.height > self.crop_y + self.crop_height + 1e-9
            ):
                raise ValueError("Evidence highlight must be contained within crop")
        return self


class Scene(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    id: str
    start_frame: int = Field(json_schema_extra={"minimum": 0})
    duration_frames: int = Field(json_schema_extra={"exclusiveMinimum": 0})
    narration: str
    script_line_id: str | None = None
    claim_id: str | None = None
    source_marker: str | None = Field(
        default=None, json_schema_extra={"pattern": r"\S"}
    )
    visual: Literal["whiteboard", "chart", "evidence_highlight", "ai_clip", "brand_outro"]
    evidence_highlight: EvidenceHighlight | None = None
    visual_assets: tuple[VisualAssetRef, ...] = ()

    @field_validator("source_marker")
    @classmethod
    def validate_source_marker(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("source_marker must contain a visible marker")
        return value

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
        paths = [asset.path for asset in self.visual_assets]
        if len(paths) != len(set(paths)):
            raise ValueError(f"Scene {self.id}: duplicate visual asset path")
        return self


class Storyboard(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    title: str
    scenes: tuple[Scene, ...] = Field(default_factory=tuple)
    visual_budget_profile: VisualBudgetProfile = "legacy"
    visual_budget_override: VisualBudgetOverride | None = None

    @model_validator(mode="after")
    def validate_visual_budget_activation(self) -> "Storyboard":
        if (
            self.visual_budget_override is not None
            and self.visual_budget_profile != "m6_5_v1"
        ):
            raise ValueError("visual budget override requires m6_5_v1 profile")
        return self
