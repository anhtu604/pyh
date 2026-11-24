import pytest
from pydantic import ValidationError

from healthvideo.domain.script import Script, ScriptLine
from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.workflows.citations import resolve_citations


def test_r5_keeps_same_subject_across_deep_sequence_without_legacy_quota():
    from tests.domain.test_quality_standards import contract_payload

    scenes = [Scene(id=f"S{i}", start_frame=i * 90, duration_frames=90,
                    narration="Synthetic.", visual="process_animation",
                    anatomy={"subject": "liver_organ", "state": "normal", "motion": "flow"})
              for i in range(5)]
    with pytest.raises(ValidationError, match="consecutive"):
        Storyboard(title="Legacy", scenes=scenes)
    board = Storyboard(title="R5", scenes=scenes, quality_profile="r5_v1",
                       r5_contract=contract_payload())
    assert len(board.scenes) == 5
    assert board.visual_budget_profile == "explain_first_v1"


def test_storyboard_defaults_to_explain_first_visual_budget() -> None:
    board = Storyboard.model_validate({"title": "Legacy", "scenes": []})

    assert board.visual_budget_profile == "explain_first_v1"
    assert board.visual_budget_override is None
    assert board.model_dump(exclude_defaults=True) == {"title": "Legacy"}


def test_storyboard_rejects_override_with_explain_first_profile() -> None:
    with pytest.raises(ValidationError, match="m6_5_v1"):
        Storyboard.model_validate(
            {
                "title": "Sai profile",
                "scenes": [],
                "visual_budget_override": {
                    "rationale": "Override thử nghiệm.",
                    "whiteboard_svg": {"min_percent": 65, "max_percent": 75},
                    "chart_crop": {"min_percent": 15, "max_percent": 25},
                },
            }
        )


def test_scene_motion_validates_emphasis_text_in_narration() -> None:
    scene = Scene.model_validate(
        {
            "id": "S01",
            "start_frame": 0,
            "duration_frames": 90,
            "narration": "Tăng acid uric máu kéo dài gây lắng đọng tinh thể urat.",
            "on_screen_text": "Tăng acid uric máu",
            "visual": "whiteboard",
            "motion": {
                "emphasis": "marker-underline-title",
                "emphasis_text": "tăng acid uric máu",
                "transition_in": "circle-match-iris",
            },
        }
    )
    assert scene.motion is not None
    assert scene.motion.emphasis == "marker-underline-title"
    assert scene.motion.emphasis_text == "tăng acid uric máu"
    assert scene.motion.transition_in == "circle-match-iris"

    with pytest.raises(ValidationError, match="motion.emphasis_text must be in narration"):
        Scene.model_validate(
            {
                "id": "S01",
                "start_frame": 0,
                "duration_frames": 90,
                "narration": "Tăng acid uric máu kéo dài gây lắng đọng tinh thể urat.",
                "on_screen_text": "Tăng acid uric máu",
                "visual": "whiteboard",
                "motion": {
                    "emphasis": "marker-underline-title",
                    "emphasis_text": "suy thận mạn",
                },
            }
        )

    with pytest.raises(ValidationError, match="emphasis_text requires emphasis"):
        Scene.model_validate(
            {
                "id": "S01",
                "start_frame": 0,
                "duration_frames": 90,
                "narration": "Tăng acid uric máu kéo dài.",
                "on_screen_text": "Tăng acid uric máu",
                "visual": "whiteboard",
                "motion": {
                    "emphasis_text": "tăng acid uric",
                    "transition_in": "circle-match-iris",
                },
            }
        )


