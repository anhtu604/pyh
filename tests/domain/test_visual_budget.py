from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from healthvideo.domain.storyboard import Scene, Storyboard, VisualAssetRef
from healthvideo.domain.visual_budget import (
    PercentRange,
    VisualBudgetOverride,
    VisualCategory,
    calculate_visual_budget,
    classify_scene_visual,
    validate_visual_budget,
)


def storyboard(
    durations: Sequence[tuple[str, int]],
    *,
    profile: str = "m6_5_v1",
    override: VisualBudgetOverride | None = None,
) -> Storyboard:
    start = 0
    scenes = []
    for index, (visual, duration) in enumerate(durations, start=1):
        scenes.append(
            Scene(
                id=f"S{index:02d}",
                start_frame=start,
                duration_frames=duration,
                narration=f"Cảnh {index}",
                visual=visual,
            )
        )
        start += duration
    return Storyboard(
        title="Ngân sách visual",
        scenes=tuple(scenes),
        visual_budget_profile=profile,
        visual_budget_override=override,
    )


@pytest.mark.parametrize(
    ("visual", "category"),
    [
        ("whiteboard", VisualCategory.WHITEBOARD_SVG),
        ("brand_outro", VisualCategory.WHITEBOARD_SVG),
        ("chart", VisualCategory.CHART_CROP),
        ("evidence_highlight", VisualCategory.CHART_CROP),
        ("ai_clip", VisualCategory.AI_CLIP),
    ],
)
def test_classifies_every_current_primary_visual(
    visual: str, category: VisualCategory
) -> None:
    assert classify_scene_visual(visual) is category


def test_unknown_primary_visual_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported scene visual"):
        classify_scene_visual("future_visual")


@pytest.mark.parametrize(
    "durations",
    [
        (("whiteboard", 65), ("chart", 25), ("ai_clip", 10)),
        (("brand_outro", 75), ("chart", 15), ("ai_clip", 10)),
        (("whiteboard", 75), ("chart", 25)),
    ],
)
def test_default_inclusive_boundaries_pass(
    durations: Sequence[tuple[str, int]],
) -> None:
    report = validate_visual_budget(storyboard(durations))

    assert report.passed is True
    assert sum(report.category_frames.values()) == report.total_frames == 100


@pytest.mark.parametrize(
    "durations",
    [
        (("whiteboard", 64), ("chart", 26), ("ai_clip", 10)),
        (("whiteboard", 76), ("chart", 14), ("ai_clip", 10)),
        (("whiteboard", 70), ("chart", 19), ("ai_clip", 11)),
    ],
)
def test_one_frame_boundary_violation_fails_without_rounding(
    durations: Sequence[tuple[str, int]],
) -> None:
    with pytest.raises(ValueError, match="visual budget failed"):
        validate_visual_budget(storyboard(durations))


def test_cross_multiplication_rejects_sub_basis_boundary_violation() -> None:
    board = storyboard(
        (("whiteboard", 6500), ("chart", 2501), ("ai_clip", 1000))
    )

    report = calculate_visual_budget(board)

    assert report.category_basis_points[VisualCategory.CHART_CROP] == 2500
    assert report.passed is False
    with pytest.raises(ValueError, match="visual budget failed"):
        validate_visual_budget(board)


def test_report_uses_canonical_floor_basis_points_and_ignores_overlays() -> None:
    board = storyboard(
        (("whiteboard", 2), ("chart", 1)),
        override=VisualBudgetOverride(
            rationale="Ba frame kiểm tra phép chia nguyên.",
            whiteboard_svg=PercentRange(min_percent=60, max_percent=70),
            chart_crop=PercentRange(min_percent=30, max_percent=40),
            ai_clip=PercentRange(min_percent=0, max_percent=0),
        ),
    )
    first = board.scenes[0].model_copy(
        update={
            "visual_assets": (
                VisualAssetRef(path="assets/overlay.svg", role="whiteboard"),
            )
        }
    )
    board = board.model_copy(update={"scenes": (first, *board.scenes[1:])})

    report = validate_visual_budget(board)

    assert report.category_frames == {
        VisualCategory.WHITEBOARD_SVG: 2,
        VisualCategory.CHART_CROP: 1,
        VisualCategory.AI_CLIP: 0,
    }
    assert report.category_basis_points == {
        VisualCategory.WHITEBOARD_SVG: 6666,
        VisualCategory.CHART_CROP: 3333,
        VisualCategory.AI_CLIP: 0,
    }


def test_legacy_storyboard_bypasses_budget_enforcement() -> None:
    board = storyboard((("whiteboard", 100),), profile="legacy")

    report = validate_visual_budget(board)

    assert report.profile == "legacy"
    assert report.passed is True


def test_valid_override_replaces_all_default_ranges() -> None:
    override = VisualBudgetOverride(
        rationale="Cần nhiều chart cho dữ liệu đã khai báo.",
        whiteboard_svg=PercentRange(min_percent=50, max_percent=60),
        chart_crop=PercentRange(min_percent=40, max_percent=50),
        ai_clip=PercentRange(min_percent=0, max_percent=0),
    )
    report = validate_visual_budget(
        storyboard((("whiteboard", 55), ("chart", 45)), override=override)
    )

    assert report.override_active is True
    assert report.effective_bounds[VisualCategory.CHART_CROP] == PercentRange(
        min_percent=40, max_percent=50
    )


def test_enabled_timeline_must_be_complete_and_contiguous() -> None:
    board = storyboard((("whiteboard", 75), ("chart", 25)))
    second = board.scenes[1].model_copy(update={"start_frame": 76})
    board = board.model_copy(update={"scenes": (board.scenes[0], second)})

    with pytest.raises(ValueError, match="contiguous"):
        calculate_visual_budget(board)


@pytest.mark.parametrize(
    "override",
    [
        {
            "rationale": " ",
            "whiteboard_svg": {"min_percent": 65, "max_percent": 75},
            "chart_crop": {"min_percent": 15, "max_percent": 25},
            "ai_clip": {"min_percent": 0, "max_percent": 10},
        },
        {
            "rationale": "Sai thứ tự.",
            "whiteboard_svg": {"min_percent": 76, "max_percent": 75},
            "chart_crop": {"min_percent": 15, "max_percent": 25},
            "ai_clip": {"min_percent": 0, "max_percent": 10},
        },
        {
            "rationale": "Ngoài khoảng phần trăm.",
            "whiteboard_svg": {"min_percent": -1, "max_percent": 75},
            "chart_crop": {"min_percent": 15, "max_percent": 25},
            "ai_clip": {"min_percent": 0, "max_percent": 101},
        },
        {
            "rationale": "Không khả thi.",
            "whiteboard_svg": {"min_percent": 80, "max_percent": 90},
            "chart_crop": {"min_percent": 30, "max_percent": 40},
            "ai_clip": {"min_percent": 0, "max_percent": 10},
        },
        {
            "rationale": "Tổng maximum không đủ.",
            "whiteboard_svg": {"min_percent": 20, "max_percent": 30},
            "chart_crop": {"min_percent": 20, "max_percent": 30},
            "ai_clip": {"min_percent": 0, "max_percent": 10},
        },
    ],
)
def test_override_rejects_blank_invalid_or_infeasible_ranges(
    override: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        VisualBudgetOverride.model_validate(override)
