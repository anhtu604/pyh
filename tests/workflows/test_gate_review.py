from datetime import UTC, datetime
from pathlib import Path

import pytest

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
from tests.helpers import create_v2_project_fixture

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
        "asset:assets/evidence-r01.svg",
    }


def test_approve_medical_rejects_missing_semantic_asset_bytes(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    (project_dir / "revisions" / "001" / "assets" / "evidence-r01.svg").write_bytes(b"changed")

    with pytest.raises(Exception, match="sha256"):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)


def test_approve_medical_writes_record_once_and_advances_state(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)

    record = approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    approval_path = project_dir / "revisions" / "001" / MEDICAL_APPROVAL_ARTIFACT
    assert approval_path.is_file()
    assert read_yaml(approval_path)["reviewer"] == REVIEWER
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.MEDICALLY_APPROVED
    assert record.artifact_hashes

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
