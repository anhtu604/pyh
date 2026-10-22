import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("filename", "has_nested_models"),
    [
        ("brand.schema.json", True),
        ("posts.schema.json", True),
        ("project-v2.schema.json", True),
        ("pronunciation.schema.json", True),
        ("topic-card.schema.json", True),
        ("evidence.schema.json", True),
        ("explainer.schema.json", True),
        ("script.schema.json", True),
        ("storyboard.schema.json", True),
        ("render-input.schema.json", True),
        ("stage-manifest.schema.json", True),
        ("asset-manifest.schema.json", True),
        ("license-ledger.schema.json", True),
        ("outline.schema.json", True),
        ("clip-plan.schema.json", True),
    ],
)
def test_exported_schema_has_versioned_contract(
    tmp_path: Path, filename: str, has_nested_models: bool
) -> None:
    output_dir = tmp_path / "schemas"
    subprocess.run(
        [sys.executable, "tools/export_schemas.py", "--output-dir", str(output_dir)],
        check=True,
        cwd=REPOSITORY_ROOT,
    )

    schema = json.loads((output_dir / filename).read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "properties" in schema
    assert "schema_version" in schema["properties"]
    if has_nested_models:
        assert "$defs" in schema
    else:
        assert "$defs" not in schema


def test_schema_export_is_deterministic(tmp_path: Path) -> None:
    output_dir = tmp_path / "schemas"
    command = [
        sys.executable,
        "tools/export_schemas.py",
        "--output-dir",
        str(output_dir),
    ]

    subprocess.run(command, check=True, cwd=REPOSITORY_ROOT)
    first = {
        path.name: path.read_bytes()
        for path in sorted(output_dir.glob("*.schema.json"))
    }
    subprocess.run(command, check=True, cwd=REPOSITORY_ROOT)
    second = {
        path.name: path.read_bytes()
        for path in sorted(output_dir.glob("*.schema.json"))
    }

    assert second == first


@pytest.mark.parametrize(
    "filename", ["storyboard.schema.json", "render-input.schema.json"]
)
def test_exported_storyboard_contract_rejects_runtime_invalid_values(
    tmp_path: Path, filename: str
) -> None:
    output_dir = tmp_path / "schemas"
    subprocess.run(
        [sys.executable, "tools/export_schemas.py", "--output-dir", str(output_dir)],
        check=True,
        cwd=REPOSITORY_ROOT,
    )
    schema = json.loads((output_dir / filename).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    valid = {
        "title": "Muối",
        "audio_file": "audio/narration.wav",
        "scenes": [
            {
                "id": "S01",
                "start_frame": 0,
                "duration_frames": 1350,
                "narration": "Một nghiên cứu cho thấy giảm muối có thể hạ huyết áp.",
                "source_marker": "[1]",
                "visual": "evidence_highlight",
                "evidence_highlight": {
                    "image": "assets/paper-r01.png",
                    "quote": "giảm huyết áp tâm thu",
                    "x": 0.12,
                    "y": 0.42,
                    "width": 0.64,
                    "height": 0.08,
                },
            }
        ],
    }

    assert validator.is_valid(valid)

    invalid_payloads: list[dict[str, object]] = []
    for field, value in (("start_frame", -1), ("duration_frames", 0)):
        payload = deepcopy(valid)
        payload["scenes"][0][field] = value
        invalid_payloads.append(payload)
    for field, value in (("source_marker", " "), ("visual", "unsupported")):
        payload = deepcopy(valid)
        payload["scenes"][0][field] = value
        invalid_payloads.append(payload)
    for field, value in (
        ("image", " "),
        ("quote", " "),
        ("x", -0.01),
        ("y", -0.01),
        ("width", 1.01),
        ("height", 1.01),
    ):
        payload = deepcopy(valid)
        payload["scenes"][0]["evidence_highlight"][field] = value
        invalid_payloads.append(payload)
    for field in ("source_marker", "evidence_highlight"):
        payload = deepcopy(valid)
        del payload["scenes"][0][field]
        invalid_payloads.append(payload)
    payload = deepcopy(valid)
    payload["scenes"][0]["evidence_highlight"] = None
    invalid_payloads.append(payload)

    for invalid in invalid_payloads:
        assert not validator.is_valid(invalid)


@pytest.mark.parametrize(
    "filename", ["storyboard.schema.json", "render-input.schema.json"]
)
def test_exported_storyboard_contract_announces_cross_field_invariants(
    tmp_path: Path, filename: str
) -> None:
    output_dir = tmp_path / "schemas"
    subprocess.run(
        [sys.executable, "tools/export_schemas.py", "--output-dir", str(output_dir)],
        check=True,
        cwd=REPOSITORY_ROOT,
    )
    schema = json.loads((output_dir / filename).read_text(encoding="utf-8"))

    assert schema["$defs"]["EvidenceHighlight"]["x-invariants"] == {
        "x_plus_width": "x + width <= 1",
        "y_plus_height": "y + height <= 1",
    }


def test_storyboard_schema_adds_optional_visual_budget_contract(tmp_path: Path) -> None:
    output_dir = tmp_path / "schemas"
    subprocess.run(
        [sys.executable, "tools/export_schemas.py", "--output-dir", str(output_dir)],
        check=True,
        cwd=REPOSITORY_ROOT,
    )
    schema = json.loads(
        (output_dir / "storyboard.schema.json").read_text(encoding="utf-8")
    )

    assert schema["properties"]["visual_budget_profile"]["default"] == "explain_first_v1"
    assert schema["properties"]["visual_budget_profile"]["enum"] == [
        "m6_5_v1",
        "explain_first_v1",
    ]
    assert schema["properties"]["visual_budget_override"]["default"] is None
    assert schema["$defs"]["PercentRange"]["properties"]["min_percent"][
        "minimum"
    ] == 0
    assert schema["$defs"]["PercentRange"]["properties"]["max_percent"][
        "maximum"
    ] == 100
    assert schema["$defs"]["PercentRange"]["x-invariants"] == {
        "ordered": "min_percent <= max_percent"
    }
    assert schema["$defs"]["VisualBudgetOverride"]["x-invariants"] == {
        "feasible": "sum(min_percent) <= 100 <= sum(max_percent)"
    }


def test_exported_chart_role_and_render_profile_are_additive(tmp_path: Path) -> None:
    output_dir = tmp_path / "schemas"
    subprocess.run(
        [sys.executable, "tools/export_schemas.py", "--output-dir", str(output_dir)],
        check=True,
        cwd=REPOSITORY_ROOT,
    )
    storyboard = json.loads(
        (output_dir / "storyboard.schema.json").read_text(encoding="utf-8")
    )
    asset_manifest = json.loads(
        (output_dir / "asset-manifest.schema.json").read_text(encoding="utf-8")
    )
    render_input = json.loads(
        (output_dir / "render-input.schema.json").read_text(encoding="utf-8")
    )

    assert "chart" in storyboard["$defs"]["VisualAssetRef"]["properties"]["role"][
        "enum"
    ]
    assert "chart" in asset_manifest["$defs"]["AssetRecord"]["properties"][
        "storyboard_role"
    ]["anyOf"][0]["enum"]
    assert render_input["properties"]["visual_budget_profile"]["default"] == "explain_first_v1"
    assert render_input["x-invariants"]["m6_5_chart_ref"] == (
        "m6_5_v1 chart scenes contain exactly one role=chart asset"
    )


def test_removed_ai_clip_kinds_rejected() -> None:
    from pydantic import ValidationError

    from healthvideo.domain.asset_manifest import AssetRecord
    from healthvideo.domain.storyboard import Storyboard, VisualAssetRef

    with pytest.raises(ValidationError, match="visual"):
        Storyboard.model_validate({
            "title": "Removed scene",
            "scenes": [{"id": "S01", "start_frame": 0, "duration_frames": 120,
                        "narration": "Illustration", "visual": "ai_clip"}],
        })
    with pytest.raises(ValidationError, match="kind"):
        AssetRecord.model_validate({
            "path": "assets/removed.mp4", "kind": "ai_clip", "semantic": False,
            "classification_reason": "Illustration", "sha256": "a" * 64,
            "source": "synthetic", "license": "own", "creator": "test",
            "revision": "001", "rights_required": True,
            "ai_provenance": {
                "provider": "google_vertex_ai", "model": "veo-3.1-fast-generate-001",
                "prompt": "Illustration", "request_sha256": "b" * 64,
                "generated_at": "2026-10-22T00:00:00Z", "duration_ms": 4000,
                "mime_type": "video/mp4", "container": "mp4",
                "source_fps": 24, "width": 1080, "height": 1920,
                "source_frame_count": 96,
                "output_sha256": "a" * 64,
            },
        })
    with pytest.raises(ValidationError, match="role"):
        VisualAssetRef(path="assets/removed.mp4", role="ai_clip")


@pytest.mark.parametrize("filename", [
    "storyboard.schema.json", "render-input.schema.json", "asset-manifest.schema.json",
])
def test_exported_contracts_exclude_removed_ai_clip_kinds(tmp_path: Path, filename: str) -> None:
    from tools.export_schemas import export_schemas

    export_schemas(tmp_path)
    schema = json.loads((tmp_path / filename).read_text(encoding="utf-8"))
    assert "ai_clip" not in json.dumps(schema)
    assert "AIClipProvenance" not in schema["$defs"]
    # Generated artifacts in Git must carry the same current contract.
    assert schema == json.loads((REPOSITORY_ROOT / "schemas" / filename).read_text(encoding="utf-8"))
