"""Versioned R5 data contract. Resolution, measurement and review runtime live elsewhere.

Frame intervals are half-open and scene-relative on resolved shots/actions/windows;
report source intervals are composition-relative. No clinical values live here.
"""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

if TYPE_CHECKING:
    from healthvideo.domain.script import Script
    from healthvideo.domain.storyboard import Storyboard

QualityProfile = Literal["r5_v1"]
R5_STANDARD_NAME = "pyh_r5_quality_v1"
D1_MAX_TEXT_PERCENT = 15
D1_MAX_TEXT_SECONDS = 6
D2_STORY_MEDIAN_SECONDS = (2.5, 3.5)
D2_STORY_P90_MAX_SECONDS = 8
D2_MECHANISM_MEDIAN_SECONDS = (8, 20)
D2_ACTION_STEP_SECONDS = (3, 6)
D2_LONG_SHOT_SECONDS = 20
D2_LONG_SHOT_MIN_STEPS = 3
D2_HARD_EXPERIMENTAL = True
D3_MISSING_UPDATE_POLICY = "disclose_latest_source_and_search_date_without_inventing_update"
D4_SCRIPT_REVIEW_ROUNDS = 2
D4_VISUAL_REVIEW_ROUNDS = 3
D4_PRODUCT_REVIEW_ROUNDS = 3
D4_EXHAUSTED_POLICY = "stop_and_present_to_doctor"
R5_MAX_SIMULTANEOUS_LABELS = 2
R5_MAX_LABEL_WORDS = 3
R5_MAX_TAKEAWAY_WORDS = 8


def r5_standard_snapshot() -> dict[str, object]:
    """Copy the complete versioned thresholds into a newly opted-in revision."""
    return {
        "name": R5_STANDARD_NAME, "profile": "r5_v1",
        "D1": {"max_text_percent": D1_MAX_TEXT_PERCENT, "max_text_seconds": D1_MAX_TEXT_SECONDS},
        "D2": {
            "story_median_seconds": list(D2_STORY_MEDIAN_SECONDS),
            "story_p90_max_seconds": D2_STORY_P90_MAX_SECONDS,
            "mechanism_median_seconds": list(D2_MECHANISM_MEDIAN_SECONDS),
            "action_step_seconds": list(D2_ACTION_STEP_SECONDS),
            "long_shot_seconds": D2_LONG_SHOT_SECONDS,
            "long_shot_min_steps": D2_LONG_SHOT_MIN_STEPS,
            "hard_experimental": D2_HARD_EXPERIMENTAL,
        },
        "D3": {"missing_update_policy": D3_MISSING_UPDATE_POLICY},
        "D4": {"script_review_rounds": D4_SCRIPT_REVIEW_ROUNDS,
               "visual_review_rounds": D4_VISUAL_REVIEW_ROUNDS,
               "product_review_rounds": D4_PRODUCT_REVIEW_ROUNDS,
               "exhausted_policy": D4_EXHAUSTED_POLICY},
    }

# IDs reserved for R5.3.5/.6/.7, never module names or executable paths.
R5Component = Literal[
    "ScaleChain", "ZoomChain", "TakeawayCard", "VnLabSheet",
    "ReferenceDistribution", "CreditCard", "R5LiverLeakSignature", "StoryShot",
]
R5_COMPONENT_IDS = (
    "ScaleChain", "ZoomChain", "TakeawayCard", "VnLabSheet",
    "ReferenceDistribution", "CreditCard", "R5LiverLeakSignature", "StoryShot",
)
ShotKind = Literal["story", "mechanism", "recap", "credit"]
TextKind = Literal[
    "question", "takeaway", "worksheet", "source_card", "table", "lab_sheet",
    "text_tree", "credit", "label", "scale_bar",
]
Nonblank = Annotated[str, Field(pattern=r"\S")]
Frame = Annotated[int, Field(strict=True, ge=0)]


