import pytest
from pydantic import ValidationError

from healthvideo.domain.storyboard import Storyboard


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

