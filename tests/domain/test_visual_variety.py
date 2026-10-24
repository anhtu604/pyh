from copy import deepcopy

import pytest
from pydantic import ValidationError

from healthvideo.domain.asset_manifest import AssetManifest
from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.domain.visual_budget import validate_visual_budget
from tests.test_flux import illustration_record


def mechanism_scenes(count):
    return [{"id": f"S{i}", "start_frame": i * 90, "duration_frames": 90,
             "chapter_id": "CH01", "narration": "Synthetic explanation",
             "visual": "comparison" if i % 2 else "process_animation",
             "anatomy": {"subject": "heart", "state": "normal", "motion": "pulse"}}
            for i in range(count)]


def test_long_video_requires_four_subjects_and_clip_requires_two():
    scenes = mechanism_scenes(6)
    with pytest.raises(ValidationError, match="at least 4 anatomy.subject.*liver_lobule"):
        Storyboard(title="Synthetic", format_profile="youtube_long", scenes=scenes)
    for scene, subject in zip(scenes[-3:], ("liver_lobule", "liver_organ", "artery_cross_section"), strict=True):
        scene["anatomy"]["subject"] = subject
    Storyboard(title="Synthetic", format_profile="youtube_long", scenes=scenes)
    Storyboard(title="Synthetic", format_profile="youtube_long", scenes=scenes[:3])
    with pytest.raises(ValidationError, match="at least 2 anatomy.subject"):
        Storyboard(title="Synthetic", scenes=mechanism_scenes(6))
    Storyboard(title="Synthetic", scenes=scenes)


@pytest.mark.parametrize("text", [None, "", "   "])
def test_whiteboard_needs_visible_text_or_whiteboard_asset(text):
    scene = {"id": "EMPTY", "start_frame": 0, "duration_frames": 90,
             "narration": "Spoken words do not fill the board", "visual": "whiteboard",
             "on_screen_text": text}
    with pytest.raises(ValidationError, match="EMPTY.*whiteboard.*on_screen_text"):
        Scene.model_validate(scene)
    decorated = deepcopy(scene)
    decorated["visual_assets"] = [{"path": "mascot.svg", "role": "mascot", "pose": "explain"}]
    with pytest.raises(ValidationError, match="whiteboard"):
        Scene.model_validate(decorated)
    scene["visual_assets"] = [{"path": "illustration.png", "role": "whiteboard"}]
    Scene.model_validate(scene)

    scene["visual_assets"] = []
    scene["on_screen_text"] = "Visible idea"
    Scene.model_validate(scene)
    scene.update(visual="brand_outro", on_screen_text=None)
    Scene.model_validate(scene)


def test_flux_warning_counts_only_referenced_manifest_illustrations_and_never_blocks():
    recipe = illustration_record()
    other = {**recipe, "path": "assets/illustrations/chapter.png", "seed": 43}
    assets = AssetManifest(assets=[recipe, other])
    scenes = [{"id": f"W{i}", "start_frame": i * 90, "duration_frames": 90,
               "chapter_id": f"CH0{i + 1}", "narration": "Synthetic", "visual": "whiteboard",
               "on_screen_text": "Synthetic illustration"} for i in range(2)]
    # Valid 65/20/15 frame budget: the FLUX advisory alone must never block.
    scenes.extend([
        {"id": "M", "start_frame": 180, "duration_frames": 780, "chapter_id": "CH03",
         "narration": "Synthetic", "visual": "process_animation",
         "anatomy": {"subject": "heart", "state": "normal", "motion": "pulse"}},
        {"id": "C", "start_frame": 960, "duration_frames": 240, "chapter_id": "CH04",
         "narration": "Synthetic", "visual": "chart"},
    ])

    def report():
        board = Storyboard(title="Synthetic", format_profile="youtube_long", scenes=scenes)
        result = validate_visual_budget(board, assets)
        assert result.passed
        return result

    assert any("FLUX" in w for w in report().warnings)
    scenes[0]["visual_assets"] = [{"path": recipe["path"], "role": "whiteboard"}]
    assert any("FLUX" in w for w in report().warnings)
    scenes[1]["visual_assets"] = [{"path": other["path"], "role": "whiteboard"}]
    assert not any("FLUX" in w for w in report().warnings)
    scenes[1]["visual_assets"][0]["path"] = "ordinary.png"
    assert any("FLUX" in w for w in report().warnings)
