"""T6 Python contracts; illustrative content only, no network or real rendering."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from healthvideo.domain.asset_manifest import AssetManifest
from healthvideo.domain.explainer import Explainer
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.domain.visual_budget import (
    calculate_visual_budget,
    validate_visual_budget,
)
from healthvideo.render.input import build_render_input
from healthvideo.storage.explainer import write_explainer
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.draft import _validate
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.produce import produce_project
from tests.domain.test_explainer import explainer_data
from tests.helpers import create_v2_project_fixture
from tests.workflows.test_explain_first import _project
from tests.workflows.test_produce import V2_REVIEWED_AT, _write_synthetic_output
from tools.export_schemas import export_schemas

KINDS = ("anatomy_animation", "process_animation", "comparison", "timelapse")
ANATOMY = {
    "subject": "artery_cross_section",
    "state": "diseased",
    "severity": 0.4,
    "motion": "Illustrative motion only",
}


def scene_data(visual: str = "anatomy_animation", **changes: object) -> dict:
    return {
        "id": "S-TEST-01",
        "start_frame": 0,
        "duration_frames": 1350,
        "narration": "Illustration only",
        "visual": visual,
        "anatomy": dict(ANATOMY),
        "explainer_layer_id": "L1",
        **changes,
    }


@pytest.mark.parametrize("kind", KINDS)
def test_mechanism_requires_anatomy_and_carries_props_verbatim(kind: str) -> None:
    scene = Scene.model_validate(scene_data(kind))
    board = Storyboard(title="Illustration", scenes=(scene,))
    payload = build_render_input(board, "audio/narration.wav").model_dump(mode="json")
    assert payload["scenes"][0]["anatomy"] == ANATOMY
    assert payload["scenes"][0]["explainer_layer_id"] == "L1"
    with pytest.raises(ValidationError, match="anatomy"):
        Scene.model_validate(scene_data(kind, anatomy=None))
    data = scene_data(kind)
    del data["anatomy"]
    with pytest.raises(ValidationError, match="anatomy"):
        Scene.model_validate(data)


@pytest.mark.parametrize(
    "changes",
    [
        {"subject": " "},
        {"motion": "\t"},
        {"state": "unknown"},
        {"severity": -0.001},
        {"severity": 1.001},
        {"severity": float("nan")},
    ],
)
def test_invalid_anatomy_rejected(changes: dict) -> None:
    with pytest.raises(ValidationError):
        Scene.model_validate(scene_data(anatomy={**ANATOMY, **changes}))


def test_anatomy_default_severity_and_free_subject() -> None:
    anatomy = {**ANATOMY, "subject": " future organ "}
    del anatomy["severity"]
    scene = Scene.model_validate(scene_data(anatomy=anatomy))
    result = build_render_input(
        Storyboard(title="Test", scenes=(scene,)), "audio/a.wav"
    )
    assert result.model_dump()["scenes"][0]["anatomy"]["subject"] == " future organ "
    assert result.scenes[0].anatomy.severity == 0


@pytest.mark.parametrize("visual", ["whiteboard", "chart", "brand_outro", "ai_clip"])
def test_old_kinds_forbid_anatomy(visual: str) -> None:
    with pytest.raises(ValidationError, match="anatomy"):
        Scene.model_validate(scene_data(visual))


def test_old_scene_serialization_is_byte_identical() -> None:
    # Exact pre-T6 serialized scene, including the existing null-valued fields.
    expected = {
        "schema_version": "1.0",
        "id": "S1",
        "start_frame": 0,
        "duration_frames": 1350,
        "narration": "Illustration",
        "script_line_id": None,
        "claim_id": None,
        "chapter_id": None,
        "source_marker": None,
        "visual": "whiteboard",
        "evidence_highlight": None,
        "visual_assets": [],
    }
    board = Storyboard(title="Test", scenes=(Scene.model_validate(expected),))
    actual = build_render_input(board, "audio/a.wav").model_dump(mode="json")["scenes"][
        0
    ]
    assert json.dumps(actual) == json.dumps(expected)


@pytest.mark.parametrize(
    "filename", ["storyboard.schema.json", "render-input.schema.json"]
)
def test_exported_schema_enforces_anatomy_contract(
    tmp_path: Path, filename: str
) -> None:
    export_schemas(tmp_path)
    validator = Draft202012Validator(json.loads((tmp_path / filename).read_text()))
    payload = {"title": "Test", "audio_file": "audio/a.wav", "scenes": [scene_data()]}
    validator.validate(payload)
    for changes in (
        {"anatomy": None},
        {"visual": "whiteboard"},
        {"anatomy": {**ANATOMY, "severity": 2}},
        {"anatomy": {**ANATOMY, "motion": " "}},
    ):
        bad = deepcopy(payload)
        bad["scenes"][0].update(changes)
        assert list(validator.iter_errors(bad))
    del payload["scenes"][0]["anatomy"]
    assert list(validator.iter_errors(payload))


def budget_board(mechanism: int, evidence: int, text: int, ai: int) -> Storyboard:
    scenes = []
    start = 0
    for visual, frames in zip(
        (*KINDS, "chart", "evidence_highlight", "whiteboard", "brand_outro", "ai_clip"),
        (1, 1, 1, mechanism - 3, evidence - 1, 1, text - 1, 1, ai),
        strict=True,
    ):
        if not frames:
            continue
        data = scene_data(
            visual, id=f"S{len(scenes)}", start_frame=start, duration_frames=frames
        )
        if visual not in KINDS:
            data.pop("anatomy")
        if visual == "evidence_highlight":
            data.update(
                source_marker="[R-TEST-01]",
                evidence_highlight={
                    "image": "assets/test.svg",
                    "quote": "Illustration only",
                    "x": 0,
                    "y": 0,
                    "width": 1,
                    "height": 1,
                },
            )
        scenes.append(Scene.model_validate(data))
        start += frames
    return Storyboard(
        title="Test", scenes=tuple(scenes), visual_budget_profile="explain_first_v1"
    )


@pytest.mark.parametrize(
    "frames", [(550, 250, 150, 50), (700, 150, 150, 0), (650, 250, 100, 0)]
)
def test_explain_budget_inclusive_frame_boundaries(frames: tuple) -> None:
    report = validate_visual_budget(budget_board(*frames))
    assert report.passed
    assert report.total_frames == 1000
    assert sum(report.category_frames.values()) == 1000
    assert report.category_frames == {
        "mechanism": frames[0],
        "chart_crop": frames[1],
        "whiteboard_svg": frames[2],
        "ai_clip": frames[3],
    }


@pytest.mark.parametrize(
    "frames",
    [
        (549, 251, 150, 50),
        (701, 150, 149, 0),
        (600, 251, 149, 0),
        (651, 149, 150, 50),
        (650, 201, 99, 50),
        (600, 249, 151, 0),
        (600, 249, 100, 51),
        (64999, 25001, 10000, 0),
    ],
)
def test_explain_budget_rejects_one_frame_violations(frames: tuple) -> None:
    board = budget_board(*frames)
    assert not calculate_visual_budget(board).passed
    with pytest.raises(ValueError, match="visual budget failed"):
        validate_visual_budget(board)


def test_explain_budget_requires_nonempty_contiguous_timeline() -> None:
    with pytest.raises(ValueError, match="at least one frame"):
        validate_visual_budget(
            Storyboard(title="Test", visual_budget_profile="explain_first_v1")
        )
    board = budget_board(600, 250, 150, 0)
    shifted = board.scenes[0].model_copy(update={"start_frame": 1})
    with pytest.raises(ValueError, match="contiguous"):
        validate_visual_budget(
            board.model_copy(update={"scenes": (shifted, *board.scenes[1:])})
        )


@pytest.mark.parametrize("profile", ["legacy", "explain_first_v1"])
@pytest.mark.parametrize(
    "layer,visual,error",
    [
        ("L-TEST-UNKNOWN", "whiteboard", "unknown explainer layer"),
        ("L1", "whiteboard", "visual.*anatomy_animation"),
        ("L1", "anatomy_animation", None),
        (None, "whiteboard", None),
    ],
)
def test_draft_checks_scene_layer_only_for_explain_projects(
    tmp_path: Path,
    profile: str,
    layer: str | None,
    visual: str,
    error: str | None,
) -> None:
    project = _project(tmp_path, profile, "evidence_ready")
    revision = project / "revisions/001"
    write_explainer(revision, Explainer.model_validate(explainer_data()))
    script = Script.model_validate(
        {
            "title": "Test",
            "format_profile": "explain_first_v1",
            "lines": [
                {
                    "id": "TEST",
                    "text": "Illustration",
                    "delivery": {"intent": "explain"},
                }
            ],
        }
    )
    data = scene_data(visual, explainer_layer_id=layer)
    if visual == "whiteboard":
        data.pop("anatomy")
    board = Storyboard(title="Test", scenes=(Scene.model_validate(data),))
    # Later hook/outro validation is a real sentinel: reaching it proves layer checks passed.
    expected = error if profile == "explain_first_v1" and error else "M6.4"
    with pytest.raises(ValueError, match=expected):
        _validate(
            revision,
            script,
            board,
            AssetManifest.model_validate({"assets": []}),
            project=ProjectManifestV2.model_validate(
                read_yaml(project / "project.yaml")
            ),
        )


@pytest.mark.parametrize("subject", ["artery_cross_section", "heart", "future_organ"])
def test_produce_mechanism_needs_no_generated_asset_and_rejects_unknown_subject(
    tmp_path: Path,
    subject: str,
) -> None:
    project = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    revision = project / "revisions/001"
    board = {
        "title": "Illustration",
        "visual_budget_profile": "explain_first_v1",
        "scenes": [
            scene_data(
                kind,
                id=f"S{i}",
                start_frame=i * 240,
                duration_frames=240,
                anatomy={**ANATOMY, "subject": subject},
            )
            for i, kind in enumerate(KINDS)
        ],
    }
    board["scenes"].extend(
        [
            {
                "id": "E",
                "visual": "chart",
                "start_frame": 960,
                "duration_frames": 400,
                "narration": "Illustration only",
            },
            {
                "id": "T",
                "visual": "whiteboard",
                "start_frame": 1360,
                "duration_frames": 240,
                "narration": "Illustration only",
            },
        ]
    )
    write_yaml_atomic(revision / "storyboard/storyboard.yaml", board)
    write_yaml_atomic(revision / "assets/asset-manifest.yaml", {"assets": []})
    approve_gate(project, GateKind.MEDICAL, reviewer="test", now=V2_REVIEWED_AT)

    def runner(argv: list[str]) -> int:
        _write_synthetic_output(argv)
        return 0

    if subject == "future_organ":
        before = (project / "project.yaml").read_bytes()
        with pytest.raises(
            ValueError, match="future_organ.*artery_cross_section.*heart"
        ):
            produce_project(project, SilentTTS(), runner)
        assert (project / "project.yaml").read_bytes() == before
    else:
        output = produce_project(project, SilentTTS(), runner)
        payload = json.loads(
            (output.parent / "render-input.json").read_text(encoding="utf-8")
        )
        assert [scene["visual"] for scene in payload["scenes"][:4]] == list(KINDS)
        assert all(
            scene["anatomy"]["subject"] == subject for scene in payload["scenes"][:4]
        )
        assert all(scene["visual_assets"] == [] for scene in payload["scenes"])
        qa = json.loads(
            (revision / "reviews/video-qa.json").read_text(encoding="utf-8")
        )
        assert qa["visual_budget"]["profile"] == "explain_first_v1"
        assert qa["visual_budget"]["category_frames"]["mechanism"] == 960
        assert qa["visual_budget"]["passed"] is True
