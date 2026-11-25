"""Advisory mascot placement checks; never change storyboard validity or gates."""

from healthvideo.domain.long_form import long_form_storyboard
from healthvideo.domain.script_style import StyleIssue
from healthvideo.domain.storyboard import Storyboard

_DENSE_VISUALS = frozenset({
    "anatomy_animation", "process_animation", "comparison", "timelapse",
    "chart", "stat_gauge", "evidence_highlight", "source_card",
})


def lint_mascot_usage(storyboard: Storyboard) -> list[StyleIssue]:
    """Flag missing long-video branding and scenes needing a layout review.

    Co-presence is a review heuristic, not proof of geometric overlap.
    Use existing style-lint fields so all submission/review consumers can show it.
    """
    storyboard = long_form_storyboard(storyboard)
    scenes = [scene for scene in storyboard.scenes
              if any(asset.role == "mascot" for asset in scene.visual_assets)]
    issues = []
    if storyboard.format_profile == "youtube_long" and storyboard.scenes and not scenes:
        issues.append(StyleIssue(
            storyboard.scenes[0].id,
            "mascot_missing",
            "Video dài chưa có mascot; cân nhắc hook, tóm ý hoặc CTA/outro.",
            "warn",
        ))
    for scene in scenes:
        if (scene.anatomy is not None or scene.visual in _DENSE_VISUALS
                or any(asset.role == "chart" for asset in scene.visual_assets)):
            issues.append(StyleIssue(
                scene.id, "mascot_dense_scene",
                f"{scene.id}: mascot cùng anatomy/chart/nguồn; kiểm bố cục 16:9 và 9:16, "
                "không che giải phẫu, biểu đồ, phụ đề hoặc thẻ nguồn.",
                "warn",
            ))
    return issues
