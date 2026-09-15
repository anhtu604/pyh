import shutil
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

import healthvideo.tts.pronunciation as pronunciation_module
import healthvideo.workflows.ai_clips as ai_clips_module
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.video_ai.base import VeoRequest, VeoResult, VideoProbeResult
from healthvideo.workflows.ai_clips import AIClipRights, generate_ai_clip
from healthvideo.workflows.gate_review import (
    MEDICAL_APPROVAL_ARTIFACT,
    approve_gate,
    hash_reviewed_artifacts,
    medical_reviewed_paths,
    reject_gate,
    resume_gate,
)
from tests.helpers import (
    advance_v2_project_to_video_review,
    create_project_fixture,
    create_v2_project_fixture,
)

REVIEWER = "BS Nguyễn Văn An"
NOW = datetime(2026, 9, 11, 9, 0, tzinfo=UTC)


class _FakeVeo:
    def generate(self, request: VeoRequest) -> VeoResult:
        return VeoResult(video_bytes=b"synthetic-ai-clip", mime_type="video/mp4")


def _ai_probe(_path: Path) -> VideoProbeResult:
    return VideoProbeResult(
        mime_type="video/mp4", container="mp4", width=1080, height=1920,
        source_fps=24, duration_ms=4000, source_frame_count=96,
        video_stream_count=1,
    )


def _author_ai_clip(project_dir: Path, *, decorative: bool = False) -> Path:
    board_path = project_dir / "revisions/001/storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["visual_budget_profile"] = "m6_5_v1"
    whiteboard = board["scenes"][0]
    highlight = board["scenes"][2]
    clip = board["scenes"][3]
    whiteboard["start_frame"], whiteboard["duration_frames"] = 0, 780
    highlight["start_frame"], highlight["duration_frames"] = 780, 300
    clip["start_frame"], clip["duration_frames"] = 1080, 120
    clip["visual"] = "ai_clip"
    clip.pop("evidence_highlight", None)
    board["scenes"] = [whiteboard, highlight, clip]
    if decorative:
        clip["claim_id"] = None
        clip["source_marker"] = None
    write_yaml_atomic(board_path, board)
    output = generate_ai_clip(
        project_dir,
        scene_id="S04",
        prompt="PRIVATE PROMPT <script>",
        duration_seconds=4,
        requested_seed=17,
        rights=AIClipRights(
            source="Google Vertex AI generation",
            creator="Protect Your Health operator",
            license="operator-recorded provider terms",
            rights_basis="operator confirmed authorized generation and use",
        ),
        transport=_FakeVeo(),
        now=NOW,
        probe=_ai_probe,
    )
    write_yaml_atomic(
        project_dir / "project.yaml",
        read_yaml(project_dir / "project.yaml") | {"state": "awaiting_medical_review"},
    )
    return output


def _create_ai_project(tmp_path: Path) -> Path:
    root = tmp_path / "ai-project"
    shutil.copytree(Path("tests/fixtures/golden-project-v2"), root)
    write_yaml_atomic(
        root / "project.yaml",
        read_yaml(root / "project.yaml") | {"state": "draft_ready"},
    )
    return root


def _advance_to_awaiting_medical_review(project_dir: Path) -> None:
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset(
            {
                "script/script.yaml",
                "storyboard/storyboard.yaml",
                "assets/asset-manifest.yaml",
            }
        ),
    )
    changed = transition_v2(manifest, WorkflowState.AWAITING_MEDICAL_REVIEW, context)
    write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))


def _enable_visual_budget(
    project_dir: Path,
    *,
    passing_default: bool = True,
    override: dict[str, object] | None = None,
) -> Path:
    storyboard_path = (
        project_dir / "revisions" / "001" / "storyboard" / "storyboard.yaml"
    )
    board = read_yaml(storyboard_path)
    board["visual_budget_profile"] = "m6_5_v1"
    highlight = deepcopy(board["scenes"][0])
    whiteboard_frames = 900 if passing_default else 800
    highlight_frames = 300 if passing_default else 400
    board["scenes"] = [
        {
            "id": "S01",
            "start_frame": 0,
            "duration_frames": whiteboard_frames,
            "narration": "Visual whiteboard synthetic.",
            "claim_id": "C01",
            "source_marker": "[1]",
            "visual": "whiteboard",
        },
        {
            **highlight,
            "id": "S02",
            "start_frame": whiteboard_frames,
            "duration_frames": highlight_frames,
        },
    ]
    if override is not None:
        board["visual_budget_override"] = override
    write_yaml_atomic(storyboard_path, board)
    return storyboard_path


def _override(
    *,
    rationale: str = "Fixture cần tỷ lệ chart cao hơn mặc định.",
    whiteboard: tuple[int, int] = (60, 70),
    chart: tuple[int, int] = (30, 40),
) -> dict[str, object]:
    return {
        "rationale": rationale,
        "whiteboard_svg": {
            "min_percent": whiteboard[0],
            "max_percent": whiteboard[1],
        },
        "chart_crop": {
            "min_percent": chart[0],
            "max_percent": chart[1],
        },
        "ai_clip": {"min_percent": 0, "max_percent": 0},
    }


