import pytest

from healthvideo.domain.project import ProjectManifest, ProjectState, transition


def test_state_machine_accepts_only_next_state() -> None:
    project = ProjectManifest(slug="muoi-va-huyet-ap")

    changed = transition(project, ProjectState.EVIDENCE_IN_PROGRESS)

    assert changed.state is ProjectState.EVIDENCE_IN_PROGRESS
    with pytest.raises(ValueError, match="Invalid transition"):
        transition(changed, ProjectState.RENDERED)
