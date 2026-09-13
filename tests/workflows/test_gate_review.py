from datetime import UTC, datetime
from pathlib import Path

import pytest

import healthvideo.tts.pronunciation as pronunciation_module
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.gate_review import (
    MEDICAL_APPROVAL_ARTIFACT,
    approve_gate,
    medical_reviewed_paths,
    reject_gate,
    resume_gate,
)
from tests.helpers import advance_v2_project_to_video_review, create_v2_project_fixture

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
