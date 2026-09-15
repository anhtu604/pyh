import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

import healthvideo.workflows.ai_clips as ai_clips_module
from healthvideo.domain.asset_manifest import (
    AssetKind,
    AssetManifest,
    load_asset_manifest,
    validate_asset_manifest,
)
from healthvideo.domain.brand import LogoVariant
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.hook_outro import OUTRO_TEXT
from healthvideo.domain.invalidation import (
    ArtifactChange,
    InvalidationLevel,
    evaluate_invalidation,
)
from healthvideo.domain.project import ProjectState, transition
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.stage import StageManifest, StageStatus
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.storage.revisions import create_revision
from healthvideo.storage.stages import append_stage_manifest
from healthvideo.tts.base import TTSRequest, TTSResult
from healthvideo.tts.silent import SilentTTS
from healthvideo.video_ai.base import VeoRequest, VeoResult, VideoProbeResult
from healthvideo.video_ai.veo import GoogleVeoTransport
from healthvideo.workflows.ai_clips import AIClipRights, generate_ai_clip
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.hook_outro import author_hook_outro
from healthvideo.workflows.migrate import migrate_project, plan_migration
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review_html import render_medical_packet, render_video_packet
from healthvideo.workflows.visual_assets import (
    bind_chart_asset,
    create_brand_logo_asset,
    create_evidence_chart,
)
from tests.helpers import _advance_v2_state, create_v2_project_fixture

GOLDEN_PROJECTS = [
    Path("tests/fixtures/golden-project"),
    Path("tests/fixtures/golden-project-v2"),
]

GOLDEN_ENTERED_AT = datetime(2026, 9, 10, 7, 30, tzinfo=UTC)


def test_m64_hook_outro_through_both_manual_gates_and_package(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision = project / "revisions/001"
    board_path = revision / "storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["scenes"][0]["duration_frames"] = 1350
    write_yaml_atomic(board_path, board)
    author_hook_outro(project, duration_frames=90)
    create_brand_logo_asset(project, scene_id="OUTRO", asset_name="pyh-logo", variant=LogoVariant.MONOGRAM)
    packet = render_medical_packet(revision)
    assert "Hook:" in packet and "Outro:" in packet and "pyh-logo.svg" in packet
    logo = next(asset for asset in read_yaml(revision / "assets/asset-manifest.yaml")["assets"]
                if asset.get("storyboard_role") == "brand")
    assert logo["sha256"] in packet and logo["license"] in packet
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=GOLDEN_ENTERED_AT)
    video = produce_project(project, SilentTTS(), _write_golden_video)
    assert video.is_file()
    assert read_yaml(project / "project.yaml")["state"] == "awaiting_video_review"
    render_input = json.loads((revision / "renders/render-input.json").read_text(encoding="utf-8"))
    assert render_input["scenes"][0]["start_frame"] == 0
    assert render_input["scenes"][-1]["visual"] == "brand_outro"
    qa = json.loads((revision / "reviews/video-qa.json").read_text(encoding="utf-8"))
    assert qa["composition_duration_ms"] == 48000 and qa["audio_duration_ms"] > 0
    approve_gate(project, GateKind.VIDEO, reviewer="doctor", now=GOLDEN_ENTERED_AT)
    package = package_project(project)
    caption = (package / "caption.txt").read_text(encoding="utf-8")
    script = read_yaml(revision / "script/script.yaml")
    assert script["lines"][0]["text"] in caption
    assert script["lines"][-1]["text"] not in caption


