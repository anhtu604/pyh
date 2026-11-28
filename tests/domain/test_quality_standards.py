"""Offline R5 contract examples; no medical-content certification."""
import copy
from pathlib import Path

import pytest
from pydantic import ValidationError

from healthvideo.domain.quality_standards import (
    R5_STANDARD_NAME,
    R5Contract,
    R5Shot,
    validate_r5_contract,
)
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.factory_standards import pin_standards


def contract_payload():
    return {
        "questions": [
            {"id": "Q1", "text": "First?", "hook_line_id": "L1", "answer_line_ids": ["L3"]},
            {"id": "Q2", "text": "Second?", "hook_line_id": "L1", "answer_line_ids": ["L3"]},
        ],
        "blocks": [{"id": "B1", "line_ids": ["L2"], "question_ids": ["Q1", "Q2"],
                    "takeaway_line_id": "L2", "professional_update": True}],
    }


def shot_payload():
    return {"id": "SH1", "kind": "mechanism", "tier": "cell", "component": "ZoomChain",
            "asset_paths": ["assets/cell.svg"], "question_ids": ["Q1"],
            "start": {"kind": "scene_start"}, "end": {"kind": "scene_end"},
            "actions": [], "text_windows": []}


def test_contract_validates_real_script_ids_without_rewriting():
    script = Script(title="Synthetic", lines=[{"id": f"L{i}", "text": "First? Second?" if i == 1 else "Synthetic."}
                                               for i in range(1, 4)])
    before = script.model_dump_json()
    board = Storyboard(title="Synthetic", quality_profile="r5_v1", r5_contract=contract_payload())
    validate_r5_contract(board, script)
    assert script.model_dump_json() == before
    bad = contract_payload()
    bad["questions"][0]["hook_line_id"] = "missing"
    with pytest.raises(ValueError, match="missing"):
        validate_r5_contract(board.model_copy(update={"r5_contract": R5Contract(**bad)}), script)


@pytest.mark.parametrize("change", [
    lambda p: p.update(questions=p["questions"][:1]),
    lambda p: p.update(questions=p["questions"] * 3),
    lambda p: p["questions"][0].update(answer_line_ids=[]),
    lambda p: p["questions"][1].update(id="Q1"),
    lambda p: p["blocks"][0].update(question_ids=[]),
    lambda p: p["blocks"][0].update(question_ids=["Q9"]),
    lambda p: p["blocks"][0].update(takeaway_line_id="L9"),
    lambda p: p["blocks"][0].update(professional_update=False),
    lambda p: p["blocks"][0].update(unexpected=True),
    lambda p: p["blocks"][0].update(professional_update="true"),
])
def test_rejects_incomplete_or_unknown_contract_data(change):
    payload = copy.deepcopy(contract_payload())
    change(payload)
    with pytest.raises(ValidationError):
        R5Contract(**payload)


@pytest.mark.parametrize("change", [
    lambda p: p.update(component="../../evil.tsx"),
    lambda p: p.pop("start"),
    lambda p: p.update(extra="no"),
    lambda p: p.update(asset_paths=["../escape.svg"]),
    lambda p: p.update(start={"kind": "phrase", "line_id": "L1"}),
    lambda p: p.update(start={"kind": "scene_start", "phrase": "ignored"}),
    lambda p: p.update(text_windows=[{"kind": "table", "text": "a\tb",
                                      "start": p["start"], "end": p["end"]}]),
])
def test_shot_fails_closed(change):
    payload = shot_payload()
    change(payload)
    with pytest.raises(ValidationError):
        R5Shot(**payload)


def test_versioned_pin_is_opt_in_and_never_rewrites_existing_snapshot(tmp_path):
    project = tmp_path / "project"
    write_yaml_atomic(project / "project.yaml", {"active_revision": "001"})
    target = pin_standards(tmp_path, project, quality_profile="r5_v1")
    assert read_yaml(target)["quality_standard"]["name"] == R5_STANDARD_NAME
    before = target.read_bytes()
    pin_standards(tmp_path, project)
    assert target.read_bytes() == before
    write_yaml_atomic(project / "project.yaml", {"active_revision": "002"})
    legacy = pin_standards(tmp_path, project)
    assert "quality_standard" not in read_yaml(legacy)
    legacy_bytes = legacy.read_bytes()
    pin_standards(tmp_path, project, quality_profile="r5_v1")
    assert legacy.read_bytes() == legacy_bytes


def test_r5_fields_require_explicit_profile():
    with pytest.raises(ValidationError, match="quality_profile"):
        Storyboard(title="Legacy", r5_contract=contract_payload())


def test_legacy_storyboard_fixture_bytes_and_hash():
    import hashlib

    fixture = Path(__file__).parents[1] / "fixtures/golden-project-v2/revisions/001/storyboard/storyboard.yaml"
    payload = Storyboard.model_validate(read_yaml(fixture)).model_dump_json().encode()
    assert len(payload) == 6162
    assert hashlib.sha256(payload).hexdigest() == "e5a6365206b4912c8767a4dbca4755469446c8600f7414361a0660aed82b72e0"


