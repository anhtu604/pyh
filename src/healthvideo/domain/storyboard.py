from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from healthvideo.domain.brand import MascotPose
from healthvideo.domain.explainer import Nonblank
from healthvideo.domain.format_profile import FormatProfile
from healthvideo.domain.quality_standards import (
    QualityProfile,
    R5Contract,
    R5Shot,
    ResolvedR5Shot,
)
from healthvideo.domain.visual_budget import VisualBudgetOverride, VisualBudgetProfile
from healthvideo.visuals.anatomy_library import load_library

MECHANISM_VISUALS = ("anatomy_animation", "process_animation", "comparison", "timelapse")
VisualStyle = Literal["scale_zoom", "iso_infographic", "whiteboard"]
_SHARED_STYLE_VISUALS = frozenset({
    "chart", "source_card", "evidence_highlight", "brand_outro", "stat_gauge", "kinetic_term",
})
STYLE_VISUALS: dict[VisualStyle, frozenset[str]] = {
    "scale_zoom": _SHARED_STYLE_VISUALS | frozenset(MECHANISM_VISUALS) | {"whiteboard"},
    "iso_infographic": _SHARED_STYLE_VISUALS | frozenset(MECHANISM_VISUALS) | {"whiteboard"},
    "whiteboard": _SHARED_STYLE_VISUALS | {"whiteboard", "process_animation", "comparison"},
}
MotionEmphasis = Literal[
    "marker-underline-title",
    "lead-word-zoom-assemble",
    "outline-word-fill",
    "title-demote-to-label",
    "scan-bracket-sweep",
    "scanline-annotate-focus",
    "spotlight-sweep-moves",
]
MotionTransition = Literal[
    "circle-match-iris",
    "wipe-transitions",
    "crash-zoom-punch",
]


class SceneMotion(BaseModel):
    """Optional shotcraft motion overlay and transition_in for a scene."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    emphasis: MotionEmphasis | None = Field(default=None, exclude_if=lambda v: v is None)
    emphasis_text: Nonblank | None = Field(default=None, exclude_if=lambda v: v is None)
    transition_in: MotionTransition | None = Field(default=None, exclude_if=lambda v: v is None)

    @model_validator(mode="after")
    def validate_motion(self) -> "SceneMotion":
        if self.emphasis is None and self.transition_in is None:
            raise ValueError("motion requires emphasis or transition_in")
        if self.emphasis_text is not None and self.emphasis is None:
            raise ValueError("motion.emphasis_text requires emphasis")
        return self


class StatGauge(BaseModel):
    """Single claim-backed number + unit + label rendered via gauge or chart-live."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float | int | Nonblank
    unit: Nonblank
    label: Nonblank
    max_value: float | None = Field(default=None, gt=0, exclude_if=lambda v: v is None)
    variant: Literal[
        "gauge-readout-moves",
        "chart-live-moves",
        "timeline-travel",
    ] = "gauge-readout-moves"

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: float | str) -> float | str:
        import math

        if isinstance(value, bool):
            raise TypeError("stat_gauge value cannot be boolean")
        if isinstance(value, (int, float)):
            if not math.isfinite(value):
                raise ValueError("stat_gauge value must be finite")
            return value
        if not any(ch.isdigit() for ch in value):
            raise ValueError("stat_gauge string value must contain a number")
        return value


