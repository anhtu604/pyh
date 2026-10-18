"""Read and atomically write an explainer within an explicit revision root."""

from pathlib import Path

from healthvideo.domain.explainer import Explainer
from healthvideo.storage.files import read_yaml, write_yaml_atomic


def read_explainer(revision_dir: Path) -> Explainer:
    return Explainer.model_validate(read_yaml(revision_dir / "explainer" / "explainer.yaml"))


def write_explainer(revision_dir: Path, explainer: Explainer) -> Path:
    path = revision_dir / "explainer" / "explainer.yaml"
    write_yaml_atomic(path, explainer.model_dump(mode="json"))
    return path
