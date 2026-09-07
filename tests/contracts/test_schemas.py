import json
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("filename", "has_nested_models"),
    [
        ("evidence.schema.json", False),
        ("author-brief.schema.json", False),
        ("script.schema.json", True),
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
