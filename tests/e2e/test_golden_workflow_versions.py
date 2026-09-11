import shutil
from datetime import UTC, datetime
from pathlib import Path

from healthvideo.domain.project import ProjectState, transition
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.stage import StageManifest, StageStatus
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.storage.stages import append_stage_manifest

GOLDEN_PROJECTS = [
    Path("tests/fixtures/golden-project"),
    Path("tests/fixtures/golden-project-v2"),
]

GOLDEN_ENTERED_AT = datetime(2026, 9, 10, 7, 30, tzinfo=UTC)


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


def test_dual_golden_keeps_v1_side_state_free_while_v2_pauses_and_resumes() -> None:
    v1_layout, v2_layout = [resolve_project_layout(path) for path in GOLDEN_PROJECTS]
    v1_project = v1_layout.manifest
    v2_project = v2_layout.manifest
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset({"topic/card.yaml"}),
    )

    assert not hasattr(v1_project, "side_state")
    assert v2_project.side_state is None

    paused = transition_v2(
        v2_project,
        WorkflowState.AWAITING_BROWSER_LOGIN,
        context,
        reason_code="browser_session_expired",
        resume_state=WorkflowState.IDEA,
        entered_at=GOLDEN_ENTERED_AT,
    )
    assert paused.state is WorkflowState.AWAITING_BROWSER_LOGIN
    assert paused.side_state is not None
    assert paused.side_state.resume_state is WorkflowState.IDEA
    assert paused.side_state.entered_at == GOLDEN_ENTERED_AT

    resumed = transition_v2(paused, WorkflowState.IDEA, context)
    assert resumed.state is WorkflowState.IDEA
    assert resumed.side_state is None

    assert transition(v1_project, ProjectState.PRODUCING).state is (
        ProjectState.PRODUCING
    )


def test_dual_golden_appends_a_stage_manifest_without_touching_the_tracked_fixture(
    tmp_path: Path,
) -> None:
    v2_source = GOLDEN_PROJECTS[1]
    before = {
        path: path.read_bytes() for path in v2_source.rglob("*") if path.is_file()
    }

    copy_dir = tmp_path / "golden-project-v2"
    shutil.copytree(v2_source, copy_dir)
    revision_root = copy_dir / "revisions" / "001"

    manifest = StageManifest(
        stage="evidence_ledger",
        status=StageStatus.COMPLETE,
        input_hash="a" * 64,
        output_hash="b" * 64,
        tool_version="1.0.0",
        agent="claude",
        model="claude-sonnet-5",
        started_at=GOLDEN_ENTERED_AT,
        completed_at=GOLDEN_ENTERED_AT,
        estimated_input_tokens=100,
        estimated_output_tokens=200,
    )

    path = append_stage_manifest(revision_root, manifest)

    assert path.is_relative_to(revision_root / "workflow" / "stages")
    assert path.is_file()
    after = {
        candidate: candidate.read_bytes()
        for candidate in v2_source.rglob("*")
        if candidate.is_file()
    }
    assert after == before
