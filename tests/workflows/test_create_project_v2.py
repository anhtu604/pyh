from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.storage.files import read_yaml
from healthvideo.workflows.create_project_v2 import create_project_v2

FROZEN_NOW = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)


def test_create_project_v2_starts_at_idea_with_revision_001(tmp_path) -> None:
    """Creating a v2 project must publish its initial revision and blank brief."""
    project = create_project_v2(
        tmp_path,
        "muoi-va-huyet-ap",
        "Muối và huyết áp",
        now=FROZEN_NOW,
    )

    manifest = ProjectManifestV2.model_validate(read_yaml(project / "project.yaml"))
    assert manifest.state is WorkflowState.IDEA
    assert manifest.active_revision == "001"
    assert (project / "revisions/001/author/brief.yaml").is_file()


def test_create_project_v2_leaves_no_partial_destination_on_failure(
    tmp_path, monkeypatch
) -> None:
    """A failed initial write must not expose a partially-created destination."""
    monkeypatch.setattr(
        "healthvideo.workflows.create_project_v2.write_yaml_atomic",
        Mock(side_effect=OSError("disk")),
    )

    with pytest.raises(OSError, match="disk"):
        create_project_v2(tmp_path, "muoi", "Muối", now=FROZEN_NOW)

    assert not (tmp_path / "muoi").exists()
