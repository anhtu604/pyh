from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

import healthvideo.tts.pronunciation as pronunciation_module
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import (
    TransitionContext,
    TransitionError,
    transition_v2,
)
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.gate_review import (
    MEDICAL_APPROVAL_ARTIFACT,
    approve_gate,
    hash_reviewed_artifacts,
    medical_reviewed_paths,
    reject_gate,
    reopen_gate,
    resume_gate,
)
from tests.helpers import (
    advance_v2_project_to_video_review,
    align_fixture_script,
    create_v2_project_fixture,
)

REVIEWER = "BS Nguyễn Văn An"
NOW = datetime(2026, 9, 11, 9, 0, tzinfo=UTC)


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
    align_fixture_script(project_dir / "revisions/001", board)
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
        "assets/license-ledger.yaml",
        "profiles/pronunciation.vi.yaml",
        "asset:assets/evidence-r01.svg",
        "asset:assets/evidence-r01-crop.png",
        "asset:assets/test-logo.svg",
    }


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
        board["visual_budget_profile"] = "explain_first_v1"
        del board["visual_budget_override"]
    elif mutation == "bounds":
        board["visual_budget_override"]["chart_crop"]["max_percent"] += 1
    else:
        board["visual_budget_override"]["rationale"] += " Đã sửa."
    write_yaml_atomic(storyboard_path, board)

    revision = project_dir / "revisions/001"
    current = hash_reviewed_artifacts(medical_reviewed_paths(revision))
    assert current != record.artifact_hashes


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


def test_reject_gate_invalid_resume_state_leaves_no_record(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    manifest_path = project_dir / "project.yaml"
    original = manifest_path.read_bytes()
    active_revision = read_yaml(manifest_path)["active_revision"]

    with pytest.raises(TransitionError, match="not a valid exit"):
        reject_gate(
            project_dir,
            GateKind.MEDICAL,
            reviewer=REVIEWER,
            reason="Cần sửa bằng chứng.",
            resume_state=WorkflowState.EVIDENCE_READY,
            now=NOW,
        )

    reviews = project_dir / "revisions" / active_revision / "reviews" / "medical"
    assert not list(reviews.glob("*-rejected*.yaml"))
    assert manifest_path.read_bytes() == original
    assert read_yaml(manifest_path)["state"] == "awaiting_medical_review"


def test_approve_video_hashes_render_manifest_and_mp4(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=NOW)

    record = approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=NOW)

    assert set(record.artifact_hashes) == {
        "renders/render-manifest.json",
        "renders/video.mp4",
        "posts/posts.yaml",
    }
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


def _approved_project(tmp_path: Path, *, video: bool = False) -> Path:
    project = create_v2_project_fixture(
        tmp_path, state=WorkflowState.DRAFT_READY if video else WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    if video:
        advance_v2_project_to_video_review(project, now=NOW)
        approve_gate(project, GateKind.VIDEO, reviewer=REVIEWER, now=NOW)
    else:
        approve_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    return project


@pytest.mark.parametrize("video", [False, True])
def test_reopen_preserves_approval_bytes_and_prior_hashes(tmp_path: Path, video: bool) -> None:
    project = _approved_project(tmp_path, video=video)
    revision = project / "revisions/001"
    old = {kind.value: (revision / f"reviews/{kind.value}-approval.yaml").read_bytes()
           for kind in GateKind if kind is GateKind.MEDICAL or video}
    prior = read_yaml(revision / MEDICAL_APPROVAL_ARTIFACT)["artifact_hashes"]
    record = reopen_gate(
        project, GateKind.MEDICAL, reviewer=REVIEWER, reason="Revise storyboard",
        changed=["storyboard/storyboard.yaml"], resume_state=WorkflowState.DRAFT_READY, now=NOW,
    )
    manifest = ProjectManifestV2.model_validate(read_yaml(project / "project.yaml"))
    assert manifest.state is WorkflowState.NEEDS_MEDICAL_REVISION
    assert manifest.side_state.resume_state is WorkflowState.DRAFT_READY
    assert manifest.side_state.reason_code.startswith("medical_reopen:")
    assert record.prior_approval_hashes == prior
    assert record.invalidation_reasons == sorted(record.invalidation_reasons)
    for kind, content in old.items():
        assert not (revision / f"reviews/{kind}-approval.yaml").exists()
        assert (revision / record.superseded_approvals[kind]).read_bytes() == content
    assert len(list((revision / "reviews/medical").glob("*-reopened.yaml"))) == 1


@pytest.mark.parametrize(
    ("kind", "changed", "resume", "match"),
    [
        (GateKind.MEDICAL, ["renders/video.mp4"], WorkflowState.DRAFT_READY, "medical re-review: video"),
        (GateKind.MEDICAL, ["storyboard/storyboard.yaml"], WorkflowState.EVIDENCE_READY, "not a valid exit"),
        (GateKind.VIDEO, ["storyboard/storyboard.yaml"], WorkflowState.DRAFT_READY, "only the medical"),
        *[(GateKind.MEDICAL, [path], WorkflowState.DRAFT_READY, "POSIX path")
          for path in ["../script.yaml", "/script.yaml", "C:/script.yaml", "a\\b", "", "."]],
        (GateKind.MEDICAL, [], WorkflowState.DRAFT_READY, "nonempty"),
    ],
)
def test_reopen_refusal_writes_nothing(tmp_path: Path, kind, changed, resume, match: str) -> None:
    project = _approved_project(tmp_path)
    before = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match=match):
        reopen_gate(project, kind, reviewer=REVIEWER, reason="Revise", changed=changed,
                    resume_state=resume, now=NOW)
    assert {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()} == before


