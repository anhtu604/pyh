"""Offline operator acceptance across both explicit doctor gates."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.asset_manifest import AssetManifest
from healthvideo.domain.evidence import EvidenceClaim, EvidenceQuestion, SourceRecord
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.invalidation import (
    ArtifactChange,
    InvalidationLevel,
    evaluate_invalidation,
)
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.topic import TopicCard
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.create_project_v2 import create_project_v2
from healthvideo.workflows.draft import submit_draft, submit_medical_review
from healthvideo.workflows.evidence import build_evidence_ledger, record_question
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.operator import OperatorActionKind, get_next_action
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review_html import render_medical_packet, render_video_packet
from healthvideo.workflows.topic import select_topic
from tests.helpers import (
    write_explainer_fixture,
    write_posts_fixture,
)

FROZEN = datetime(2026, 9, 10, 7, 30, tzinfo=UTC)
SOURCE = Path("tests/fixtures/golden-project-v2/revisions/001")


def test_selected_topic_research_keeps_both_doctor_gates_closed(tmp_path):
    project = create_project_v2(tmp_path, "research-test", "Synthetic topic", now=FROZEN)
    select_topic(project, TopicCard.model_validate(read_yaml(SOURCE / "topic/card.yaml")))
    action = get_next_action(project)
    assert action.kind is OperatorActionKind.RESEARCH
    assert "step evidence-search" in action.message
    record_question(project, EvidenceQuestion(
        patient_population="adults", intervention="salt", outcome="BP",
        search_keywords=["sodium blood pressure"],
    ))
    for gate in (GateKind.MEDICAL, GateKind.VIDEO):
        with pytest.raises(ValueError):
            approve_gate(project, gate, reviewer="Test reviewer", now=FROZEN)
    with pytest.raises(ValueError):
        package_project(project)
    revision = project / "revisions/001"
    assert not list((revision / "reviews").glob("*"))
    assert not (revision / "publish/manifest.json").exists()
    assert read_yaml(project / "project.yaml")["state"] == "research_in_progress"


def _fake_render(argv: list[str]) -> int:
    output = Path(argv[argv.index("--output") + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"synthetic-video-for-operator-test")
    return 0


def test_pyh_golden_stops_at_both_human_gates(tmp_path: Path) -> None:
    project = create_project_v2(
        tmp_path, "muoi-va-huyet-ap", "Ăn mặn và tăng huyết áp", now=FROZEN
    )
    revision = project / "revisions" / "001"
    manifest = read_yaml(project / "project.yaml")
    write_yaml_atomic(project / "project.yaml", manifest)
    card = TopicCard.model_validate(read_yaml(SOURCE / "topic" / "card.yaml"))
    select_topic(project, card, now=FROZEN)
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
    write_explainer_fixture(revision, frozen_ledger["claims"][0]["id"])
    build_evidence_ledger(
        project,
        [EvidenceClaim.model_validate(item) for item in frozen_ledger["claims"]],
        [SourceRecord.model_validate(item) for item in frozen_ledger["records"]],
        now=FROZEN,
    )
    shutil.copytree(SOURCE / "assets", revision / "assets", dirs_exist_ok=True)
    board = read_yaml(SOURCE / "storyboard/storyboard.yaml")
    lines = read_yaml(SOURCE / "script/script.yaml")["lines"]
    for scene, line in zip(board["scenes"], lines, strict=True):
        assert scene["narration"] == line["text"]
        scene["script_line_id"] = line["id"]
    board_path = tmp_path / "bound-storyboard.yaml"
    write_yaml_atomic(board_path, board)
    submit_draft(
        project,
        SOURCE / "script/script.yaml",
        board_path,
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
    write_posts_fixture(revision)
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