def test_medical_reviewed_paths_includes_ledger_script_storyboard_manifest_and_semantic_assets(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision_root = project_dir / "revisions" / "001"
    paths = medical_reviewed_paths(revision_root)
    assert set(paths) == {
        "evidence/ledger.yaml",
        "script/script.yaml",
        "storyboard/storyboard.yaml",
        "assets/asset-manifest.yaml",
        "profiles/pronunciation.vi.yaml",
        "asset:assets/evidence-r01.svg",
    }


@pytest.mark.parametrize("decorative", [False, True])
def test_ai_clip_bytes_and_rights_are_medically_reviewed(
    tmp_path: Path, decorative: bool
) -> None:
    project_dir = _create_ai_project(tmp_path)
    output = _author_ai_clip(project_dir, decorative=decorative)
    revision = project_dir / "revisions/001"

    paths = medical_reviewed_paths(revision)
    assert paths["asset:assets/ai-clips/S04.mp4"] == output
    assert "assets/license-ledger.yaml" in paths
    record = approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    assert "asset:assets/ai-clips/S04.mp4" in record.artifact_hashes

    output.write_bytes(b"changed-after-approval")
    assert hash_reviewed_artifacts(medical_reviewed_paths(revision)) != record.artifact_hashes


def test_medical_gate_recovers_valid_pending_ai_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = _create_ai_project(tmp_path)
    real_write = ai_clips_module._write_manifest
    calls = 0

    def fail_once(path: Path, payload: dict[str, object]) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("synthetic crash after AI intent")
        real_write(path, payload)

    monkeypatch.setattr(ai_clips_module, "_write_manifest", fail_once)
    with pytest.raises(OSError, match="synthetic crash"):
        _author_ai_clip(project_dir)
    revision = project_dir / "revisions/001"
    assert (revision / ai_clips_module.AI_CLIP_INTENT).is_file()
    write_yaml_atomic(
        project_dir / "project.yaml",
        read_yaml(project_dir / "project.yaml") | {"state": "awaiting_medical_review"},
    )

    approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    assert not (revision / ai_clips_module.AI_CLIP_INTENT).exists()
    assert read_yaml(project_dir / "project.yaml")["state"] == "medically_approved"


def test_semantic_ai_clip_requires_real_script_citation(tmp_path: Path) -> None:
    project_dir = _create_ai_project(tmp_path)
    _author_ai_clip(project_dir)
    script_path = project_dir / "revisions/001/script/script.yaml"
    script = read_yaml(script_path)
    for line in script["lines"]:
        if line.get("claim_id") == "C01":
            line["source_marker"] = None
    write_yaml_atomic(script_path, script)

    with pytest.raises(ValueError, match="script claim/source mapping"):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)


def test_approve_medical_rejects_missing_semantic_asset_bytes(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    (project_dir / "revisions" / "001" / "assets" / "evidence-r01.svg").write_bytes(b"changed")

    with pytest.raises(Exception, match="sha256"):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)


def test_approve_medical_rejects_invalid_pronunciation_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    profile = tmp_path / "pronunciation.vi.yaml"
    profile.write_text(
        "schema_version: '1.0'\nlanguage: en\nversion: '1'\nentries: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pronunciation_module, "PRONUNCIATION_PROFILE_PATH", profile)
    with pytest.raises(ValueError):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_medical_review"


def test_approve_medical_writes_record_once_and_advances_state(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)

    record = approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    approval_path = project_dir / "revisions" / "001" / MEDICAL_APPROVAL_ARTIFACT
    assert approval_path.is_file()
    assert read_yaml(approval_path)["reviewer"] == REVIEWER
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.MEDICALLY_APPROVED
    assert record.artifact_hashes
    assert "profiles/pronunciation.vi.yaml" in record.artifact_hashes

    with pytest.raises(FileExistsError):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)