def test_reopen_refuses_pre_gate_state(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    with pytest.raises(ValueError, match="awaiting_medical_review"):
        reopen_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, reason="Revise",
                    changed=["script/script.yaml"], resume_state=WorkflowState.DRAFT_READY, now=NOW)


def test_reopen_resume_resubmit_and_approve(tmp_path: Path) -> None:
    from healthvideo.workflows.draft import submit_draft, submit_medical_review

    project = _approved_project(tmp_path)
    revision = project / "revisions/001"
    record = reopen_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, reason="Revise",
                         changed=["storyboard/storyboard.yaml"],
                         resume_state=WorkflowState.DRAFT_READY, now=NOW)
    resume_gate(project, GateKind.MEDICAL, target=WorkflowState.DRAFT_READY, now=NOW)
    board = read_yaml(revision / "storyboard/storyboard.yaml")
    board["scenes"][1]["anatomy"]["motion"] += " Revised draft."
    board_file = tmp_path / "new-board.yaml"
    write_yaml_atomic(board_file, board)
    submit_draft(project, revision / "script/script.yaml", board_file,
                 revision / "assets/asset-manifest.yaml")
    submit_medical_review(project)
    approval = approve_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    assert approval.artifact_hashes != record.prior_approval_hashes
    assert (revision / MEDICAL_APPROVAL_ARTIFACT).is_file()
    assert (revision / record.superseded_approvals["medical"]).is_file()


def test_reopen_collision_keeps_existing_history(tmp_path: Path) -> None:
    project = _approved_project(tmp_path)
    revision = project / "revisions/001"
    directory = revision / "reviews/medical"
    directory.mkdir()
    timestamp = NOW.astimezone().strftime("%Y%m%dT%H%M%S%f")
    for suffix in ("superseded-approval", "reopened"):
        (directory / f"{timestamp}-{suffix}.yaml").write_bytes(b"existing audit history")
    original = (revision / MEDICAL_APPROVAL_ARTIFACT).read_bytes()
    record = reopen_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, reason="Revise",
                         changed=["storyboard/storyboard.yaml"],
                         resume_state=WorkflowState.DRAFT_READY, now=NOW)
    assert record.superseded_approvals["medical"].endswith("-superseded-approval-1.yaml")
    assert (revision / record.superseded_approvals["medical"]).read_bytes() == original
    assert (directory / f"{timestamp}-reopened-1.yaml").is_file()
    for suffix in ("superseded-approval", "reopened"):
        assert (directory / f"{timestamp}-{suffix}.yaml").read_bytes() == b"existing audit history"


def test_reopen_missing_current_approval_writes_nothing(tmp_path: Path) -> None:
    project = _approved_project(tmp_path)
    revision = project / "revisions/001"
    (revision / MEDICAL_APPROVAL_ARTIFACT).unlink()
    original = (project / "project.yaml").read_bytes()
    with pytest.raises(FileNotFoundError):
        reopen_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, reason="Revise",
                    changed=["storyboard/storyboard.yaml"],
                    resume_state=WorkflowState.DRAFT_READY, now=NOW)
    assert (project / "project.yaml").read_bytes() == original
    assert not (revision / "reviews/medical").exists()
