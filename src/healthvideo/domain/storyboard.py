from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from healthvideo.domain.brand import MascotPose
from healthvideo.domain.explainer import Nonblank
from healthvideo.domain.format_profile import FormatProfile
from healthvideo.domain.visual_budget import VisualBudgetOverride, VisualBudgetProfile
from healthvideo.visuals.anatomy_library import load_library

MECHANISM_VISUALS = ("anatomy_animation", "process_animation", "comparison", "timelapse")


class SourceCard(BaseModel):
    """Renderer text copied exactly from the evidence ledger, never a source image."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: Nonblank
    title: Nonblank
    journal: str
    year: int | None = None
    pmid: str | None = None
    doi: str | None = None
    interpretation: Nonblank

    @classmethod
    def from_ledger(cls, ledger: Mapping[str, Any], claim_id: str, source_id: str) -> "SourceCard":
        from healthvideo.domain.evidence import EvidenceClaim, SourceRecord

        claims = {item["id"]: item for item in ledger.get("claims", [])}
        records = {item["id"]: item for item in ledger.get("records", [])}
        if claim_id not in claims or source_id not in records:
            raise ValueError("source card requires claim and source in ledger")
        claim = EvidenceClaim.model_validate(claims[claim_id])
        source = SourceRecord.model_validate(records[source_id])
        if source_id not in claim.sources:
            raise ValueError("source card source must belong to claim in ledger")
        return cls(source_id=source.id, title=source.title, journal=source.journal,
                   year=source.year, pmid=source.pmid, doi=source.doi,
                   interpretation=claim.text_public)


class AnatomyCue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    word: Nonblank
    action: Nonblank
    start_frame: int | None = Field(default=None, ge=0, exclude_if=lambda v: v is None)


class CaptionWord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: Nonblank
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_end(self) -> "CaptionWord":
        if self.end_frame < self.start_frame:
            raise ValueError("word end must follow start")
        return self


class TextEntrance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: Nonblank
    start_frame: int = Field(ge=0)


class SceneAnatomy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: Nonblank
    state: Literal["normal", "diseased"]
    severity: float = Field(default=0, ge=0, le=1)
    motion: Nonblank
    cues: tuple[AnatomyCue, ...] = Field(default=(), exclude_if=lambda v: not v)


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


class AssetTextLabel(BaseModel):
    """Baked annotation declared by its target asset; overlay text belongs in Remotion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_path: str
    text: Nonblank


