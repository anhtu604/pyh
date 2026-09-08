"""Layout of a published production run under ``renders/<input_hash>/``."""

from pathlib import Path

RENDERS_DIRECTORY = "renders"
OUTPUT_NAME = "video.mp4"
RENDER_INPUT_NAME = "render-input.json"
MANIFEST_NAME = "manifest.json"
PRODUCTION_ARTIFACT = "production"
"""Key in ``project.yaml.artifact_hashes`` selecting the active run."""


def renders_directory(project_dir: Path) -> Path:
    return project_dir / RENDERS_DIRECTORY


def production_run_dir(project_dir: Path, input_hash: str) -> Path:
    return renders_directory(project_dir) / input_hash
