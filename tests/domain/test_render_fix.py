from copy import deepcopy

import pytest
from pydantic import ValidationError

from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Scene, SourceCard, Storyboard
from healthvideo.domain.visual_budget import VisualCategory, classify_scene_visual
from healthvideo.workflows.citations import resolve_citations

LEDGER = {
    "records": [{"id": "R1", "title": "Synthetic paper", "journal": "Test journal",
                 "year": 2020, "pmid": "123", "doi": "10.0000/test"}],
    "claims": [{"id": "M01", "text_public": "Synthetic claim.",
                "text_technical": "Synthetic claim.", "type": "evidence", "sources": ["R1"]}],
}


def card_scene(**changes):
    return Scene.model_validate({
        "id": "S01", "start_frame": 0, "duration_frames": 90,
        "narration": "A spoken explanation.", "visual": "source_card", "claim_id": "M01",
        "source_marker": "[M01]", "source_card": {
            "source_id": "R1", "title": "Synthetic paper", "journal": "Test journal",
            "year": 2020, "pmid": "123", "doi": "10.0000/test",
            "interpretation": "Synthetic claim.",
        }, **changes,
    })


def script():
    return Script.model_validate({"title": "Test", "lines": [{
        "id": "L01", "text": "A spoken explanation.", "delivery": {"intent": "explain"}, "claim_id": "M01", "source_marker": "[M01]",
    }]})


def test_source_card_matches_ledger_and_counts_in_chart_budget():
    resolve_citations(script(), LEDGER, [card_scene()])
    assert classify_scene_visual("source_card") is VisualCategory.CHART_CROP
    card = SourceCard.from_ledger(LEDGER, "M01", "R1")
    assert card == card_scene().source_card


@pytest.mark.parametrize("field,value", [("title", "Invented"), ("journal", "Other"),
    ("year", 2021), ("doi", None), ("pmid", "456"), ("interpretation", "Invented claim.")])
def test_source_card_rejects_fabricated_metadata(field, value):
    data = card_scene().model_dump()
    data["source_card"][field] = value
    with pytest.raises(ValueError, match="source card.*ledger"):
        resolve_citations(script(), LEDGER, [Scene.model_validate(data)])


def test_source_card_requires_claim_and_marker():
    for changes in ({"claim_id": None}, {"source_marker": None}, {"source_card": None}):
        with pytest.raises(ValidationError, match="source_card requires"):
            card_scene(**changes)


def test_mechanism_run_limit_resets_on_different_visual_or_subject():
    base = {"id": "S1", "start_frame": 0, "duration_frames": 90, "narration": "Text",
            "visual": "process_animation", "anatomy": {
                "subject": "heart", "state": "normal", "motion": "pulse"}}
    scenes = [deepcopy(base) for _ in range(5)]
    Storyboard(title="Four", scenes=scenes[:4])
    with pytest.raises(ValidationError, match="more than 4 consecutive"):
        Storyboard(title="Five", scenes=scenes)
    scenes[2]["visual"] = "comparison"
    Storyboard(title="Varied", scenes=scenes)
    scenes[2]["visual"] = "process_animation"
    scenes[2]["anatomy"]["subject"] = "artery_cross_section"
    Storyboard(title="Varied subject", scenes=scenes)


def test_on_screen_text_limit_and_numbers_need_claim():
    card_scene(on_screen_text="x" * 90)
    with pytest.raises(ValidationError):
        card_scene(on_screen_text="x" * 91)
    # Scene claim/source binding is the same public evidence mapping as narration.
    with pytest.raises(ValueError, match="on_screen_text.*claim"):
        resolve_citations(script(), LEDGER, [Scene(
            id="S1", start_frame=0, duration_frames=90, narration="Text", visual="whiteboard",
            on_screen_text="Giảm 20%",
        )])
    resolve_citations(script(), LEDGER, [card_scene(on_screen_text="Giảm 20%")])