class SceneSFX(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    at: str | float = 'start'
    volume: float = Field(default=.2, ge=.15, le=.4, allow_inf_nan=False)

    @field_validator('id')
    @classmethod
    def catalog_id(cls, value: str) -> str:
        from healthvideo.audio.sfx import load_catalog

        if value not in load_catalog():
            raise ValueError('SFX id must belong to CC0 catalog')
        return value

    @field_validator('at')
    @classmethod
    def valid_at(cls, value):
        import math

        if isinstance(value, str):
            if not value.strip():
                raise ValueError('SFX keyword must not be empty')
        elif not math.isfinite(value) or value < 0:
            raise ValueError('SFX time must be finite and nonnegative')
        return value


class Scene(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    id: str
    start_frame: int = Field(json_schema_extra={"minimum": 0})
    duration_frames: int = Field(json_schema_extra={"exclusiveMinimum": 0})
    narration: str
    words: tuple[CaptionWord, ...] = Field(default=(), exclude_if=lambda v: not v)
    entrances: tuple[TextEntrance, ...] = Field(default=(), exclude_if=lambda v: not v)
    sfx: tuple[SceneSFX, ...] = Field(default=(), max_length=2, exclude_if=lambda v: not v)
    on_screen_text: str | None = Field(default=None, max_length=90, exclude_if=lambda v: v is None)
    script_line_id: str | None = None
    claim_id: str | None = None
    chapter_id: str | None = Field(default=None, pattern=r"^CH\d{2}$")
    source_marker: str | None = Field(
        default=None, json_schema_extra={"pattern": r"\S"}
    )
    visual: Literal[
        "whiteboard", "chart", "evidence_highlight", "source_card", "brand_outro",
        "anatomy_animation", "process_animation", "comparison", "timelapse",
    ]
    explainer_layer_id: str | None = Field(default=None, exclude_if=lambda v: v is None)
    anatomy: SceneAnatomy | None = Field(default=None, exclude_if=lambda v: v is None)
    evidence_highlight: EvidenceHighlight | None = None
    source_card: SourceCard | None = Field(default=None, exclude_if=lambda v: v is None)
    visual_assets: tuple[VisualAssetRef, ...] = ()
    labels: tuple[AssetTextLabel, ...] = Field(default=(), exclude_if=lambda value: not value)
    annotations: tuple[AssetTextLabel, ...] = Field(default=(), exclude_if=lambda value: not value)

    @field_validator("source_marker")
    @classmethod
    def validate_source_marker(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("source_marker must contain a visible marker")
        return value

    @model_validator(mode="after")
    def validate_scene(self) -> "Scene":
        if self.visual == "whiteboard" and not (
            (self.on_screen_text or "").strip()
            or any(asset.role == "whiteboard" for asset in self.visual_assets)
        ):
            raise ValueError(f"Scene {self.id}: whiteboard requires on_screen_text "
                             "or a visual_assets reference with role whiteboard")
        if self.visual == "source_card" and (
            self.source_card is None or not self.claim_id or not self.source_marker
        ):
            raise ValueError(f"Scene {self.id}: source_card requires claim, marker and ledger metadata")
        if self.visual != "source_card" and self.source_card is not None:
            raise ValueError(f"Scene {self.id}: source_card metadata requires source_card visual")
        if self.visual != "evidence_highlight" and self.evidence_highlight is not None:
            raise ValueError(f"Scene {self.id}: highlight metadata requires evidence_highlight visual")
        if self.visual in MECHANISM_VISUALS and self.anatomy is None:
            raise ValueError(f"Scene {self.id}: {self.visual} requires anatomy")
        if self.visual not in MECHANISM_VISUALS and self.anatomy is not None:
            raise ValueError(f"Scene {self.id}: {self.visual} forbids anatomy")
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
        if self.anatomy and self.anatomy.cues:
            from healthvideo.audio.align import normalize_word
            from healthvideo.visuals.anatomy_library import cue_actions

            narration_tokens = [normalize_word(w) for w in self.narration.split()]
            actions = cue_actions(Path(__file__).resolve().parents[3], self.anatomy.subject)
            for cue in self.anatomy.cues:
                tokens = [normalize_word(w) for w in cue.word.split()]
                if not any(narration_tokens[i:i+len(tokens)] == tokens
                           for i in range(len(narration_tokens)-len(tokens)+1)):
                    raise ValueError(f"Scene {self.id}: cue word must be in narration: {cue.word}")
                if cue.action not in actions:
                    raise ValueError(f"Scene {self.id}: cue action must exist in component: {cue.action}")
        for word in self.words:
            if word.end_frame > self.duration_frames:
                raise ValueError(f"Scene {self.id}: word timing exceeds scene")
        if any(b.start_frame < a.end_frame for a, b in zip(self.words, self.words[1:])):
            raise ValueError(f"Scene {self.id}: word timings overlap or are unordered")
        if any(e.start_frame >= self.duration_frames for e in self.entrances):
            raise ValueError(f"Scene {self.id}: entrance exceeds scene")
        paths = [asset.path for asset in self.visual_assets]
        if len(paths) != len(set(paths)):
            raise ValueError(f"Scene {self.id}: duplicate visual asset path")
        return self


class Storyboard(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    title: str
    sfx_defaults: bool = Field(default=True, exclude_if=lambda v: v is True)
    scenes: tuple[Scene, ...] = Field(default_factory=tuple)
    visual_budget_profile: VisualBudgetProfile = "explain_first_v1"
    visual_budget_override: VisualBudgetOverride | None = None
    format_profile: FormatProfile = "vertical_clip"

    @model_validator(mode="after")
    def validate_mechanism_variety(self) -> "Storyboard":
        previous = None
        run = 0
        for scene in self.scenes:
            key = (scene.visual, scene.anatomy.subject) if scene.anatomy else None
            run = run + 1 if key is not None and key == previous else 1
            if run > 4:
                raise ValueError(f"Scene {scene.id}: more than 4 consecutive mechanism scenes "
                                 "with the same anatomy.subject and visual; vary the view")
            previous = key
        mechanisms = [scene for scene in self.scenes if scene.anatomy is not None]
        if (self.format_profile == "youtube_long" and len(mechanisms) >= 6
                and len({scene.anatomy.subject for scene in mechanisms}) < 2):
            raise ValueError("youtube_long with at least 6 mechanism scenes requires at least 2 anatomy.subject "
                             "values; choose from library.json: " + ", ".join(SUPPORTED_ANATOMY_SUBJECTS))
        return self

    @model_validator(mode="after")
    def validate_chapters(self) -> "Storyboard":
        if self.format_profile != "youtube_long":
            return self
        seen: list[str] = []
        for scene in self.scenes:
            if scene.chapter_id is None:
                raise ValueError(f"Scene {scene.id}: youtube_long scene requires chapter_id")
            if seen and seen[-1] == scene.chapter_id:
                continue
            if scene.chapter_id in seen:
                raise ValueError(
                    f"Scene {scene.id}: chapter {scene.chapter_id} must be contiguous"
                )
            seen.append(scene.chapter_id)
        return self

    @model_validator(mode="after")
    def validate_visual_budget_activation(self) -> "Storyboard":
        if (
            self.visual_budget_override is not None
            and self.visual_budget_profile != "m6_5_v1"
        ):
            raise ValueError("visual budget override requires m6_5_v1 profile")
        return self


SUPPORTED_ANATOMY_SUBJECTS = tuple(load_library(Path(__file__).resolve().parents[3]))


def validate_anatomy_subjects(storyboard: Storyboard) -> None:
    """Require anatomy subjects supported by the renderer."""
    for scene in storyboard.scenes:
        if scene.anatomy is not None and scene.anatomy.subject not in SUPPORTED_ANATOMY_SUBJECTS:
            raise ValueError(
                f"Scene {scene.id}: unsupported anatomy subject {scene.anatomy.subject!r}; "
                f"supported subjects: {', '.join(SUPPORTED_ANATOMY_SUBJECTS)}"
            )
