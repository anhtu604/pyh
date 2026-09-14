import pytest
from pydantic import ValidationError

from healthvideo.domain.storyboard import Storyboard, VisualAssetRef


def test_storyboard_defaults_to_legacy_visual_budget() -> None:
    board = Storyboard.model_validate({"title": "Legacy", "scenes": []})

    assert board.visual_budget_profile == "legacy"
    assert board.visual_budget_override is None
    assert board.model_dump(exclude_defaults=True) == {"title": "Legacy"}


def test_storyboard_rejects_override_with_legacy_profile() -> None:
    with pytest.raises(ValidationError, match="m6_5_v1"):
        Storyboard.model_validate(
            {
                "title": "Sai profile",
                "scenes": [],
                "visual_budget_override": {
                    "rationale": "Override thử nghiệm.",
                    "whiteboard_svg": {"min_percent": 65, "max_percent": 75},
                    "chart_crop": {"min_percent": 15, "max_percent": 25},
                    "ai_clip": {"min_percent": 0, "max_percent": 10},
                },
            }
        )


@pytest.mark.parametrize("duration_frames", [120, 180, 240])
def test_m65_ai_clip_accepts_exact_composition_durations(
    duration_frames: int,
) -> None:
    board = Storyboard.model_validate(
        {
            "title": "AI clip",
            "visual_budget_profile": "m6_5_v1",
            "scenes": [
                {
                    "id": "S01",
                    "start_frame": 0,
                    "duration_frames": duration_frames,
                    "narration": "Minh họa.",
                    "visual": "ai_clip",
                }
            ],
        }
    )

    assert board.scenes[0].duration_frames == duration_frames


def test_m65_ai_clip_rejects_non_provider_duration_but_legacy_keeps_it() -> None:
    scene = {
        "id": "S01",
        "start_frame": 0,
        "duration_frames": 121,
        "narration": "Minh họa.",
        "visual": "ai_clip",
    }
    with pytest.raises(ValidationError, match="120, 180, or 240"):
        Storyboard.model_validate(
            {
                "title": "M6.5",
                "visual_budget_profile": "m6_5_v1",
                "scenes": [scene],
            }
        )

    legacy = Storyboard.model_validate({"title": "Legacy", "scenes": [scene]})
    assert legacy.scenes[0].duration_frames == 121


def test_ai_clip_visual_asset_role_cannot_have_mascot_pose() -> None:
    reference = VisualAssetRef.model_validate(
        {"path": "assets/ai-clips/S01.mp4", "role": "ai_clip"}
    )
    assert reference.pose is None
    with pytest.raises(ValidationError, match="cannot have pose"):
        VisualAssetRef.model_validate(
            {
                "path": "assets/ai-clips/S01.mp4",
                "role": "ai_clip",
                "pose": "welcome",
            }
        )