def test_m65_zero_ai_budget_through_chart_outro_gates_and_package(tmp_path: Path) -> None:
    before = _snapshot_tree(GOLDEN_PROJECTS[1])
    project = tmp_path / "golden-project-v2"
    shutil.copytree(GOLDEN_PROJECTS[1], project)
    _advance_v2_state(project, WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision = project / "revisions/001"
    ledger_path = revision / "evidence/ledger.yaml"
    ledger = read_yaml(ledger_path)
    ledger["claims"][0]["chart_data"] = [
        {"id": "bp-count", "source_id": "R01", "label": "Mẫu thử tổng hợp",
         "value": 12, "denominator": 40, "unit": "người"}
    ]
    write_yaml_atomic(ledger_path, ledger)
    board_path = revision / "storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["visual_budget_profile"] = "m6_5_v1"
    start = 0
    for scene in board["scenes"]:
        chart_crop = scene["visual"] in {"chart", "evidence_highlight"}
        scene["start_frame"], scene["duration_frames"] = start, 225 if chart_crop else 315
        start += scene["duration_frames"]
    write_yaml_atomic(board_path, board)
    author_hook_outro(project, duration_frames=90)
    create_brand_logo_asset(project, scene_id="OUTRO", asset_name="pyh-logo", variant=LogoVariant.MONOGRAM)
    chart = create_evidence_chart(
        project, claim_id="C01", datum_id="bp-count", asset_name="chart-count",
        license="synthetic_test_only", rights_basis="fixture nội bộ", creator="repository_fixture",
    )
    bind_chart_asset(project, scene_id="S04", asset_path="assets/chart-count.svg")
    assert "Ngân sách visual M6.5" in render_medical_packet(revision)
    records = {record.path: record for record in load_asset_manifest(revision / "assets/asset-manifest.yaml").assets}
    chart_record = records["assets/chart-count.svg"]
    assert (chart_record.kind, chart_record.semantic, chart_record.storyboard_role) == (
        AssetKind.DATA_CHART, True, "chart"
    )
    rights = read_yaml(revision / "assets/license-ledger.yaml")["entries"]
    assert any(entry["path"] == chart_record.path for entry in rights)
    assert any(record.storyboard_role == "brand" and record.sha256 for record in records.values())
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=GOLDEN_ENTERED_AT)

    tts_calls: list[str] = []
    staged_charts: list[bytes] = []

    class CountingSilent(SilentTTS):
        def synthesize(self, request: TTSRequest, output_path: Path) -> TTSResult:
            tts_calls.append(request.text)
            return super().synthesize(request, output_path)

    def runner(argv: list[str]) -> int:
        props = Path(argv[argv.index("--props") + 1])
        staged_charts.append((props.parent / "assets/chart-count.svg").read_bytes())
        return _write_golden_video(argv)

    produce_project(project, CountingSilent(), runner)
    assert staged_charts == [chart.read_bytes()] and len(tts_calls) == 1
    render_input = json.loads((revision / "renders/render-input.json").read_text(encoding="utf-8"))
    scenes = render_input["scenes"]
    assert (scenes[0]["id"], scenes[0]["start_frame"], scenes[0]["visual"]) == ("S01", 0, "whiteboard")
    assert not any("intro" in f"{scene['id']} {scene['visual']}".lower() for scene in scenes)
    assert scenes[-1]["visual"] == "brand_outro" and scenes[-1]["narration"] == OUTRO_TEXT
    assert next(scene for scene in scenes if scene["id"] == "S04")["visual_assets"] == [
        {"path": "assets/chart-count.svg", "role": "chart", "pose": None}
    ]
    qa = json.loads((revision / "reviews/video-qa.json").read_text(encoding="utf-8"))
    assert qa["composition_duration_ms"] == 60000 and qa["audio_duration_ms"] > 0
    assert qa["visual_budget"]["category_frames"] == {"whiteboard_svg": 1350, "chart_crop": 450, "ai_clip": 0}
    assert qa["visual_budget"]["passed"] is True
    assert "QA production: khớp report tái tính" in render_video_packet(revision)
    assert read_yaml(project / "project.yaml")["state"] == "awaiting_video_review"

    approve_gate(project, GateKind.VIDEO, reviewer="doctor", now=GOLDEN_ENTERED_AT)
    package = package_project(project)
    caption = (package / "caption.txt").read_text(encoding="utf-8")
    script = read_yaml(revision / "script/script.yaml")
    assert script["lines"][0]["text"] in caption and OUTRO_TEXT not in caption
    assert not (package / "ai-disclosure.json").exists()
    assert read_yaml(project / "project.yaml")["state"] == "packaged"
    assert _snapshot_tree(GOLDEN_PROJECTS[1]) == before


