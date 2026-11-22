"""Deterministic safe-zone QA checks for 9:16 vertical clips and 16:9 layouts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from healthvideo.qa.script import QAIssue


@dataclass(frozen=True, slots=True)
class SafeZoneSpec:
    """Pixel and ratio bounds protecting platform UI and typography readability."""

    width: int
    height: int
    top_margin_px: int
    bottom_margin_px: int
    right_margin_px: int
    left_margin_px: int
    max_mascot_width_percent: float = 28.0
    max_caption_lines: int = 2
    max_caption_chars_per_line: int = 24
    max_hook_window_seconds: float = 2.0


SAFE_ZONE_9X16 = SafeZoneSpec(
    width=1080,
    height=1920,
    top_margin_px=288,      # 15% of 1920
    bottom_margin_px=422,   # 22% of 1920
    right_margin_px=120,    # TikTok/Shorts/Reels action rail
    left_margin_px=60,
    max_mascot_width_percent=28.0,
    max_caption_lines=2,
    max_caption_chars_per_line=24,
    max_hook_window_seconds=2.0,
)

SAFE_ZONE_16X9 = SafeZoneSpec(
    width=1920,
    height=1080,
    top_margin_px=60,
    bottom_margin_px=60,
    right_margin_px=60,
    left_margin_px=60,
    max_mascot_width_percent=35.0,
    max_caption_lines=2,
    max_caption_chars_per_line=42,
    max_hook_window_seconds=3.0,
)


def _as_mapping(clip: Mapping[str, Any] | BaseModel | None) -> Mapping[str, Any]:
    if clip is None:
        return {}
    if isinstance(clip, BaseModel):
        return clip.model_dump(mode="python")
    return clip


def review_vertical_safe_zone(
    clip: Mapping[str, Any] | BaseModel | None = None,
    *,
    caption_lines: Sequence[str] | None = None,
    caption_box: Mapping[str, int | float] | None = None,
    require_flag: bool = False,
) -> list[QAIssue]:
    """Validate basic 9:16 safe-zone invariants without breaking legacy pre-Style-A clips."""
    data = _as_mapping(clip)
    clip_id = str(data.get("id") or "")
    issues: list[QAIssue] = []

    if (require_flag or "safe_zone_checked" in data) and data.get("safe_zone_checked") is not True:
        issues.append(
            QAIssue(
                code="safe_zone_unchecked",
                line_id=clip_id,
                message="Clip dọc 9:16 chưa xác nhận safe_zone_checked=true.",
                severity="error",
            )
        )

    mascot_width = data.get("mascot_max_width_percent")
    if mascot_width is not None and (
        not isinstance(mascot_width, (int, float))
        or mascot_width <= 0
        or mascot_width > SAFE_ZONE_9X16.max_mascot_width_percent
    ):
        issues.append(
            QAIssue(
                code="mascot_exceeds_safe_width",
                line_id=clip_id,
                message=(
                    f"mascot_max_width_percent={mascot_width} vượt ngưỡng "
                    f"{SAFE_ZONE_9X16.max_mascot_width_percent}% trên khung 9:16."
                ),
                severity="error",
            )
        )

    subtitle_pos = data.get("subtitle_position")
    if subtitle_pos is not None and subtitle_pos != "bottom_center":
        issues.append(
            QAIssue(
                code="invalid_subtitle_position",
                line_id=clip_id,
                message=f"subtitle_position={subtitle_pos!r} phải là 'bottom_center'.",
                severity="error",
            )
        )

    hook_window = data.get("hook_window_seconds")
    if hook_window is not None and (
        not isinstance(hook_window, (int, float))
        or hook_window <= 0
        or hook_window > SAFE_ZONE_9X16.max_hook_window_seconds
    ):
        issues.append(
            QAIssue(
                code="hook_window_exceeded",
                line_id=clip_id,
                message=(
                    f"hook_window_seconds={hook_window} vượt {SAFE_ZONE_9X16.max_hook_window_seconds}s."
                ),
                severity="warning",
            )
        )

    if caption_lines is not None:
        nonblank = [line.strip() for line in caption_lines if line.strip()]
        if len(nonblank) > SAFE_ZONE_9X16.max_caption_lines or any(
            len(line) > SAFE_ZONE_9X16.max_caption_chars_per_line for line in nonblank
        ):
            issues.append(
                QAIssue(
                    code="caption_exceeds_safe_width",
                    line_id=clip_id,
                    message=(
                        f"Phụ đề 9:16 vượt {SAFE_ZONE_9X16.max_caption_lines} dòng "
                        f"hoặc {SAFE_ZONE_9X16.max_caption_chars_per_line} ký tự/dòng."
                    ),
                    severity="warning",
                )
            )

    if caption_box is not None:
        x = float(caption_box.get("x", 0))
        y = float(caption_box.get("y", 0))
        w = float(caption_box.get("width", 0))
        h = float(caption_box.get("height", 0))
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > SAFE_ZONE_9X16.width or y + h > SAFE_ZONE_9X16.height:
            issues.append(
                QAIssue(
                    code="safe_zone_out_of_bounds",
                    line_id=clip_id,
                    message="Hộp phụ đề nằm ngoài khung hình 1080×1920.",
                    severity="error",
                )
            )
        else:
            if y < SAFE_ZONE_9X16.top_margin_px:
                issues.append(
                    QAIssue(
                        code="safe_zone_top_overlap",
                        line_id=clip_id,
                        message=f"Hộp phụ đề y={y:.0f} xâm lấn vùng đỉnh {SAFE_ZONE_9X16.top_margin_px}px.",
                        severity="error",
                    )
                )
            max_bottom = SAFE_ZONE_9X16.height - SAFE_ZONE_9X16.bottom_margin_px
            if y + h > max_bottom:
                issues.append(
                    QAIssue(
                        code="safe_zone_bottom_overlap",
                        line_id=clip_id,
                        message=(
                            f"Hộp phụ đề đáy y+h={y + h:.0f} xâm lấn vùng mô tả/nút đáy (> {max_bottom}px)."
                        ),
                        severity="error",
                    )
                )
            max_right = SAFE_ZONE_9X16.width - SAFE_ZONE_9X16.right_margin_px
            if x + w > max_right:
                issues.append(
                    QAIssue(
                        code="safe_zone_right_rail_overlap",
                        line_id=clip_id,
                        message=(
                            f"Hộp phụ đề phải x+w={x + w:.0f} xâm lấn cột nút phải (> {max_right}px)."
                        ),
                        severity="error",
                    )
                )

    return issues