def test_threshold_snapshot_matches_doctor_decisions():
    from healthvideo.domain.quality_standards import r5_standard_snapshot

    snapshot = r5_standard_snapshot()
    assert snapshot["D1"] == {"max_text_percent": 15, "max_text_seconds": 6}
    assert snapshot["D2"] == {
        "story_median_seconds": [2.5, 3.5], "story_p90_max_seconds": 8,
        "mechanism_median_seconds": [8, 20], "action_step_seconds": [3, 6],
        "long_shot_seconds": 20, "long_shot_min_steps": 3, "hard_experimental": True,
    }
    assert snapshot["D4"] == {"script_review_rounds": 2, "visual_review_rounds": 3,
                              "product_review_rounds": 3, "exhausted_policy": "stop_and_present_to_doctor"}
    snapshot["D2"]["story_median_seconds"][0] = 99
    assert r5_standard_snapshot()["D2"]["story_median_seconds"] == [2.5, 3.5]


def test_resolved_intervals_and_report_do_not_certify_unmeasured_quality():
    from healthvideo.domain.quality_standards import QualityReport, ResolvedR5Shot

    payload = shot_payload()
    payload.pop("start")
    payload.pop("end")
    resolved = ResolvedR5Shot(**payload, start_frame=0, end_frame=300)
    assert resolved.component == "ZoomChain"
    with pytest.raises(ValidationError, match="contained"):
        ResolvedR5Shot(**{**payload, "actions": [{"actor": "A", "compartment": "C",
                        "change": "move", "outcome": "arrival", "start_frame": 0, "end_frame": 301}]},
                       start_frame=0, end_frame=300)
    empty = {"count": 0, "median_seconds": None, "p90_seconds": None}
    report = QualityReport(estimated=True, denominator_frames=300, numerator_frames=0,
                           shot_intervals=[], source_intervals=[], text_union_intervals=[],
                           story=empty, mechanism=empty)
    assert report.manual_review == "pending"
    with pytest.raises(ValidationError):
        QualityReport(**{**report.model_dump(), "numerator_frames": 301})
    with pytest.raises(ValidationError, match="N/A"):
        QualityReport(**{**report.model_dump(), "story": {**empty, "median_seconds": 0}})
    for changes in ({"estimated": "false"},
                    {"story": {"count": 1, "median_seconds": "2.5", "p90_seconds": 3.0}},
                    {"story": {"count": 1, "median_seconds": True, "p90_seconds": 3.0}}):
        with pytest.raises(ValidationError):
            QualityReport(**{**report.model_dump(), **changes})


@pytest.mark.parametrize("target", ["question_text", "answer", "block", "shot_question", "anchor_line", "anchor_phrase"])
def test_cross_document_references_fail_closed(target):
    script = Script(title="Synthetic", lines=[{"id": f"L{i}", "text": "First? Second?" if i == 1 else "Synthetic."}
                                               for i in range(1, 4)])
    contract = contract_payload()
    shot = shot_payload()
    if target == "question_text":
        contract["questions"][0]["text"] = "Unapproved rewrite?"
    elif target == "answer":
        contract["questions"][0]["answer_line_ids"] = ["missing"]
    elif target == "block":
        contract["blocks"][0].update(line_ids=["missing"], takeaway_line_id="missing")
    elif target == "shot_question":
        shot["question_ids"] = ["missing"]
    else:
        shot["start"] = {"kind": "phrase", "line_id": "missing" if target == "anchor_line" else "L1",
                         "phrase": "absent"}
    board = Storyboard(title="R5", quality_profile="r5_v1", r5_contract=contract,
                       scenes=[{"id": "S1", "start_frame": 0, "duration_frames": 300,
                                "visual": "whiteboard", "on_screen_text": "Synthetic",
                                "narration": "Synthetic.", "shots": [shot]}])
    with pytest.raises(ValueError):
        validate_r5_contract(board, script)


def test_takeaway_card_word_limit_covers_clip_only_scenes():
    # PYH-001 2026-11-27: clip-only S52 carried a 10-word question; only Remotion caught it.
    script = Script(title="Synthetic", lines=[{"id": f"L{i}", "text": "First? Second?" if i == 1 else "Synthetic."}
                                               for i in range(1, 4)])
    shot = {**shot_payload(), "kind": "story", "tier": None, "component": "TakeawayCard", "asset_paths": [],
            "text_windows": [{"kind": "question", "text": "một hai ba bốn năm sáu bảy tám chín mười",
                              "start": {"kind": "scene_start"}, "end": {"kind": "scene_end"}}]}
    scene = {"id": "S52", "start_frame": 0, "duration_frames": 120, "narration": "Synthetic.",
             "clip_only": "CL01", "visual": "brand_outro", "shots": [shot]}
    other = copy.deepcopy(scene)
    other["id"], other["shots"][0]["id"] = "S53", "SH2"
    board = Storyboard(title="Synthetic", quality_profile="r5_v1", r5_contract=contract_payload(),
                       scenes=[scene, other])
    with pytest.raises(ValueError, match="S52 shot SH1: TakeawayCard question needs 1..8 words, got 10") as error:
        validate_r5_contract(board, script)
    assert "S53 shot SH2" in str(error.value)