def test_m6_5_default_budget_allows_normal_manual_medical_approval(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    _enable_visual_budget(project_dir)

    approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    revision = project_dir / "revisions/001"
    assert (revision / MEDICAL_APPROVAL_ARTIFACT).is_file()
    assert read_yaml(project_dir / "project.yaml")["state"] == "medically_approved"
    assert not (revision / "reviews/visual-budget-approval.yaml").exists()


def test_m6_5_invalid_default_budget_refuses_before_approval_or_state_change(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    _enable_visual_budget(project_dir, passing_default=False)

    with pytest.raises(ValueError, match="visual budget failed"):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    revision = project_dir / "revisions/001"
    assert not (revision / MEDICAL_APPROVAL_ARTIFACT).exists()
    assert read_yaml(project_dir / "project.yaml")["state"] == (
        "awaiting_medical_review"
    )


def test_m6_5_reviewed_override_changes_bounds_but_still_enforces_them(
    tmp_path: Path,
) -> None:
    passing = create_v2_project_fixture(
        tmp_path / "passing", state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    _enable_visual_budget(passing, passing_default=False, override=_override())
    approve_gate(passing, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    failing = create_v2_project_fixture(
        tmp_path / "failing", state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    _enable_visual_budget(
        failing,
        passing_default=False,
        override=_override(whiteboard=(70, 80), chart=(20, 30)),
    )
    with pytest.raises(ValueError, match="visual budget failed"):
        approve_gate(failing, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)


@pytest.mark.parametrize("mutation", ["timing", "profile", "bounds", "rationale"])
def test_m6_5_storyboard_policy_changes_make_medical_hash_stale(
    tmp_path: Path, mutation: str
) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    storyboard_path = _enable_visual_budget(
        project_dir, passing_default=False, override=_override()
    )
    record = approve_gate(
        project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW
    )
    board = read_yaml(storyboard_path)
    if mutation == "timing":
        board["scenes"][0]["duration_frames"] += 1
    elif mutation == "profile":
        board["visual_budget_profile"] = "legacy"
        del board["visual_budget_override"]
    elif mutation == "bounds":
        board["visual_budget_override"]["chart_crop"]["max_percent"] += 1
    else:
        board["visual_budget_override"]["rationale"] += " Đã sửa."
    write_yaml_atomic(storyboard_path, board)

    revision = project_dir / "revisions/001"
    current = hash_reviewed_artifacts(medical_reviewed_paths(revision))
    assert current != record.artifact_hashes


def test_legacy_v2_and_v1_medical_gates_remain_compatible(tmp_path: Path) -> None:
    legacy_v2 = create_v2_project_fixture(
        tmp_path / "v2", state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    approve_gate(legacy_v2, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    legacy_v1 = create_project_fixture(tmp_path / "v1", "awaiting_medical_review")
    from healthvideo.workflows.review import approve_medical

    approve_medical(legacy_v1, reviewer=REVIEWER)

    assert read_yaml(legacy_v2 / "project.yaml")["state"] == "medically_approved"
    assert read_yaml(legacy_v1 / "project.yaml")["state"] == "script_approved"


def test_reject_medical_enters_side_state_and_can_repeat_before_approval(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)

    first = reject_gate(
        project_dir,
        GateKind.MEDICAL,
        reviewer=REVIEWER,
        reason="Thiếu nguồn cho claim C01.",
        resume_state=WorkflowState.DRAFT_READY,
        now=NOW,
    )
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.NEEDS_MEDICAL_REVISION
    assert manifest.side_state.resume_state is WorkflowState.DRAFT_READY
    assert first.reason == "Thiếu nguồn cho claim C01."

    resume_gate(project_dir, GateKind.MEDICAL, target=WorkflowState.DRAFT_READY, now=NOW)
    _advance_to_awaiting_medical_review(project_dir)

    second = reject_gate(
        project_dir,
        GateKind.MEDICAL,
        reviewer=REVIEWER,
        reason="Vẫn còn một câu chưa khớp claim.",
        resume_state=WorkflowState.DRAFT_READY,
        now=NOW,
    )
    assert first != second


def test_reject_gate_requires_non_blank_reason(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    with pytest.raises(Exception, match="reason"):
        reject_gate(
            project_dir,
            GateKind.MEDICAL,
            reviewer=REVIEWER,
            reason="   ",
            resume_state=WorkflowState.DRAFT_READY,
            now=NOW,
        )


def test_approve_video_hashes_render_manifest_and_mp4(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=NOW)

    record = approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=NOW)

    assert set(record.artifact_hashes) == {"renders/render-manifest.json", "renders/video.mp4"}
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.VIDEO_APPROVED


def test_reject_video_with_semantic_issue_must_resume_to_draft_ready_with_that_reason_class(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=NOW)

    reject_gate(
        project_dir,
        GateKind.VIDEO,
        reviewer=REVIEWER,
        reason="Phát hiện câu thoại sai claim khi xem lại video.",
        resume_state=WorkflowState.DRAFT_READY,
        now=NOW,
    )

    with pytest.raises(Exception, match=r"reason (class|code)"):
        resume_gate(project_dir, GateKind.VIDEO, target=WorkflowState.DRAFT_READY, now=NOW)

    resume_gate(
        project_dir,
        GateKind.VIDEO,
        target=WorkflowState.DRAFT_READY,
        reason_code="semantic_issue",
        now=NOW,
    )
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.DRAFT_READY


def test_reject_video_without_semantic_issue_resumes_to_production_in_progress(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=NOW)

    reject_gate(
        project_dir,
        GateKind.VIDEO,
        reviewer=REVIEWER,
        reason="Âm lượng chưa chuẩn hoá.",
        resume_state=WorkflowState.PRODUCTION_IN_PROGRESS,
        now=NOW,
    )
    resume_gate(project_dir, GateKind.VIDEO, target=WorkflowState.PRODUCTION_IN_PROGRESS, now=NOW)

    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.PRODUCTION_IN_PROGRESS
