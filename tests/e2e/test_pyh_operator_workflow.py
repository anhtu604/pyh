"""Offline operator acceptance across both explicit doctor gates."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.asset_manifest import AssetManifest
from healthvideo.domain.author import AuthorBrief
from healthvideo.domain.evidence import EvidenceClaim, EvidenceQuestion, SourceRecord
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.invalidation import (
    ArtifactChange,
    InvalidationLevel,
    evaluate_invalidation,
)
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.domain.topic import TopicCard
from healthvideo.storage.files import canonical_json_hash, read_yaml, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.author import save_author_brief
from healthvideo.workflows.create_project_v2 import create_project_v2
from healthvideo.workflows.draft import submit_draft, submit_medical_review
from healthvideo.workflows.evidence import build_evidence_ledger, record_question
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.operator import OperatorActionKind, get_next_action
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review_html import render_medical_packet, render_video_packet
from healthvideo.workflows.topic import select_topic

FROZEN = datetime(2026, 9, 10, 7, 30, tzinfo=UTC)
SOURCE = Path("tests/fixtures/golden-project-v2/revisions/001")


def _fake_render(argv: list[str]) -> int:
    output = Path(argv[argv.index("--output") + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"synthetic-video-for-operator-test")
    return 0


def _complete_orientation(project: Path) -> None:
    manifest_path = project / "project.yaml"
    orientation_dir = project / "revisions/001/orientation"
    scope = {"synthetic_test_record": True, "topic": "muối"}
    write_yaml_atomic(orientation_dir / "scope.yaml", scope)
    selected = ProjectManifestV2.model_validate(read_yaml(manifest_path))
    researching = transition_v2(
        selected,
        WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS,
        TransitionContext(
            "001",
            canonical_json_hash(scope),
            frozenset({"orientation/scope.yaml"}),
        ),
    )
    write_yaml_atomic(manifest_path, researching.model_dump(mode="json"))

    completed = {"synthetic_test_record": True, "run_id": "run-001"}
    write_yaml_atomic(orientation_dir / "completed/run-001.yaml", completed)
    awaiting = transition_v2(
        researching,
        WorkflowState.AWAITING_EDITORIAL_DIRECTION,
        TransitionContext(
            "001",
            canonical_json_hash(completed),
            frozenset({"orientation/completed/<run_id>.yaml"}),
        ),
    )
    write_yaml_atomic(manifest_path, awaiting.model_dump(mode="json"))


def test_pyh_golden_stops_at_both_human_gates(tmp_path: Path) -> None:
    project = create_project_v2(
        tmp_path, "muoi-va-huyet-ap", "Ăn mặn và tăng huyết áp", now=FROZEN
    )
    revision = project / "revisions" / "001"
    card = TopicCard.model_validate(read_yaml(SOURCE / "topic" / "card.yaml"))
    select_topic(project, card, now=FROZEN)
    _complete_orientation(project)
    brief = AuthorBrief.model_validate(read_yaml(SOURCE / "author" / "brief.yaml"))
    save_author_brief(project, brief, confirm=True, now=FROZEN)
    record_question(
        project,
        EvidenceQuestion(
            patient_population="Người trưởng thành",
            intervention="Giảm muối",
            outcome="Huyết áp",
            search_keywords=["sodium blood pressure"],
        ),
        now=FROZEN,
    )
    frozen_ledger = read_yaml(SOURCE / "evidence" / "ledger.yaml")
    build_evidence_ledger(
        project,
        [EvidenceClaim.model_validate(item) for item in frozen_ledger["claims"]],
        [SourceRecord.model_validate(item) for item in frozen_ledger["records"]],
        now=FROZEN,
    )
    shutil.copy2(SOURCE / "assets" / "evidence-r01.svg", revision / "assets")
    submit_draft(
        project,
        SOURCE / "script/script.yaml",
        SOURCE / "storyboard/storyboard.yaml",
        SOURCE / "assets/asset-manifest.yaml",
    )
    submit_medical_review(project)

    assert "Gói duyệt y khoa" in render_medical_packet(revision)
    assert get_next_action(project).kind is OperatorActionKind.AWAIT_MEDICAL_APPROVAL
    with pytest.raises(ValueError):
        produce_project(project, SilentTTS(), _fake_render)
    approve_gate(
        project, GateKind.MEDICAL, reviewer="BS Test", note="fixture", now=FROZEN
    )
    produce_project(project, SilentTTS(), _fake_render)
    assert "Gói duyệt video" in render_video_packet(revision)
    assert get_next_action(project).kind is OperatorActionKind.AWAIT_VIDEO_APPROVAL
    with pytest.raises(ValueError):
        package_project(project)
    approve_gate(
        project, GateKind.VIDEO, reviewer="BS Test", note="fixture", now=FROZEN
    )
    package_project(project)
    assert get_next_action(project).kind is OperatorActionKind.COMPLETE


def test_post_approval_invalidation_routes_to_existing_gates() -> None:
    manifest = AssetManifest.model_validate(
        read_yaml(SOURCE / "assets" / "asset-manifest.yaml")
    )
    cases = {
        "script/script.yaml": (
            InvalidationLevel.MEDICAL,
            WorkflowState.NEEDS_MEDICAL_REVISION,
        ),
        "evidence/ledger.yaml": (
            InvalidationLevel.MEDICAL,
            WorkflowState.NEEDS_MEDICAL_REVISION,
        ),
        "assets/evidence-r01.svg": (
            InvalidationLevel.MEDICAL,
            WorkflowState.NEEDS_MEDICAL_REVISION,
        ),
        "audio/narration.wav": (
            InvalidationLevel.VIDEO,
            WorkflowState.NEEDS_PRODUCTION_REVISION,
        ),
        "timing/words.json": (
            InvalidationLevel.VIDEO,
            WorkflowState.NEEDS_PRODUCTION_REVISION,
        ),
        "renders/video.mp4": (
            InvalidationLevel.VIDEO,
            WorkflowState.NEEDS_PRODUCTION_REVISION,
        ),
        "unknown/file.bin": (
            InvalidationLevel.MEDICAL,
            WorkflowState.NEEDS_MEDICAL_REVISION,
        ),
    }
    for path, (level, state) in cases.items():
        decision = evaluate_invalidation(
            [ArtifactChange(Path(path), frozenset())], manifest
        )
        assert (decision.level, decision.target_state) == (level, state)
