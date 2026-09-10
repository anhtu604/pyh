from pathlib import Path

from healthvideo.domain.project import ProjectState, transition
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.project_layout import resolve_project_layout

GOLDEN_PROJECTS = [
    Path("tests/fixtures/golden-project"),
    Path("tests/fixtures/golden-project-v2"),
]


def test_v1_and_v2_golden_are_available_from_first_m1_task() -> None:
    layouts = [resolve_project_layout(path) for path in GOLDEN_PROJECTS]

    assert [layout.schema_version for layout in layouts] == ["1.0", "2.0"]
    for layout in layouts:
        assert (layout.artifact_root / "evidence" / "ledger.yaml").is_file()
        assert (layout.artifact_root / "script" / "script.yaml").is_file()
        assert (layout.artifact_root / "storyboard" / "storyboard.yaml").is_file()


def test_dual_golden_keeps_v1_linear_and_advances_v2_with_its_topic_card() -> None:
    v1_layout, v2_layout = [resolve_project_layout(path) for path in GOLDEN_PROJECTS]
    v1_project = v1_layout.manifest
    v2_project = v2_layout.manifest
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset({"topic/card.yaml"}),
    )

    assert transition(v1_project, ProjectState.PRODUCING).state is (
        ProjectState.PRODUCING
    )
    assert transition_v2(v2_project, WorkflowState.TOPIC_SELECTED, context).state is (
        WorkflowState.TOPIC_SELECTED
    )
