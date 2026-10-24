import json
import shutil
import wave
from datetime import UTC, datetime
from pathlib import Path

from healthvideo.domain.asset_manifest import (
    AssetKind,
    AssetManifest,
    load_asset_manifest,
    validate_asset_manifest,
)
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.hook_outro import OUTRO_TEXT
from healthvideo.domain.invalidation import (
    ArtifactChange,
    InvalidationLevel,
    evaluate_invalidation,
)
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.stage import StageManifest, StageStatus
from healthvideo.domain.storyboard import Storyboard
from healthvideo.domain.visual_budget import calculate_visual_budget
from healthvideo.render.timing import retime_storyboard
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.storage.revisions import create_revision
from healthvideo.storage.stages import append_stage_manifest
from healthvideo.tts.base import TTSRequest, TTSResult, word_timestamps
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review_html import render_medical_packet, render_video_packet
from healthvideo.workflows.visual_assets import (
    bind_chart_asset,
    create_evidence_chart,
)
from tests.helpers import (
    _advance_v2_state,
    align_fixture_script,
    create_long_form_project_fixture,
    create_v2_project_fixture,
)

GOLDEN_PROJECTS = [
    Path("tests/fixtures/golden-project-v2"),
]

GOLDEN_ENTERED_AT = datetime(2026, 9, 10, 7, 30, tzinfo=UTC)


class GoldenSceneTTS:
    """Keep visual-budget fixtures at their intended duration using actual PCM audio."""

    provider_name = "golden-scene-timing"

    def __init__(self, revision_root: Path) -> None:
        board = read_yaml(revision_root / "storyboard/storyboard.yaml")
        self.duration_ms = {
            scene["narration"]: (scene["duration_frames"] - 9) * 1000 // 30
            for scene in board["scenes"]
        }
        self.calls: list[str] = []

    def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
        self.calls.append(request.text)
        duration_ms = self.duration_ms[request.text]
        output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output), "wb") as wav:
            wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            wav.writeframes(b"\0\0" * (duration_ms * 24))
        return TTSResult(
            provider=self.provider_name, audio_file=output, duration_ms=duration_ms,
            word_timestamps=word_timestamps(request.text.split(), duration_ms),
        )


def test_video_review_recomputes_measured_runtime_budget_without_changing_medical_packet(
    tmp_path: Path,
) -> None:
    project = create_v2_project_fixture(tmp_path)
    revision = project / "revisions/001"
    board_path = revision / "storyboard/storyboard.yaml"
    raw = read_yaml(board_path)
    raw["visual_budget_profile"] = "m6_5_v1"
    raw["scenes"][0]["script_line_id"] = "L01"
    write_yaml_atomic(board_path, raw)
    approved = Storyboard.model_validate(raw)
    medical = render_medical_packet(revision)
    runtime, record = retime_storyboard(approved, {scene.script_line_id: 1000 for scene in approved.scenes})
    (revision / "renders").mkdir(exist_ok=True)
    (revision / "renders/scene-timing.json").write_text(json.dumps(record), encoding="utf-8")
    (revision / "reviews").mkdir(exist_ok=True)
    (revision / "reviews/video-qa.json").write_text(json.dumps({
        "visual_budget": calculate_visual_budget(runtime).model_dump(mode="json"),
    }), encoding="utf-8")

    packet = render_video_packet(revision)

    assert "QA production: khớp report tái tính" in packet
    assert "Tổng timeline: 234 frame" in packet
    assert render_medical_packet(revision) == medical


def test_video_review_clip_source_spans_follow_measured_runtime(tmp_path: Path) -> None:
    project = create_long_form_project_fixture(tmp_path)
    revision = project / "revisions/001"
    board = Storyboard.model_validate(read_yaml(revision / "storyboard/storyboard.yaml"))
    _, record = retime_storyboard(board, {scene.script_line_id: 30000 for scene in board.scenes})
    (revision / "renders").mkdir(exist_ok=True)
    (revision / "renders/scene-timing.json").write_text(json.dumps(record), encoding="utf-8")
    (revision / "renders/render-manifest.json").write_text(json.dumps({
        "clips": {"CL01": "clips/CL01.mp4", "CL02": "clips/CL02.mp4"},
    }), encoding="utf-8")

    packet = render_video_packet(revision)

    assert "Source timeline: 0–1818 frame" in packet
    assert "Source timeline: 1818–3636 frame" in packet
    assert "Source timeline: 0–1800 frame" not in packet


