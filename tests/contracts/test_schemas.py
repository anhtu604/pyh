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
        ("evidence.schema.json", False),
        ("author-brief.schema.json", False),
        ("script.schema.json", True),
        ("storyboard.schema.json", True),
        ("render-input.schema.json", True),
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
    command = [sys.executable, "tools/export_schemas.py", "--output-dir", str(output_dir)]

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


@pytest.mark.parametrize("filename", ["storyboard.schema.json", "render-input.schema.json"])
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


@pytest.mark.parametrize("filename", ["storyboard.schema.json", "render-input.schema.json"])
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