def test_stat_gauge_and_kinetic_term_scene_and_ledger_validation() -> None:
    kinetic = Scene.model_validate(
        {
            "id": "S01",
            "start_frame": 0,
            "duration_frames": 90,
            "narration": "Gút cấp là cơn viêm khớp cấp tính do tinh thể muối urat.",
            "visual": "kinetic_term",
            "kinetic_term": {
                "term": "GÚT CẤP",
                "definition": "Viêm khớp cấp tính do tinh thể muối urat.",
            },
        }
    )
    assert kinetic.kinetic_term is not None
    assert kinetic.kinetic_term.variant == "lead-word-zoom-assemble"

    with pytest.raises(ValidationError, match="stat_gauge requires claim_id"):
        Scene.model_validate(
            {
                "id": "S02",
                "start_frame": 90,
                "duration_frames": 90,
                "narration": "Ngưỡng bão hòa urat huyết thanh là 6,8 mg/dL.",
                "visual": "stat_gauge",
                "stat_gauge": {
                    "value": 6.8,
                    "unit": "mg/dL",
                    "label": "Ngưỡng bão hòa urat",
                },
            }
        )

    with pytest.raises(ValidationError):
        Scene.model_validate(
            {
                "id": "S02",
                "start_frame": 90,
                "duration_frames": 90,
                "narration": "Ngưỡng bão hòa urat huyết thanh là 6,8 mg/dL.",
                "claim_id": "C01",
                "visual": "stat_gauge",
                "stat_gauge": {
                    "value": 6.8,
                    "unit": "mg/dL",
                    "label": "Ngưỡng bão hòa urat",
                    "variant": "before-after-slider-scrub",
                },
            }
        )

    gauge_scene = Scene.model_validate(
        {
            "id": "S02",
            "start_frame": 90,
            "duration_frames": 90,
            "narration": "Ngưỡng bão hòa urat huyết thanh là 6,8 mg/dL.",
            "claim_id": "C01",
            "source_marker": "[1]",
            "visual": "stat_gauge",
            "stat_gauge": {
                "value": 6.8,
                "unit": "mg/dL",
                "label": "Ngưỡng bão hòa urat",
            },
        }
    )
    script = Script(
        title="Gút",
        lines=(
            ScriptLine(
                id="L01",
                text="Ngưỡng bão hòa urat huyết thanh là 6,8 mg/dL.",
                claim_id="C01",
                source_marker="[1]",
            ),
        ),
    )
    empty_ledger: dict[str, list[object]] = {"records": [], "claims": []}
    with pytest.raises(ValueError, match="stat_gauge requires a valid claim_id in ledger"):
        resolve_citations(script, empty_ledger, (gauge_scene,))

    valid_ledger = {
        "records": [
            {
                "id": "R01",
                "title": "Urate saturation",
                "authors": ["Richette P"],
                "journal": "Lancet",
                "year": 2020,
                "pmid": "31900001",
                "doi": "10.1016/S0140-6736(19)33048-8",
                "url": "https://pubmed.ncbi.nlm.nih.gov/31900001/",
                "key_findings": "Serum urate saturation threshold is 6.8 mg/dL.",
            }
        ],
        "claims": [
            {
                "id": "C01",
                "text_public": "Ngưỡng bão hòa urat huyết thanh là 6,8 mg/dL.",
                "text_technical": "Serum urate saturation threshold is 6.8 mg/dL at 37 C.",
                "type": "evidence",
                "sources": ["R01"],
            }
        ],
    }
    citations = resolve_citations(script, valid_ledger, (gauge_scene,))
    assert "[1]" in citations
    assert citations["[1]"][0].id == "R01"


def test_style_a_mascot_pose_validation_and_backcompat() -> None:
    from healthvideo.domain.storyboard import validate_style_a_mascot_poses

    def make_scene(
        scene_id: str,
        start: int,
        *,
        chapter_id: str | None = None,
        visual: str = "whiteboard",
        mascot_pose: str | None = None,
        visual_assets: list[dict[str, object]] | None = None,
    ) -> Scene:
        payload: dict[str, object] = {
            "id": scene_id,
            "start_frame": start,
            "duration_frames": 90,
            "narration": f"Lời thoại {scene_id}.",
            "visual": visual,
        }
        if visual == "whiteboard":
            payload["on_screen_text"] = f"Nội dung {scene_id}"
        if chapter_id is not None:
            payload["chapter_id"] = chapter_id
        if mascot_pose is not None:
            payload["mascot_pose"] = mascot_pose
        if visual_assets is not None:
            payload["visual_assets"] = visual_assets
        return Scene.model_validate(payload)

    # Legacy scene without mascot_pose omits the field when dumped.
    legacy = make_scene("S01", 0)
    assert "mascot_pose" not in legacy.model_dump(mode="json")

    # Invalid pose name is rejected by MascotPose enum.
    with pytest.raises(ValidationError):
        make_scene("S01", 0, mascot_pose="dancing")

    # Conflicting mascot_pose and visual_assets pose is rejected.
    with pytest.raises(ValidationError, match="conflicts with mascot visual asset pose"):
        make_scene(
            "S01",
            0,
            mascot_pose="welcome",
            visual_assets=[{"path": "assets/brand/surprised.png", "role": "mascot", "pose": "surprised"}],
        )

    # Missing mascot_pose on hook, chapter start CH02, and outro fails Style A check.
    missing_board = Storyboard(
        title="Style A missing",
        format_profile="youtube_long",
        scenes=(
            make_scene("S01", 0, chapter_id="CH01"),
            make_scene("S02", 90, chapter_id="CH01"),
            make_scene("S03", 180, chapter_id="CH02"),
            make_scene("S04", 270, chapter_id="CH02", visual="brand_outro"),
        ),
    )
    with pytest.raises(ValueError, match="thiếu mascot_pose") as exc_info:
        validate_style_a_mascot_poses(missing_board)
    message = str(exc_info.value)
    assert "S01" in message
    assert "S03" in message
    assert "S04" in message
    assert "S02" not in message

    # Valid Style A storyboard: explicit mascot_pose or mascot visual_assets on hook, chapter starts, outro.
    valid_board = Storyboard(
        title="Style A valid",
        format_profile="youtube_long",
        scenes=(
            make_scene("S01", 0, chapter_id="CH01", mascot_pose="surprised"),
            make_scene("S02", 90, chapter_id="CH01"),
            make_scene(
                "S03",
                180,
                chapter_id="CH02",
                visual_assets=[{"path": "assets/brand/explain.png", "role": "mascot", "pose": "explain"}],
            ),
            make_scene("S04", 270, chapter_id="CH02", visual="brand_outro", mascot_pose="thumbs_up"),
        ),
    )
    validate_style_a_mascot_poses(valid_board)