def test_m64_hook_outro_through_both_manual_gates_and_package(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision = project / "revisions/001"
    board_path = revision / "storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    write_yaml_atomic(board_path, board)
    script_path = revision / "script/script.yaml"
    script = read_yaml(script_path)
    script["format_profile"] = "hook_outro_v1"
    write_yaml_atomic(script_path, script)
    packet = render_medical_packet(revision)
    assert "test-logo.svg" in packet
    assert read_yaml(revision / "script/script.yaml")["lines"][-1]["text"] == OUTRO_TEXT
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
    runtime_frames = sum(scene["duration_frames"] for scene in render_input["scenes"])
    assert qa["composition_duration_ms"] == round(runtime_frames * 1000 / 30)
    assert qa["audio_duration_ms"] == qa["composition_duration_ms"]
    assert qa["composition_duration_ms"] != 48000
    approve_gate(project, GateKind.VIDEO, reviewer="doctor", now=GOLDEN_ENTERED_AT)
    package = package_project(project)
    caption = (package / "caption.txt").read_text(encoding="utf-8")
    script = read_yaml(revision / "script/script.yaml")
    assert script["lines"][0]["text"] in caption
    assert script["lines"][-1]["text"] not in caption


def test_m65_zero_ai_budget_through_chart_outro_gates_and_package(tmp_path: Path) -> None:
    before = _snapshot_tree(GOLDEN_PROJECTS[0])
    project = tmp_path / "golden-project-v2"
    shutil.copytree(GOLDEN_PROJECTS[0], project)
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
    board = _m65_golden_board(revision)
    write_yaml_atomic(board_path, board)
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

    tts = GoldenSceneTTS(revision)
    staged_charts: list[bytes] = []

    def runner(argv: list[str]) -> int:
        props = Path(argv[argv.index("--props") + 1])
        staged_charts.append((props.parent / "assets/chart-count.svg").read_bytes())
        return _write_golden_video(argv)

    produce_project(project, tts, runner)
    assert staged_charts == [chart.read_bytes()]
    assert tts.calls == [line["text"] for line in read_yaml(revision / "script/script.yaml")["lines"]]
    render_input = json.loads((revision / "renders/render-input.json").read_text(encoding="utf-8"))
    scenes = render_input["scenes"]
    assert (scenes[0]["id"], scenes[0]["start_frame"], scenes[0]["visual"]) == ("S01", 0, "whiteboard")
    assert not any("intro" in f"{scene['id']} {scene['visual']}".lower() for scene in scenes)
    assert scenes[-1]["visual"] == "brand_outro" and scenes[-1]["narration"] == OUTRO_TEXT
    assert next(scene for scene in scenes if scene["id"] == "S04")["visual_assets"] == [
        {"path": "assets/chart-count.svg", "role": "chart", "pose": None}
    ]
    qa = json.loads((revision / "reviews/video-qa.json").read_text(encoding="utf-8"))
    runtime_board = Storyboard.model_validate({**read_yaml(board_path), "scenes": scenes})
    assert qa["composition_duration_ms"] == round(sum(s["duration_frames"] for s in scenes) * 1000 / 30)
    assert qa["audio_duration_ms"] == qa["composition_duration_ms"]
    assert qa["visual_budget"] == calculate_visual_budget(runtime_board).model_dump(mode="json")
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
    assert _snapshot_tree(GOLDEN_PROJECTS[0]) == before


def test_dual_golden_appends_a_stage_manifest_without_touching_the_tracked_fixture(
    tmp_path: Path,
) -> None:
    v2_source = GOLDEN_PROJECTS[0]
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
    v2_source = GOLDEN_PROJECTS[0]
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
    v2_source = GOLDEN_PROJECTS[0]
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

    v2_source = GOLDEN_PROJECTS[0]
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


def _snapshot_tree(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_dual_golden_medical_gate_approves_on_a_copy_without_touching_the_tracked_fixture(
    tmp_path: Path,
) -> None:
    v2_source = GOLDEN_PROJECTS[0]
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
    shutil.copytree(GOLDEN_PROJECTS[0], project_dir)
    revision = project_dir / "revisions/001"
    board_path = revision / "storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    lines = read_yaml(revision / "script/script.yaml")["lines"]
    for scene, line in zip(board["scenes"], lines, strict=True):
        assert scene["narration"] == line["text"]
        scene["script_line_id"] = line["id"]
    write_yaml_atomic(board_path, board)
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


def _m65_golden_board(revision: Path) -> dict:
    board = read_yaml(revision / "storyboard/storyboard.yaml")
    highlight = board["scenes"][0]["evidence_highlight"]
    board["visual_budget_profile"] = "m6_5_v1"
    for scene in board["scenes"]:
        for field in ("anatomy", "beats", "evidence_highlight"):
            scene.pop(field, None)
        scene["visual"] = "whiteboard"
        scene["on_screen_text"] = "Synthetic illustration."
        if scene["id"] == "S03":
            scene.update(visual="evidence_highlight", evidence_highlight=highlight,
                         claim_id="C01", source_marker="[1]")
        elif scene["id"] == "S04":
            scene["visual"] = "chart"
        elif scene["id"] == "OUTRO":
            scene["visual"] = "brand_outro"
        if scene["id"] != "OUTRO":
            scene["narration"] = f"{scene['id']}. {scene['narration']}"
        durations = {"chart": 225, "evidence_highlight": 225,
                     "whiteboard": 315, "brand_outro": 90}
        scene["duration_frames"] = durations[scene["visual"]]
    align_fixture_script(revision, board)
    return board
