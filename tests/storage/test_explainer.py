from pathlib import Path

import pytest
from pydantic import ValidationError

from healthvideo.domain.explainer import Explainer
from healthvideo.storage.explainer import read_explainer, write_explainer
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from tests.domain.test_explainer import explainer_data


def test_explainer_yaml_roundtrip_and_replacement(tmp_path: Path) -> None:
    revision_dir = tmp_path / "revisions" / "001"
    data = explainer_data()
    data["topic_question"] = "Câu hỏi minh họa"
    explainer = Explainer.model_validate(data)
    path = write_explainer(revision_dir, explainer)
    assert path == revision_dir / "explainer" / "explainer.yaml"
    assert read_yaml(path)["layers"][0]["claim_ids"] == ["R-TEST-01"]
    assert "Câu hỏi minh họa" in path.read_text(encoding="utf-8")
    assert read_explainer(revision_dir) == explainer
    data["topic_question"] = "Updated illustrative question"
    updated = Explainer.model_validate(data)
    write_explainer(revision_dir, updated)
    assert read_explainer(revision_dir).topic_question == "Updated illustrative question"
    assert list(path.parent.iterdir()) == [path]


def test_read_explainer_validates_yaml(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_explainer(tmp_path)
    data = explainer_data()
    data["layers"] = []
    write_yaml_atomic(tmp_path / "explainer" / "explainer.yaml", data)
    with pytest.raises(ValidationError):
        read_explainer(tmp_path)