def test_m66_ai_clip_through_both_manual_gates_and_disclosed_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _snapshot_tree(GOLDEN_PROJECTS[1])
    project = tmp_path / "golden-project-v2"
    shutil.copytree(GOLDEN_PROJECTS[1], project)
    _advance_v2_state(project, WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision = project / "revisions/001"
    ledger_path = revision / "evidence/ledger.yaml"
    ledger = read_yaml(ledger_path)
    ledger["claims"][0]["chart_data"] = [
        {"id": "bp-count", "source_id": "R01", "label": "Mẫu thử tổng hợp",
         "value": 12, "denominator": 40, "unit": "người"}
    ]
    write_yaml_atomic(ledger_path, ledger)
    board_path = revision / "storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["visual_budget_profile"] = "m6_5_v1"
    board["scenes"][1]["visual"] = "ai_clip"
    durations = {"ai_clip": 180, "chart": 225, "evidence_highlight": 225, "whiteboard": 390}
    start = 0
    for scene in board["scenes"]:
        scene["start_frame"], scene["duration_frames"] = start, durations[scene["visual"]]
        start += scene["duration_frames"]
    write_yaml_atomic(board_path, board)
    author_hook_outro(project, duration_frames=90)
    create_brand_logo_asset(project, scene_id="OUTRO", asset_name="pyh-logo", variant=LogoVariant.MONOGRAM)
    create_evidence_chart(
        project, claim_id="C01", datum_id="bp-count", asset_name="chart-count",
        license="synthetic_test_only", rights_basis="fixture nội bộ", creator="repository_fixture",
    )
    bind_chart_asset(project, scene_id="S04", asset_path="assets/chart-count.svg")

    provider_requests: list[VeoRequest] = []

    class FakeVeo:
        def generate(self, request: VeoRequest) -> VeoResult:
            provider_requests.append(request)
            return VeoResult(video_bytes=b"synthetic-e2e-ai-clip", mime_type="video/mp4")

    prompt = "Minh họa tổng hợp: một người nêm ít muối khi nấu ăn"
    clip = generate_ai_clip(
        project, scene_id="S02", prompt=prompt, duration_seconds=6, requested_seed=None,
        rights=AIClipRights(
            source="Google Vertex AI generation", creator="PYH operator",
            license="synthetic_test_only", rights_basis="fixture nội bộ",
        ),
        transport=FakeVeo(), now=GOLDEN_ENTERED_AT,
        probe=lambda _path: VideoProbeResult(
            mime_type="video/mp4", container="mp4", width=1080, height=1920,
            source_fps=24, duration_ms=6000, source_frame_count=144, video_stream_count=1,
        ),
    )
    assert clip.is_relative_to(tmp_path) and len(provider_requests) == 1
    packet = render_medical_packet(revision)
    assert "veo-3.1-fast-generate-001" in packet and prompt not in packet
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=GOLDEN_ENTERED_AT)

    def no_provider(*_args: object, **_kwargs: object) -> None:
        pytest.fail("AI provider reached after medical approval")

    monkeypatch.setattr(ai_clips_module, "generate_ai_clip", no_provider)
    monkeypatch.setattr(ai_clips_module, "probe_ai_clip_media", no_provider)
    monkeypatch.setattr(GoogleVeoTransport, "generate", no_provider)
    tts_calls: list[str] = []
    staged_clips: list[bytes] = []

    class CountingSilent(SilentTTS):
        def synthesize(self, request: TTSRequest, output_path: Path) -> TTSResult:
            tts_calls.append(request.text)
            return super().synthesize(request, output_path)

    def runner(argv: list[str]) -> int:
        props = Path(argv[argv.index("--props") + 1])
        staged_clips.append((props.parent / "assets/ai-clips/S02.mp4").read_bytes())
        return _write_golden_video(argv)

    produce_project(project, CountingSilent(), runner)
    assert staged_clips == [clip.read_bytes()] and len(tts_calls) == 1
    render_input = json.loads((revision / "renders/render-input.json").read_text(encoding="utf-8"))
    scenes = render_input["scenes"]
    assert (render_input["fps"], render_input["audio_file"]) == (30, "audio/narration.wav")
    assert (scenes[0]["id"], scenes[0]["start_frame"], scenes[0]["visual"]) == ("S01", 0, "whiteboard")
    assert not any("intro" in f"{scene['id']} {scene['visual']}".lower() for scene in scenes)
    assert scenes[-1]["visual"] == "brand_outro" and scenes[-1]["narration"] == OUTRO_TEXT
    ai_scene = next(scene for scene in scenes if scene["id"] == "S02")
    assert (ai_scene["visual"], ai_scene["duration_frames"], ai_scene["visual_assets"]) == (
        "ai_clip", 180, [{"path": "assets/ai-clips/S02.mp4", "role": "ai_clip", "pose": None}]
    )
    ai_renderer = (
        Path(__file__).parents[2] / "video/src/scenes/AiClipScene.tsx"
    ).read_text(encoding="utf-8")
    assert ai_renderer.count("<OffthreadVideo") == 1
    assert "muted" in ai_renderer
    for forbidden_playback_prop in (
        "loop=", "playbackRate=", "trimBefore=", "trimAfter=", "volume=",
    ):
        assert forbidden_playback_prop not in ai_renderer
    qa = json.loads((revision / "reviews/video-qa.json").read_text(encoding="utf-8"))
    assert qa["composition_duration_ms"] == 63000 and qa["audio_duration_ms"] > 0
    assert qa["visual_budget"]["category_frames"] == {
        "whiteboard_svg": 1260, "chart_crop": 450, "ai_clip": 180,
    }
    assert qa["visual_budget"]["passed"] is True

    approve_gate(project, GateKind.VIDEO, reviewer="doctor", now=GOLDEN_ENTERED_AT)
    package = package_project(project)
    disclosure = json.loads((package / "ai-disclosure.json").read_text(encoding="utf-8"))
    assert disclosure["contains_ai"] is True
    assert disclosure["clips"] == [{
        "scene_id": "S02", "path": "assets/ai-clips/S02.mp4", "provider": "google_vertex_ai",
        "model": "veo-3.1-fast-generate-001", "classification": "semantic",
    }]
    assert prompt not in (package / "ai-disclosure.json").read_text(encoding="utf-8")
    assert "ai-disclosure.json" in json.loads(
        (package / "manifest.json").read_text(encoding="utf-8")
    )["payload_sha256"]
    assert sorted(path.name for path in (revision / "reviews").glob("*-approval.yaml")) == [
        "medical-approval.yaml", "video-approval.yaml",
    ]
    assert read_yaml(project / "project.yaml")["state"] == "packaged"
    assert len(provider_requests) == 1
    assert _snapshot_tree(GOLDEN_PROJECTS[1]) == before


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
