import pytest
from pydantic import ValidationError

from healthvideo.domain.script import Script, ScriptLine
from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.workflows.citations import resolve_citations


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
