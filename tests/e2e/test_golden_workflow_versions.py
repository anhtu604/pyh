import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from healthvideo.domain.asset_manifest import AssetManifest, validate_asset_manifest
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.invalidation import (
    ArtifactChange,
    InvalidationLevel,
    evaluate_invalidation,
)
from healthvideo.domain.project import ProjectState, transition
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.stage import StageManifest, StageStatus
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.files import read_yaml
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.storage.revisions import create_revision
from healthvideo.storage.stages import append_stage_manifest
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.migrate import migrate_project, plan_migration
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from tests.helpers import _advance_v2_state

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


def test_dual_golden_asset_manifest_loads_and_validates_without_rewrite() -> None:
    v2_source = GOLDEN_PROJECTS[1]
    manifest_path = v2_source / "revisions" / "001" / "assets" / "asset-manifest.yaml"
    before = {
        path: path.read_bytes() for path in v2_source.rglob("*") if path.is_file()
    }

    manifest = AssetManifest.model_validate(read_yaml(manifest_path))
    validate_asset_manifest(v2_source / "revisions" / "001", manifest)

    assert manifest.assets[0].path == "assets/evidence-r01.svg"
    after = {
        path: path.read_bytes() for path in v2_source.rglob("*") if path.is_file()
    }
    assert after == before


def test_dual_golden_creates_a_revision_without_touching_the_tracked_fixture(
    tmp_path: Path,
) -> None:
    v2_source = GOLDEN_PROJECTS[1]
    before = {
        path: path.read_bytes() for path in v2_source.rglob("*") if path.is_file()
    }

    copy_dir = tmp_path / "golden-project-v2"
    shutil.copytree(v2_source, copy_dir)
    parent_revision_before = {
        path: path.read_bytes()
        for path in (copy_dir / "revisions" / "001").rglob("*")
        if path.is_file()
    }

    revision = create_revision(
        copy_dir, "Sửa luận điểm sau phản biện", now=GOLDEN_ENTERED_AT
    )

    assert revision == "002"
    layout = resolve_project_layout(copy_dir)
    assert layout.manifest.active_revision == "002"
    assert (copy_dir / "revisions" / "002" / "topic" / "card.yaml").is_file()
    assert (copy_dir / "revisions" / "002" / "workflow.yaml").is_file()
    parent_revision_after = {
        path: path.read_bytes()
        for path in (copy_dir / "revisions" / "001").rglob("*")
        if path.is_file()
    }
    assert parent_revision_after == parent_revision_before

    after = {
        candidate: candidate.read_bytes()
        for candidate in v2_source.rglob("*")
        if candidate.is_file()
    }
    assert after == before


