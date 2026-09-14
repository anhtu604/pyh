"""Deterministic frame-based visual budget contract for M6.5 storyboards."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from healthvideo.domain.storyboard import Storyboard


class VisualCategory(StrEnum):
    WHITEBOARD_SVG = "whiteboard_svg"
    CHART_CROP = "chart_crop"
    AI_CLIP = "ai_clip"


class PercentRange(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={"x-invariants": {"ordered": "min_percent <= max_percent"}},
    )

    min_percent: int = Field(ge=0, le=100)
    max_percent: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_order(self) -> PercentRange:
        if self.min_percent > self.max_percent:
            raise ValueError("visual budget minimum cannot exceed maximum")
        return self


class VisualBudgetOverride(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "x-invariants": {
                "feasible": "sum(min_percent) <= 100 <= sum(max_percent)"
            }
        },
    )

    rationale: str = Field(json_schema_extra={"pattern": r"\S"})
    whiteboard_svg: PercentRange
    chart_crop: PercentRange
    ai_clip: PercentRange

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("visual budget override rationale must be nonblank")
        return value

    @model_validator(mode="after")
    def validate_feasibility(self) -> VisualBudgetOverride:
        ranges = (self.whiteboard_svg, self.chart_crop, self.ai_clip)
        if sum(item.min_percent for item in ranges) > 100 or sum(
            item.max_percent for item in ranges
        ) < 100:
            raise ValueError("visual budget override ranges are infeasible")
        return self


VisualBudgetProfile = Literal["legacy", "m6_5_v1"]


class VisualBudgetReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: VisualBudgetProfile
    override_active: bool
    total_frames: int = Field(ge=0)
    category_frames: dict[VisualCategory, int]
    category_basis_points: dict[VisualCategory, int]
    effective_bounds: dict[VisualCategory, PercentRange]
    passed: bool


DEFAULT_VISUAL_BOUNDS: Mapping[VisualCategory, PercentRange] = MappingProxyType({
    VisualCategory.WHITEBOARD_SVG: PercentRange(min_percent=65, max_percent=75),
    VisualCategory.CHART_CROP: PercentRange(min_percent=15, max_percent=25),
    VisualCategory.AI_CLIP: PercentRange(min_percent=0, max_percent=10),
})

_VISUAL_CATEGORIES: dict[str, VisualCategory] = {
    "whiteboard": VisualCategory.WHITEBOARD_SVG,
    "brand_outro": VisualCategory.WHITEBOARD_SVG,
    "chart": VisualCategory.CHART_CROP,
    "evidence_highlight": VisualCategory.CHART_CROP,
    "ai_clip": VisualCategory.AI_CLIP,
}


def classify_scene_visual(visual: str) -> VisualCategory:
    try:
        return _VISUAL_CATEGORIES[visual]
    except KeyError as exc:
        raise ValueError(f"unsupported scene visual for M6.5 budget: {visual}") from exc


def _effective_bounds(storyboard: Storyboard) -> dict[VisualCategory, PercentRange]:
    override = storyboard.visual_budget_override
    if override is None:
        return dict(DEFAULT_VISUAL_BOUNDS)
    return {
        VisualCategory.WHITEBOARD_SVG: override.whiteboard_svg,
        VisualCategory.CHART_CROP: override.chart_crop,
        VisualCategory.AI_CLIP: override.ai_clip,
    }


def calculate_visual_budget(storyboard: Storyboard) -> VisualBudgetReport:
    enabled = storyboard.visual_budget_profile == "m6_5_v1"
    category_frames = {category: 0 for category in VisualCategory}
    expected_start = 0
    for scene in storyboard.scenes:
        if enabled and scene.start_frame != expected_start:
            raise ValueError("M6.5 storyboard timeline must be contiguous from frame 0")
        category = classify_scene_visual(scene.visual)
        category_frames[category] += scene.duration_frames
        expected_start = scene.start_frame + scene.duration_frames

    total_frames = expected_start if storyboard.scenes else 0
    if enabled and total_frames <= 0:
        raise ValueError("M6.5 storyboard timeline must contain at least one frame")
    if enabled and sum(category_frames.values()) != total_frames:
        raise ValueError("M6.5 storyboard timeline must be contiguous from frame 0")

    basis_points = {
        category: (10_000 * frames) // total_frames if total_frames else 0
        for category, frames in category_frames.items()
    }
    bounds = _effective_bounds(storyboard)
    within_bounds = all(
        bound.min_percent * total_frames
        <= 100 * category_frames[category]
        <= bound.max_percent * total_frames
        for category, bound in bounds.items()
    )
    return VisualBudgetReport(
        profile=storyboard.visual_budget_profile,
        override_active=storyboard.visual_budget_override is not None,
        total_frames=total_frames,
        category_frames=category_frames,
        category_basis_points=basis_points,
        effective_bounds=bounds,
        passed=True if not enabled else within_bounds,
    )


def validate_visual_budget(storyboard: Storyboard) -> VisualBudgetReport:
    report = calculate_visual_budget(storyboard)
    if storyboard.visual_budget_profile == "m6_5_v1" and not report.passed:
        failures = []
        for category, bound in report.effective_bounds.items():
            frames = report.category_frames[category]
            if not (
                bound.min_percent * report.total_frames
                <= 100 * frames
                <= bound.max_percent * report.total_frames
            ):
                failures.append(
                    f"{category.value}={frames}/{report.total_frames} frames "
                    f"outside {bound.min_percent}-{bound.max_percent}%"
                )
        raise ValueError(f"visual budget failed: {'; '.join(failures)}")
    return report