class KineticTerm(BaseModel):
    """Medical term + short definition rendered via lead-word or outline-fill."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    term: Nonblank
    definition: Nonblank
    variant: Literal[
        "lead-word-zoom-assemble",
        "outline-word-fill",
        "marker-underline-title",
        "title-demote-to-label",
    ] = "lead-word-zoom-assemble"


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


class SceneBeat(BaseModel):
    """A scene-local visual change anchored to narration or elapsed seconds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    at: str | float
    focus: Nonblank | None = None
    labels: tuple[Nonblank, ...] = Field(default=(), max_length=6)
    action: Nonblank | None = None
    start_frame: int | None = Field(default=None, ge=0, exclude_if=lambda v: v is None)

    @field_validator("at")
    @classmethod
    def validate_at(cls, value):
        import math

        if isinstance(value, str):
            if not value.strip():
                raise ValueError("beat keyword must be nonblank")
        elif not math.isfinite(value) or value < 0:
            raise ValueError("beat time must be finite and nonnegative")
        return value

    @field_validator("labels")
    @classmethod
    def unique_labels(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("beat labels must be unique")
        return value


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
    shots: tuple[R5Shot, ...] = Field(default=(), exclude_if=lambda v: not v)
    resolved_shots: tuple[ResolvedR5Shot, ...] = Field(default=(), exclude_if=lambda v: not v)
    visual_takeaway: str | None = Field(
        default=None, min_length=1, max_length=160, exclude_if=lambda v: v is None,
    )
    words: tuple[CaptionWord, ...] = Field(default=(), exclude_if=lambda v: not v)
    entrances: tuple[TextEntrance, ...] = Field(default=(), exclude_if=lambda v: not v)
    beats: tuple[SceneBeat, ...] = Field(default=(), exclude_if=lambda v: not v)
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
        "stat_gauge", "kinetic_term",
    ]
    explainer_layer_id: str | None = Field(default=None, exclude_if=lambda v: v is None)
    anatomy: SceneAnatomy | None = Field(default=None, exclude_if=lambda v: v is None)
    evidence_highlight: EvidenceHighlight | None = None
    source_card: SourceCard | None = Field(default=None, exclude_if=lambda v: v is None)
    stat_gauge: StatGauge | None = Field(default=None, exclude_if=lambda v: v is None)
    kinetic_term: KineticTerm | None = Field(default=None, exclude_if=lambda v: v is None)
    motion: SceneMotion | None = Field(default=None, exclude_if=lambda v: v is None)
    mascot_pose: MascotPose | None = Field(default=None, exclude_if=lambda v: v is None)
    visual_assets: tuple[VisualAssetRef, ...] = ()
    labels: tuple[AssetTextLabel, ...] = Field(default=(), exclude_if=lambda value: not value)
    annotations: tuple[AssetTextLabel, ...] = Field(default=(), exclude_if=lambda value: not value)

    @field_validator("visual_takeaway", mode="before")
    @classmethod
    def strip_visual_takeaway(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

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
        if self.visual == "stat_gauge" and (
            self.stat_gauge is None or not self.claim_id or not self.claim_id.strip()
        ):
            raise ValueError(f"Scene {self.id}: stat_gauge requires claim_id and stat_gauge metadata")
        if self.visual != "stat_gauge" and self.stat_gauge is not None:
            raise ValueError(f"Scene {self.id}: stat_gauge metadata requires stat_gauge visual")
        if self.visual == "kinetic_term" and self.kinetic_term is None:
            raise ValueError(f"Scene {self.id}: kinetic_term requires kinetic_term metadata")
        if self.visual != "kinetic_term" and self.kinetic_term is not None:
            raise ValueError(f"Scene {self.id}: kinetic_term metadata requires kinetic_term visual")
        if self.motion is not None and self.motion.emphasis_text is not None:
            from healthvideo.audio.align import normalize_word

            narration_tokens = [w for w in (normalize_word(t) for t in self.narration.split()) if w]
            emphasis_tokens = [w for w in (normalize_word(t) for t in self.motion.emphasis_text.split()) if w]
            if not emphasis_tokens or not any(
                narration_tokens[i : i + len(emphasis_tokens)] == emphasis_tokens
                for i in range(len(narration_tokens) - len(emphasis_tokens) + 1)
            ):
                raise ValueError(
                    f"Scene {self.id}: motion.emphasis_text must be in narration: {self.motion.emphasis_text}"
                )
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
        if self.beats:
            from healthvideo.audio.align import normalize_word
            from healthvideo.visuals.anatomy_library import cue_actions

            if self.anatomy is None:
                raise ValueError(f"Scene {self.id}: beats require a mechanism anatomy component")
            repo = Path(__file__).resolve().parents[3]
            info = load_library(repo).get(self.anatomy.subject)
            if info is None:
                raise ValueError(f"Scene {self.id}: unsupported anatomy subject {self.anatomy.subject!r}")
            focus_regions, labels = info.get("focus_regions", {}), info.get("labels", {})
            actions = cue_actions(repo, self.anatomy.subject)
            narration = [normalize_word(w) for w in self.narration.split()]
            for beat in self.beats:
                if beat.focus is not None and beat.focus not in focus_regions:
                    raise ValueError(f"Scene {self.id}: beat focus must exist in component: {beat.focus}")
                if any(label not in labels for label in beat.labels):
                    raise ValueError(f"Scene {self.id}: beat label must exist in component")
                if beat.action is not None and beat.action not in actions:
                    raise ValueError(f"Scene {self.id}: beat action must exist in component: {beat.action}")
                if isinstance(beat.at, str):
                    tokens = [normalize_word(w) for w in beat.at.split()]
                    if not any(narration[i:i+len(tokens)] == tokens
                               for i in range(len(narration)-len(tokens)+1)):
                        raise ValueError(f"Scene {self.id}: beat keyword must be in narration: {beat.at}")
                if beat.start_frame is not None and beat.start_frame >= self.duration_frames:
                    raise ValueError(f"Scene {self.id}: beat timing exceeds scene")
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
        if self.mascot_pose is not None:
            for asset in self.visual_assets:
                if asset.role == "mascot" and asset.pose != self.mascot_pose:
                    raise ValueError(
                        f"Scene {self.id}: mascot_pose ({self.mascot_pose.value}) "
                        f"conflicts with mascot visual asset pose ({asset.pose})"
                    )
        return self

    def resolved_mascot_pose(self) -> MascotPose | None:
        """Return explicit ``mascot_pose`` or the pose from a declared mascot asset."""
        if self.mascot_pose is not None:
            return self.mascot_pose
        for asset in self.visual_assets:
            if asset.role == "mascot" and asset.pose is not None:
                return asset.pose
        return None


class Storyboard(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    title: str
    quality_profile: QualityProfile | None = Field(default=None, exclude_if=lambda v: v is None)
    r5_contract: R5Contract | None = Field(default=None, exclude_if=lambda v: v is None)
    visual_style: VisualStyle | None = Field(default=None, exclude_if=lambda v: v is None)
    sfx_defaults: bool = Field(default=True, exclude_if=lambda v: v is True)
    scenes: tuple[Scene, ...] = Field(default_factory=tuple)
    visual_budget_profile: VisualBudgetProfile = "explain_first_v1"
    visual_budget_override: VisualBudgetOverride | None = None
    format_profile: FormatProfile = "vertical_clip"

    @model_validator(mode="after")
    def validate_visual_style(self) -> "Storyboard":
        if self.visual_style is None:
            return self
        for scene in self.scenes:
            if scene.visual not in STYLE_VISUALS[self.visual_style]:
                raise ValueError(
                    f"Cảnh {scene.id}: visual {scene.visual!r} không thuộc style {self.visual_style}"
                )
            if scene.visual in MECHANISM_VISUALS:
                takeaway = scene.visual_takeaway
                if takeaway is None or len(takeaway) < 12:
                    raise ValueError(
                        f"Cảnh {scene.id}: visual_takeaway phải có ít nhất 12 ký tự"
                    )
                normalized = " ".join(takeaway.lower().split())
                if normalized in {
                    " ".join(scene.narration.lower().split()),
                    " ".join((scene.on_screen_text or "").lower().split()),
                }:
                    raise ValueError(
                        f"Cảnh {scene.id}: visual_takeaway phải khác narration và on_screen_text"
                    )
        return self

    @model_validator(mode="after")
    def validate_mechanism_variety(self) -> "Storyboard":
        if self.quality_profile == "r5_v1":
            return self
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
        required = 4 if self.format_profile == "youtube_long" else 2
        if len(mechanisms) >= required and len({scene.anatomy.subject for scene in mechanisms}) < required:
            raise ValueError(f"{self.format_profile} requires at least {required} anatomy.subject values; "
                             "choose from library.json: " + ", ".join(supported_anatomy_subjects()))
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
    def validate_r5_activation(self) -> "Storyboard":
        if self.quality_profile is None and (
            self.r5_contract is not None or any(s.shots or s.resolved_shots for s in self.scenes)
        ):
            raise ValueError("R5 data requires quality_profile=r5_v1")
        if self.quality_profile == "r5_v1" and self.r5_contract is None:
            raise ValueError("quality_profile=r5_v1 requires r5_contract")
        return self

    @model_validator(mode="after")
    def validate_visual_budget_activation(self) -> "Storyboard":
        if (
            self.visual_budget_override is not None
            and self.visual_budget_profile != "m6_5_v1"
        ):
            raise ValueError("visual budget override requires m6_5_v1 profile")
        return self


def supported_anatomy_subjects(repo: Path | None = None) -> tuple[str, ...]:
    """Read current renderer subjects, including additions made by a running worker."""
    if repo is None:
        repo = Path(__file__).resolve().parents[3]
    return tuple(load_library(repo))


# Import-time snapshot for compatibility only; validation must read the live library.
SUPPORTED_ANATOMY_SUBJECTS = supported_anatomy_subjects()


def validate_anatomy_subjects(storyboard: Storyboard) -> None:
    """Require anatomy subjects supported by the renderer."""
    subjects = supported_anatomy_subjects()
    for scene in storyboard.scenes:
        if scene.anatomy is not None and scene.anatomy.subject not in subjects:
            raise ValueError(
                f"Scene {scene.id}: unsupported anatomy subject {scene.anatomy.subject!r}; "
                f"supported subjects: {', '.join(subjects)}"
            )


def validate_style_a_mascot_poses(storyboard: Storyboard) -> None:
    """Require a valid ``mascot_pose`` on hook, each chapter opening, and outro (Style A §6)."""
    if not storyboard.scenes:
        return
    valid_poses = ", ".join(pose.value for pose in MascotPose)
    missing: list[str] = []
    seen_chapter: str | None = None
    last_index = len(storyboard.scenes) - 1
    for index, scene in enumerate(storyboard.scenes):
        roles: list[str] = []
        if index == 0:
            roles.append("hook")
        if scene.chapter_id is not None and scene.chapter_id != seen_chapter:
            roles.append(f"đầu chương {scene.chapter_id}")
            seen_chapter = scene.chapter_id
        if index == last_index or scene.visual == "brand_outro":
            roles.append("outro")
        if roles and scene.resolved_mascot_pose() is None:
            missing.append(f"Scene {scene.id} ({'/'.join(roles)})")
    if missing:
        raise ValueError(
            "Storyboard không đạt chuẩn phong cách A — thiếu mascot_pose "
            f"(9 tư thế hợp lệ: {valid_poses}) tại: {', '.join(missing)}"
        )
