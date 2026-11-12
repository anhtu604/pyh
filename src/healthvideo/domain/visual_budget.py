"""Deterministic frame-based visual budget contract for M6.5 storyboards."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from healthvideo.domain.asset_manifest import AssetKind, AssetManifest

if TYPE_CHECKING:
    from healthvideo.domain.storyboard import Storyboard


class VisualCategory(StrEnum):
    WHITEBOARD_SVG = "whiteboard_svg"
    CHART_CROP = "chart_crop"
    MECHANISM = "mechanism"


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

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("visual budget override rationale must be nonblank")
        return value

    @model_validator(mode="after")
    def validate_feasibility(self) -> VisualBudgetOverride:
        ranges = (self.whiteboard_svg, self.chart_crop)
        if sum(item.min_percent for item in ranges) > 100 or sum(
            item.max_percent for item in ranges
        ) < 100:
            raise ValueError("visual budget override ranges are infeasible")
        return self


VisualBudgetProfile = Literal["m6_5_v1", "explain_first_v1"]


class VisualBudgetReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: VisualBudgetProfile
    override_active: bool
    total_frames: int = Field(ge=0)
    category_frames: dict[VisualCategory, int]
    category_basis_points: dict[VisualCategory, int]
    effective_bounds: dict[VisualCategory, PercentRange]
    passed: bool
    mascot_frames: int = Field(default=0, ge=0)
    mascot_basis_points: int = Field(default=0, ge=0)
    warnings: tuple[str, ...] = ()


DEFAULT_VISUAL_BOUNDS: Mapping[VisualCategory, PercentRange] = MappingProxyType({
    VisualCategory.WHITEBOARD_SVG: PercentRange(min_percent=65, max_percent=75),
    VisualCategory.CHART_CROP: PercentRange(min_percent=15, max_percent=25),
})

EXPLAIN_FIRST_VISUAL_BOUNDS: Mapping[VisualCategory, PercentRange] = MappingProxyType({
    VisualCategory.MECHANISM: PercentRange(min_percent=55, max_percent=70),
    VisualCategory.CHART_CROP: PercentRange(min_percent=15, max_percent=25),
    VisualCategory.WHITEBOARD_SVG: PercentRange(min_percent=10, max_percent=15),
})

_VISUAL_CATEGORIES: dict[str, VisualCategory] = {
    "whiteboard": VisualCategory.WHITEBOARD_SVG,
    "brand_outro": VisualCategory.WHITEBOARD_SVG,
    "kinetic_term": VisualCategory.WHITEBOARD_SVG,
    "stat_gauge": VisualCategory.CHART_CROP,
    "chart": VisualCategory.CHART_CROP,
    "evidence_highlight": VisualCategory.CHART_CROP,
    "source_card": VisualCategory.CHART_CROP,
    "anatomy_animation": VisualCategory.MECHANISM,
    "process_animation": VisualCategory.MECHANISM,
    "comparison": VisualCategory.MECHANISM,
    "timelapse": VisualCategory.MECHANISM,
}


def classify_scene_visual(visual: str) -> VisualCategory:
    try:
        return _VISUAL_CATEGORIES[visual]
    except KeyError as exc:
        raise ValueError(f"unsupported scene visual for M6.5 budget: {visual}") from exc


def _effective_bounds(storyboard: Storyboard) -> dict[VisualCategory, PercentRange]:
    if storyboard.visual_budget_profile == "explain_first_v1":
        return dict(EXPLAIN_FIRST_VISUAL_BOUNDS)
    override = storyboard.visual_budget_override
    if override is None:
        return dict(DEFAULT_VISUAL_BOUNDS)
    return {
        VisualCategory.WHITEBOARD_SVG: override.whiteboard_svg,
        VisualCategory.CHART_CROP: override.chart_crop,
    }


def calculate_visual_budget(storyboard: Storyboard, assets: AssetManifest | None = None,
                            *, margin_percent: int = 0) -> VisualBudgetReport:
    bounds = _effective_bounds(storyboard)
    if margin_percent:
        bounds = {category: PercentRange(min_percent=bound.min_percent + margin_percent,
                                          max_percent=bound.max_percent - margin_percent)
                  for category, bound in bounds.items()}
    category_frames = {category: 0 for category in bounds}
    expected_start = 0
    for scene in storyboard.scenes:
        if scene.start_frame != expected_start:
            raise ValueError("M6.5 storyboard timeline must be contiguous from frame 0")
        category = classify_scene_visual(scene.visual)
        category_frames[category] = category_frames.get(category, 0) + scene.duration_frames
        expected_start = scene.start_frame + scene.duration_frames

    total_frames = expected_start if storyboard.scenes else 0
    if total_frames <= 0:
        raise ValueError("M6.5 storyboard timeline must contain at least one frame")
    if sum(category_frames.values()) != total_frames:
        raise ValueError("M6.5 storyboard timeline must be contiguous from frame 0")

    basis_points = {
        category: (10_000 * frames) // total_frames if total_frames else 0
        for category, frames in category_frames.items()
    }
    within_bounds = all(
        bound.min_percent * total_frames
        <= 100 * category_frames[category]
        <= bound.max_percent * total_frames
        for category, bound in bounds.items()
    )
    mascot_frames = sum(
        scene.duration_frames for scene in storyboard.scenes
        if any(asset.role == "mascot" for asset in scene.visual_assets)
    )
    mascot_total = sum(scene.duration_frames for scene in storyboard.scenes)
    warnings = (
        ("Mascot share exceeds 35% of storyboard frames.",)
        if 100 * mascot_frames > 35 * mascot_total else ()
    )
    if storyboard.format_profile == "youtube_long":
        flux_paths = {asset.path for asset in assets.assets
                      if asset.kind is AssetKind.ILLUSTRATION
                      and asset.source == "generated:flux2-klein-4b"} if assets else set()
        illustrated = [scene for scene in storyboard.scenes if scene.visual == "whiteboard"
                       and any(ref.role == "whiteboard" and ref.path in flux_paths
                               for ref in scene.visual_assets)]
        if len(illustrated) < 2:
            warnings += (("youtube_long: use at least 2 whiteboard scenes with FLUX illustrations "
                         "(hook and chapter opener); declare illustration recipes in asset-manifest.yaml. "
                         "Advisory only: FLUX may be omitted when GPU is unavailable."),)
    return VisualBudgetReport(
        mascot_frames=mascot_frames,
        mascot_basis_points=10_000 * mascot_frames // mascot_total if mascot_total else 0,
        warnings=warnings,
        profile=storyboard.visual_budget_profile,
        override_active=storyboard.visual_budget_override is not None,
        total_frames=total_frames,
        category_frames=category_frames,
        category_basis_points=basis_points,
        effective_bounds=bounds,
        passed=within_bounds,
    )


def validate_visual_budget(storyboard: Storyboard, assets: AssetManifest | None = None,
                           *, margin_percent: int = 0) -> VisualBudgetReport:
    report = calculate_visual_budget(storyboard, assets, margin_percent=margin_percent)
    if not report.passed:
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