class R5Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class R5Question(R5Model):
    id: Nonblank
    text: Nonblank
    hook_line_id: Nonblank
    answer_line_ids: tuple[Nonblank, ...] = Field(min_length=1)


class R5Block(R5Model):
    id: Nonblank
    line_ids: tuple[Nonblank, ...] = Field(min_length=1)
    question_ids: tuple[Nonblank, ...] = Field(min_length=1)
    takeaway_line_id: Nonblank
    professional_update: StrictBool

    @model_validator(mode="after")
    def takeaway_in_block(self) -> R5Block:
        if self.takeaway_line_id not in self.line_ids:
            raise ValueError("takeaway_line_id must belong to block line_ids")
        return self


class R5Contract(R5Model):
    questions: tuple[R5Question, ...] = Field(min_length=2, max_length=4)
    blocks: tuple[R5Block, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def references(self) -> R5Contract:
        ids = {q.id for q in self.questions}
        if len(ids) != len(self.questions) or len({b.id for b in self.blocks}) != len(self.blocks):
            raise ValueError("duplicate question or block ID")
        served = {q for block in self.blocks for q in block.question_ids}
        if served != ids:
            raise ValueError("blocks must serve exactly the declared question IDs")
        if not any(block.professional_update for block in self.blocks):
            raise ValueError("at least one professional_update block is required")
        return self


class R5Anchor(R5Model):
    kind: Literal["scene_start", "scene_end", "phrase"]
    line_id: Nonblank | None = None
    phrase: Nonblank | None = None

    @model_validator(mode="after")
    def phrase_fields(self) -> R5Anchor:
        if self.kind == "phrase":
            if self.line_id is None or self.phrase is None:
                raise ValueError("phrase anchor requires line_id and phrase")
        elif self.line_id is not None or self.phrase is not None:
            raise ValueError("scene boundary forbids line_id and phrase")
        return self


class R5Action(R5Model):
    actor: Nonblank
    compartment: Nonblank
    change: Nonblank
    outcome: Nonblank
    start: R5Anchor
    end: R5Anchor


class R5TextWindow(R5Model):
    kind: TextKind
    text: Nonblank
    start: R5Anchor
    end: R5Anchor
    claim_ids: tuple[Nonblank, ...] = ()
    exception_reason: Nonblank | None = None

    @field_validator("text")
    @classmethod
    def no_tab_layout(cls, value: str) -> str:
        if "\t" in value:
            raise ValueError("R5 text forbids tab layout")
        return value


class R5Shot(R5Model):
    id: Nonblank
    kind: ShotKind
    tier: Nonblank | None
    component: R5Component
    asset_paths: tuple[Nonblank, ...]
    question_ids: tuple[Nonblank, ...]
    start: R5Anchor
    end: R5Anchor
    actions: tuple[R5Action, ...]
    text_windows: tuple[R5TextWindow, ...]
    long_shot_reason: Nonblank | None = None

    @field_validator("asset_paths")
    @classmethod
    def safe_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            path = PurePosixPath(value)
            if (not path.parts or path.is_absolute() or ".." in path.parts
                    or "\\" in value or ":" in value or any(c.isspace() for c in value)):
                raise ValueError("asset_paths must be relative POSIX manifest paths")
        if len(set(values)) != len(values):
            raise ValueError("duplicate asset path")
        return values


class FrameInterval(R5Model):
    start_frame: Frame
    end_frame: Frame

    @model_validator(mode="after")
    def positive_interval(self) -> FrameInterval:
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must follow start_frame")
        return self


class ResolvedR5Action(FrameInterval):
    actor: Nonblank
    compartment: Nonblank
    change: Nonblank
    outcome: Nonblank


class ResolvedR5TextWindow(FrameInterval):
    kind: TextKind
    text: Nonblank
    claim_ids: tuple[Nonblank, ...] = ()
    exception_reason: Nonblank | None = None

    _no_tab_layout = field_validator("text")(R5TextWindow.no_tab_layout.__func__)


class ResolvedR5Shot(FrameInterval):
    id: Nonblank
    kind: ShotKind
    tier: Nonblank | None
    component: R5Component
    asset_paths: tuple[Nonblank, ...]
    question_ids: tuple[Nonblank, ...]
    actions: tuple[ResolvedR5Action, ...]
    text_windows: tuple[ResolvedR5TextWindow, ...]
    long_shot_reason: Nonblank | None = None

    _safe_paths = field_validator("asset_paths")(R5Shot.safe_paths.__func__)

    @model_validator(mode="after")
    def contained_intervals(self) -> ResolvedR5Shot:
        for interval in (*self.actions, *self.text_windows):
            if interval.start_frame < self.start_frame or interval.end_frame > self.end_frame:
                raise ValueError("action/text interval must be contained in shot")
        return self


class ShotStatistics(R5Model):
    count: Frame
    median_seconds: float | None = Field(strict=True, ge=0, allow_inf_nan=False)
    p90_seconds: float | None = Field(strict=True, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def empty_is_na(self) -> ShotStatistics:
        if ((self.count == 0) != (self.median_seconds is None)
                or (self.count == 0) != (self.p90_seconds is None)):
            raise ValueError("empty shot groups require N/A statistics")
        return self


class QualitySourceInterval(FrameInterval):
    scene_id: Nonblank
    shot_id: Nonblank
    kind: TextKind


class QualityShotInterval(FrameInterval):
    scene_id: Nonblank
    shot_id: Nonblank
    kind: ShotKind


class QualityReport(R5Model):
    standard: Literal["pyh_r5_quality_v1"] = R5_STANDARD_NAME
    quality_profile: QualityProfile = "r5_v1"
    estimated: StrictBool
    fps: Literal[30] = 30
    denominator_frames: Annotated[int, Field(strict=True, gt=0)]
    numerator_frames: Frame
    shot_intervals: tuple[QualityShotInterval, ...]
    source_intervals: tuple[QualitySourceInterval, ...]
    text_union_intervals: tuple[FrameInterval, ...]
    story: ShotStatistics
    mechanism: ShotStatistics
    manual_review: Literal["pending", "passed", "failed"] = "pending"
    issues: tuple[str, ...] = ()

    @model_validator(mode="after")
    def report_bounds(self) -> QualityReport:
        if self.numerator_frames > self.denominator_frames:
            raise ValueError("numerator exceeds denominator")
        intervals = (*self.shot_intervals, *self.source_intervals, *self.text_union_intervals)
        if any(i.end_frame > self.denominator_frames for i in intervals):
            raise ValueError("report interval exceeds composition")
        if any(b.start_frame <= a.end_frame
               for a, b in zip(self.text_union_intervals, self.text_union_intervals[1:])):
            raise ValueError("text union intervals must be ordered and merged")
        if sum(i.end_frame - i.start_frame for i in self.text_union_intervals) != self.numerator_frames:
            raise ValueError("text union does not match numerator")
        return self


def validate_r5_contract(board: Storyboard, script: Script) -> None:
    """Validate ID/phrase mapping, never judge medical meaning or mutate the script.

    Manifest membership and aligned anchor resolution belong to later integration.
    """
    from healthvideo.domain.long_form import long_form_script, long_form_storyboard

    if board.quality_profile is not None:
        # Clip-only scenes are filtered below, yet Remotion renders them too (TakeawayCard.tsx).
        # Report every card at once so one rework round fixes them all.
        too_long = []
        missing_reference_text = []
        for scene in board.scenes:
            has_mascot = any(asset.role == "mascot" for asset in scene.visual_assets)
            for shot in scene.shots:
                # Mirror R5ShotScene.tsx preconditions so the storyboard fails here, not in Remotion.
                kinds = {w.kind for w in shot.text_windows}
                where = f"Scene {scene.id} shot {shot.id}: {shot.component}"
                if shot.component == "VnLabSheet" and not kinds & {"lab_sheet", "table"}:
                    too_long.append(f"{where} requires a lab_sheet or table text_window")
                if shot.component == "ReferenceDistribution" and not shot.text_windows:
                    # Shot anchors are unresolved here, so report the containing scene's frame span.
                    scene_end = scene.start_frame + scene.duration_frames
                    missing_reference_text.append(
                        f"Scene {scene.id} shot {shot.id} frame [{scene.start_frame},{scene_end}): "
                        "ReferenceDistribution requires a text_window for its visible label; owner=storyboard_director"
                    )
                if shot.component == "StoryShot" and not (shot.asset_paths or has_mascot):
                    too_long.append(f"{where} requires asset_paths or a scene mascot in visual_assets")
                if shot.component != "TakeawayCard":
                    continue
                if not any(w.kind in {"takeaway", "question"} for w in shot.text_windows):
                    too_long.append(f"Scene {scene.id} shot {shot.id}: TakeawayCard requires a takeaway or "
                                    "question text_window; dùng StoryShot cho shot kể chuyện không chữ")
                for window in shot.text_windows:
                    words = len(window.text.split())
                    if window.kind in {"takeaway", "question"} and not 1 <= words <= R5_MAX_TAKEAWAY_WORDS:
                        too_long.append(f"Scene {scene.id} shot {shot.id}: TakeawayCard {window.kind} needs "
                                        f"1..{R5_MAX_TAKEAWAY_WORDS} words, got {words}")
        if missing_reference_text:
            raise ValueError("R5 storyboard contract failed:\n" + "\n".join(missing_reference_text))
        if too_long:
            raise ValueError("\n".join(too_long))
    board = long_form_storyboard(board)
    script = long_form_script(script)
    if board.quality_profile is None:
        return
    if board.r5_contract is None:
        raise ValueError("r5_v1 requires r5_contract")
    lines = {line.id: line.text for line in script.lines}
    if len(lines) != len(script.lines):
        raise ValueError("duplicate script line ID")
    contract = board.r5_contract
    for question in contract.questions:
        for line_id in (question.hook_line_id, *question.answer_line_ids):
            if line_id not in lines:
                raise ValueError(f"question {question.id}: missing script line {line_id}")
        if " ".join(question.text.split()) not in " ".join(lines[question.hook_line_id].split()):
            raise ValueError(f"question {question.id}: text differs from hook line")
    for block in contract.blocks:
        for line_id in block.line_ids:
            if line_id not in lines:
                raise ValueError(f"block {block.id}: missing script line {line_id}")
    questions = {q.id for q in contract.questions}
    shot_ids: set[str] = set()
    for scene in board.scenes:
        if "\t" in (scene.on_screen_text or ""):
            raise ValueError(f"Scene {scene.id}: R5 forbids tab layout")
        if scene.script_line_id is not None and scene.script_line_id not in lines:
            raise ValueError(f"Scene {scene.id}: missing script line {scene.script_line_id}")
        for shot in scene.shots:
            if shot.id in shot_ids:
                raise ValueError(f"duplicate shot ID {shot.id}")
            shot_ids.add(shot.id)
            if not set(shot.question_ids) <= questions:
                raise ValueError(f"shot {shot.id}: unknown question ID")
            anchors = [shot.start, shot.end]
            for item in (*shot.actions, *shot.text_windows):
                anchors.extend((item.start, item.end))
            for anchor in anchors:
                if anchor.kind == "phrase":
                    if anchor.line_id not in lines:
                        raise ValueError(f"shot {shot.id}: missing script line {anchor.line_id}")
                    if anchor.phrase not in lines[anchor.line_id]:
                        raise ValueError(f"shot {shot.id}: phrase absent from script line")
