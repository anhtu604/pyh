"""Synthetic T6c boundary fixtures; no medical assertions or network."""

import pytest
from pydantic import ValidationError

from healthvideo.domain.brand import load_brand_profile
from healthvideo.domain.clip_plan import ClipPlan, validate_clip_plan
from healthvideo.domain.format_profile import FORMAT_SPECS
from healthvideo.domain.outline import Outline
from healthvideo.domain.storyboard import Scene, Storyboard, VisualAssetRef
from healthvideo.domain.visual_budget import calculate_visual_budget
from healthvideo.workflows.long_form import clip_render_input


def board(frames: int, mascot_frames: int = 0) -> Storyboard:
    scenes = []
    if mascot_frames:
        scenes.append(
            Scene(
                id="S01",
                start_frame=0,
                duration_frames=mascot_frames,
                narration="Synthetic fixture",
                visual="whiteboard",
                chapter_id="CH01",
                visual_assets=(
                    VisualAssetRef(
                        path="assets/test.svg", role="mascot", pose="welcome"
                    ),
                ),
            )
        )
    if frames > mascot_frames:
        scenes.append(
            Scene(
                id="S02",
                start_frame=mascot_frames,
                duration_frames=frames - mascot_frames,
                narration="Synthetic fixture",
                visual="whiteboard",
                chapter_id="CH01",
            )
        )
    return Storyboard(
        title="Synthetic fixture", format_profile="youtube_long", scenes=tuple(scenes)
    )


@pytest.mark.parametrize(
    "frames,valid", [(1709, False), (1710, True), (5310, True), (5311, False)]
)
def test_clip_final_duration_includes_card(frames, valid):
    source = board(frames)
    plan = ClipPlan(
        clips=(
            {
                "id": "CL01",
                "title": "Test",
                "first_scene_id": "S02",
                "last_scene_id": "S02",
            },
        )
    )
    if valid:
        assert validate_clip_plan(plan, source, {})["CL01"] == source.scenes
        result = clip_render_input(source, source.scenes, "audio/test.wav")
        assert result.youtube_cta.duration_frames == 90
        assert len(result.scenes) == 1
    else:
        with pytest.raises(ValueError, match="duration"):
            validate_clip_plan(plan, source, {})
        with pytest.raises(ValueError, match="duration"):
            clip_render_input(source, source.scenes, "audio/test.wav")


def test_outline_four_chapters_ten_minutes():
    assert (
        len(
            Outline(
                title="Test",
                chapters=tuple(
                    {
                        "id": f"CH{i:02d}",
                        "title": "Test",
                        "goal": "Test",
                        "target_seconds": 150,
                    }
                    for i in range(1, 5)
                ),
            ).chapters
        )
        == 4
    )
    assert FORMAT_SPECS["vertical_clip"].max_frames == 5400


def test_brand_cta_default_and_nonblank():
    from pathlib import Path

    brand = load_brand_profile(Path("profiles/brand.vi.yaml"))
    assert brand.cta.youtube_full_video == "Xem bản đầy đủ trên YouTube"
    for text in ("", "  ", "\n"):
        with pytest.raises(ValidationError):
            type(brand).model_validate(
                {**brand.model_dump(), "cta": {"youtube_full_video": text}}
            )


@pytest.mark.parametrize("frames,warns", [(350, False), (351, True), (1000, True)])
def test_mascot_share_is_frame_weighted_warning(frames, warns):
    report = calculate_visual_budget(board(1000, frames))
    assert report.mascot_frames == frames
    assert bool(report.warnings) is warns
    assert report.passed  # Legacy visual budget remains nonblocking.


def test_clip_uses_custom_brand_invitation():
    from pathlib import Path

    brand = load_brand_profile(Path("profiles/brand.vi.yaml"))
    custom = type(brand).model_validate(
        {
            **brand.model_dump(),
            "cta": {"youtube_full_video": "Custom YouTube invitation"},
        }
    )
    source = board(1800)
    assert (
        clip_render_input(
            source,
            source.scenes,
            "audio/test.wav",
            brand=custom,
        ).youtube_cta.text
        == "Custom YouTube invitation"
    )
    old_profile = brand.model_dump()
    old_profile.pop("cta")
    assert type(brand).model_validate(old_profile).cta == brand.cta