def test_dual_golden_invalidation_engine_only_evaluates_v2_assets() -> None:
    """The invalidation engine (Task 7) is v2-only policy over v2 data.

    It reads the v2 golden asset manifest, is fail-closed on unrecognised
    paths, and never touches the filesystem -- so neither golden project's
    tracked bytes move, and the v1 golden project is never handed to it at
    all, i.e. fixture v1 is never subjected to v2 invalidation policy.
    """
    before = {
        path: path.read_bytes()
        for source in GOLDEN_PROJECTS
        for path in source.rglob("*")
        if path.is_file()
    }

    v2_source = GOLDEN_PROJECTS[1]
    manifest_path = v2_source / "revisions" / "001" / "assets" / "asset-manifest.yaml"
    asset_manifest = AssetManifest.model_validate(read_yaml(manifest_path))

    semantic_decision = evaluate_invalidation(
        [ArtifactChange(path=Path("assets/evidence-r01.svg"), json_pointers=frozenset())],
        asset_manifest,
    )
    assert semantic_decision.level is InvalidationLevel.MEDICAL
    assert semantic_decision.target_state is WorkflowState.NEEDS_MEDICAL_REVISION

    package_decision = evaluate_invalidation(
        [
            ArtifactChange(
                path=Path("publish/metadata.yaml"),
                json_pointers=frozenset({"/posting/visibility"}),
            )
        ],
        asset_manifest,
    )
    assert package_decision.level is InvalidationLevel.PACKAGE
    assert package_decision.target_state is None

    after = {
        path: path.read_bytes()
        for source in GOLDEN_PROJECTS
        for path in source.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_dual_golden_migration_plan_matches_the_v2_fixture_without_writing() -> None:
    before = {
        path: path.read_bytes()
        for source in GOLDEN_PROJECTS
        for path in source.rglob("*")
        if path.is_file()
    }

    plan = plan_migration(GOLDEN_PROJECTS[0])

    expected_destinations = {
        "project.yaml",
        "revisions/001/author/brief.yaml",
        "revisions/001/evidence/ledger.yaml",
        "revisions/001/script/script.yaml",
        "revisions/001/storyboard/storyboard.yaml",
        "revisions/001/assets/evidence-r01.svg",
        "revisions/001/topic/card.yaml",
        "revisions/001/assets/asset-manifest.yaml",
    }
    assert {item.destination.as_posix() for item in plan.files} == expected_destinations
    assert plan.destination == GOLDEN_PROJECTS[1]
    assert plan.destination_conflict is True

    after = {
        path: path.read_bytes()
        for source in GOLDEN_PROJECTS
        for path in source.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_dual_golden_accepts_a_newly_migrated_v1_copy(tmp_path: Path) -> None:
    source = tmp_path / "golden-project"
    shutil.copytree(GOLDEN_PROJECTS[0], source)
    source_before = {
        path.relative_to(source): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }

    migrated = migrate_project(
        source,
        now=GOLDEN_ENTERED_AT,
        migration_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    v1_layout = resolve_project_layout(source)
    v2_layout = resolve_project_layout(migrated)
    assert v1_layout.schema_version == "1.0"
    assert v2_layout.schema_version == "2.0"
    assert {
        path.relative_to(source): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    } == source_before


def _snapshot_tree(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_dual_golden_medical_gate_approves_on_a_copy_without_touching_the_tracked_fixture(
    tmp_path: Path,
) -> None:
    v2_source = GOLDEN_PROJECTS[1]
    before = _snapshot_tree(v2_source)
    copy_dir = tmp_path / "copy"
    shutil.copytree(v2_source, copy_dir)
    _advance_v2_state(copy_dir, WorkflowState.AWAITING_MEDICAL_REVIEW)

    record = approve_gate(
        copy_dir, GateKind.MEDICAL, reviewer="BS Nguyễn Văn An", now=GOLDEN_ENTERED_AT
    )

    assert record.artifact_hashes
    assert _snapshot_tree(v2_source) == before


def test_v2_golden_copy_produces_and_packages_without_touching_either_fixture(
    tmp_path: Path,
) -> None:
    before = {
        source: _snapshot_tree(source)
        for source in GOLDEN_PROJECTS
    }
    project_dir = tmp_path / "golden-project-v2"
    shutil.copytree(GOLDEN_PROJECTS[1], project_dir)
    _advance_v2_state(project_dir, WorkflowState.AWAITING_MEDICAL_REVIEW)
    approve_gate(
        project_dir,
        GateKind.MEDICAL,
        reviewer="BS Nguyễn Văn An",
        now=GOLDEN_ENTERED_AT,
    )

    video = produce_project(project_dir, SilentTTS(), _write_golden_video)
    approve_gate(
        project_dir,
        GateKind.VIDEO,
        reviewer="BS Nguyễn Văn An",
        now=GOLDEN_ENTERED_AT,
    )
    package = package_project(project_dir)

    assert video == project_dir / "revisions" / "001" / "renders" / "video.mp4"
    assert (package / "manifest.json").is_file()
    assert read_yaml(project_dir / "project.yaml")["state"] == "packaged"
    assert {
        source: _snapshot_tree(source)
        for source in GOLDEN_PROJECTS
    } == before


def _write_golden_video(argv: list[str]) -> int:
    output = Path(argv[argv.index("--output") + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"golden-v2-mp4")
    return 0
