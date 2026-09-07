import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from healthvideo.domain.author import AuthorBrief
from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.render.input import RenderInput

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "schemas"
SCHEMAS: dict[str, type[BaseModel]] = {
    "evidence.schema.json": EvidenceClaim,
    "author-brief.schema.json": AuthorBrief,
    "script.schema.json": Script,
    "storyboard.schema.json": Storyboard,
    "render-input.schema.json": RenderInput,
}


def export_schemas(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        schema = model.model_json_schema()
        schema["$schema"] = JSON_SCHEMA_DIALECT
        serialized = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True)
        (output_dir / filename).write_text(f"{serialized}\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export Pydantic JSON schemas.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    export_schemas(args.output_dir)


if __name__ == "__main__":
    main()