def test_takeaway_card_without_text_window_is_rejected():
    # PYH-001 2026-11-27: 98 TakeawayCard shots had no takeaway/question window; Remotion failed at CL01.
    script = Script(title="Synthetic", lines=[{"id": f"L{i}", "text": "First? Second?" if i == 1 else "Synthetic."}
                                               for i in range(1, 4)])
    shot = {**shot_payload(), "kind": "story", "tier": None, "component": "TakeawayCard", "asset_paths": [],
            "text_windows": []}
    board = Storyboard(title="Synthetic", quality_profile="r5_v1", r5_contract=contract_payload(),
                       scenes=[{"id": "S05", "start_frame": 0, "duration_frames": 120, "narration": "Synthetic.",
                                "visual": "whiteboard", "on_screen_text": "Synthetic", "shots": [shot]}])
    with pytest.raises(
        ValueError,
        match="S05 shot SH1: TakeawayCard requires a takeaway or question text_window; dùng StoryShot",
    ):
        validate_r5_contract(board, script)


@pytest.mark.parametrize("has_actions", [False, True])
def test_reference_distribution_without_text_is_rejected(has_actions):
    script = Script(title="Synthetic", lines=[{"id": f"L{i}", "text": "First? Second?" if i == 1 else "Synthetic."}
                                               for i in range(1, 4)])
    shot = {**shot_payload(), "kind": "story", "tier": None, "component": "ReferenceDistribution",
            "asset_paths": [], "text_windows": []}
    if has_actions:
        shot["actions"] = [{
            "actor": "A", "compartment": "C", "change": "shows", "outcome": "lam_ro_y_chinh_1",
            "start": {"kind": "scene_start"}, "end": {"kind": "scene_end"},
        }]
    board = Storyboard(title="Synthetic", quality_profile="r5_v1", r5_contract=contract_payload(),
                       scenes=[{"id": "S06", "start_frame": 0, "duration_frames": 120, "narration": "Synthetic.",
                                "visual": "whiteboard", "on_screen_text": "Synthetic", "shots": [shot]}])
    with pytest.raises(
        ValueError,
        match=r"Scene S06 shot SH1 frame \[0,120\): ReferenceDistribution .*; owner=storyboard_director",
    ):
        validate_r5_contract(board, script)


def test_story_shot_without_text_passes_with_asset_or_mascot_and_rejects_empty():
    script = Script(title="Synthetic", lines=[{"id": f"L{i}", "text": "First? Second?" if i == 1 else "Synthetic."}
                                               for i in range(1, 4)])
    base_shot = {**shot_payload(), "kind": "story", "tier": None, "component": "StoryShot",
                 "actions": [], "text_windows": []}
    # Passes with licensed asset_paths and no text_windows/actions.
    board_with_asset = Storyboard(
        title="Synthetic", quality_profile="r5_v1", r5_contract=contract_payload(),
        scenes=[{"id": "S07", "start_frame": 0, "duration_frames": 120, "narration": "Synthetic.",
                 "visual": "whiteboard", "on_screen_text": "Synthetic",
                 "shots": [{**base_shot, "asset_paths": ["assets/r5/story.svg"]}]}],
    )
    validate_r5_contract(board_with_asset, script)

    # Passes with empty asset_paths when scene has a mascot visual_asset.
    board_with_mascot = Storyboard(
        title="Synthetic", quality_profile="r5_v1", r5_contract=contract_payload(),
        scenes=[{"id": "S08", "start_frame": 0, "duration_frames": 120, "narration": "Synthetic.",
                 "visual": "whiteboard", "on_screen_text": "Synthetic",
                 "visual_assets": [{"path": "assets/brand/explain.png", "role": "mascot", "pose": "explain"}],
                 "shots": [{**base_shot, "asset_paths": []}]}],
    )
    validate_r5_contract(board_with_mascot, script)

    # Rejected when neither asset_paths nor scene mascot is present.
    board_empty = Storyboard(
        title="Synthetic", quality_profile="r5_v1", r5_contract=contract_payload(),
        scenes=[{"id": "S09", "start_frame": 0, "duration_frames": 120, "narration": "Synthetic.",
                 "visual": "whiteboard", "on_screen_text": "Synthetic",
                 "shots": [{**base_shot, "asset_paths": []}]}],
    )
    with pytest.raises(ValueError, match="S09 shot SH1: StoryShot requires asset_paths or a scene mascot"):
        validate_r5_contract(board_empty, script)
