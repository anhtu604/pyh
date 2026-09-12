from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from healthvideo.domain.agent_review import AgentReviewIssue, AgentReviewResponse
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.storage.files import canonical_json_hash, read_yaml, write_yaml_atomic
from healthvideo.workflows.agent_review import (
    complete_second_model_review,
    request_second_model_review,
)
from tests.helpers import create_v2_project_fixture

NOW = datetime(2026, 9, 12, 11, 5, 23, 123456, tzinfo=UTC)


def _project(tmp_path: Path, state: WorkflowState = WorkflowState.DRAFT_READY) -> Path:
    project = create_v2_project_fixture(tmp_path)
    data = read_yaml(project / "project.yaml")
    data["state"] = state.value
    data["side_state"] = None
    write_yaml_atomic(project / "project.yaml", data)
    return project


def _manifest(project: Path) -> ProjectManifestV2:
    return ProjectManifestV2.model_validate(read_yaml(project / "project.yaml"))


def _response(request_dir: Path, **changes) -> AgentReviewResponse:
    request = read_yaml(request_dir / "request.yaml")
    data = {
        "request_id": request["request_id"],
        "revision": request["revision"],
        "request_hash": canonical_json_hash(request),
        "reviewer": "Second model",
        "model": "fixture",
        "reviewed_at": NOW,
        "issues": [],
        "summary": "Reviewed fixture",
    }
    data.update(changes)
    return AgentReviewResponse(**data)


@pytest.mark.parametrize(
    "source_state", [WorkflowState.EVIDENCE_READY, WorkflowState.DRAFT_READY]
)
def test_request_creates_bounded_immutable_packet_and_pauses(
    tmp_path: Path, source_state: WorkflowState
) -> None:
    project = _project(tmp_path, source_state)
    request_dir = request_second_model_review(
        project, reason_code="conflicting_evidence", now=NOW
    )
    request = read_yaml(request_dir / "request.yaml")
    packet = (request_dir / "packet.xml").read_text(encoding="utf-8")
    changed = _manifest(project)
    assert changed.state is WorkflowState.AWAITING_SECOND_MODEL_REVIEW
    assert changed.side_state.resume_state is source_state
    assert request["source_state"] == source_state.value
    assert request["artifact_hashes"]
    assert "author/brief.yaml" in request["artifact_hashes"]
    assert "evidence/ledger.yaml" in request["artifact_hashes"]
    assert "audio/" not in packet and "publish/" not in packet
    assert not (request_dir / "response.yaml").exists()
    assert not list((project / "revisions" / "001" / "reviews").glob("*approval*"))


def test_invalid_request_state_has_no_mutation(tmp_path: Path) -> None:
    project = _project(tmp_path, WorkflowState.IDEA)
    before = (project / "project.yaml").read_bytes()
    with pytest.raises(ValueError):
        request_second_model_review(project, reason_code="risk", now=NOW)
    assert (project / "project.yaml").read_bytes() == before
    assert not (project / "revisions" / "001" / "handoffs" / "second-model").exists()


def test_clean_response_resumes_and_second_cycle_preserves_first(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    first = request_second_model_review(project, reason_code="risk", now=NOW)
    complete_second_model_review(project, _response(first), now=NOW)
    assert _manifest(project).state is WorkflowState.DRAFT_READY
    before = {p.name: p.read_bytes() for p in first.iterdir()}
    second = request_second_model_review(
        project, reason_code="new_risk", now=NOW + timedelta(microseconds=1)
    )
    assert second != first
    complete_second_model_review(
        project, _response(second), now=NOW + timedelta(microseconds=1)
    )
    assert {p.name: p.read_bytes() for p in first.iterdir()} == before
    assert not list((project / "revisions" / "001" / "reviews").glob("*approval*"))


def test_blocking_response_routes_to_medical_revision(tmp_path: Path) -> None:
    project = _project(tmp_path, WorkflowState.EVIDENCE_READY)
    request_dir = request_second_model_review(project, reason_code="risk", now=NOW)
    issue = AgentReviewIssue(
        severity="blocking",
        artifact="evidence/ledger.yaml",
        problem="Mismatch",
        suggested_patch="Recheck claim",
    )
    complete_second_model_review(
        project, _response(request_dir, issues=[issue]), now=NOW
    )
    changed = _manifest(project)
    assert changed.state is WorkflowState.NEEDS_MEDICAL_REVISION
    assert changed.side_state.resume_state is WorkflowState.RESEARCH_IN_PROGRESS
    assert (request_dir / "response.yaml").is_file()


def test_stale_source_and_wrong_binding_fail_closed(tmp_path: Path) -> None:
    project = _project(tmp_path)
    request_dir = request_second_model_review(project, reason_code="risk", now=NOW)
    response = _response(request_dir)
    for change in ({"request_hash": "0" * 64}, {"revision": "002"}):
        with pytest.raises(ValueError):
            complete_second_model_review(
                project, response.model_copy(update=change), now=NOW
            )
    (project / "revisions" / "001" / "evidence" / "ledger.yaml").write_text(
        "changed: true\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="stale"):
        complete_second_model_review(project, response, now=NOW)
    assert _manifest(project).state is WorkflowState.AWAITING_SECOND_MODEL_REVIEW
    assert not (request_dir / "response.yaml").exists()


def test_changed_packet_fails_closed(tmp_path: Path) -> None:
    project = _project(tmp_path)
    request_dir = request_second_model_review(project, reason_code="risk", now=NOW)
    response = _response(request_dir)
    (request_dir / "packet.xml").write_text("altered", encoding="utf-8")
    with pytest.raises(ValueError, match="packet"):
        complete_second_model_review(project, response, now=NOW)
    assert _manifest(project).state is WorkflowState.AWAITING_SECOND_MODEL_REVIEW


def test_request_rejects_duplicate_while_awaiting_and_keeps_first_bytes(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    request_dir = request_second_model_review(project, reason_code="risk", now=NOW)
    before = {path.name: path.read_bytes() for path in request_dir.iterdir()}
    with pytest.raises(ValueError, match="evidence_ready or draft_ready"):
        request_second_model_review(project, reason_code="risk", now=NOW)
    assert {path.name: path.read_bytes() for path in request_dir.iterdir()} == before


def test_response_for_another_request_cannot_complete_current_one(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    first = request_second_model_review(project, reason_code="risk", now=NOW)
    complete_second_model_review(project, _response(first), now=NOW)
    second = request_second_model_review(
        project, reason_code="new_risk", now=NOW + timedelta(microseconds=1)
    )
    with pytest.raises(ValueError):
        complete_second_model_review(project, _response(first), now=NOW)
    assert _manifest(project).state is WorkflowState.AWAITING_SECOND_MODEL_REVIEW
    assert not (second / "response.yaml").exists()


def test_blocking_draft_response_resumes_to_draft_after_revision(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    request_dir = request_second_model_review(project, reason_code="risk", now=NOW)
    issue = AgentReviewIssue(
        severity="blocking",
        artifact="script/script.yaml",
        problem="Mismatch",
        suggested_patch="Revise line",
    )
    complete_second_model_review(
        project, _response(request_dir, issues=[issue]), now=NOW
    )
    changed = _manifest(project)
    assert changed.state is WorkflowState.NEEDS_MEDICAL_REVISION
    assert changed.side_state.resume_state is WorkflowState.DRAFT_READY


def test_request_promotion_failure_keeps_state_and_no_partial_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    before = (project / "project.yaml").read_bytes()

    def fail_promotion(_source: Path, _destination: Path) -> None:
        raise OSError("injected promotion failure")

    monkeypatch.setattr(
        "healthvideo.workflows.agent_review.promote_directory_once", fail_promotion
    )
    with pytest.raises(OSError, match="injected"):
        request_second_model_review(project, reason_code="risk", now=NOW)
    assert (project / "project.yaml").read_bytes() == before
    assert not list(
        (project / "revisions" / "001" / "handoffs" / "second-model").iterdir()
    )


def test_response_write_failure_keeps_pending_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    request_dir = request_second_model_review(project, reason_code="risk", now=NOW)
    before = (project / "project.yaml").read_bytes()

    def fail_write(_path: Path, _payload: dict) -> None:
        raise OSError("injected response failure")

    monkeypatch.setattr(
        "healthvideo.workflows.agent_review.write_yaml_once", fail_write
    )
    with pytest.raises(OSError, match="injected"):
        complete_second_model_review(project, _response(request_dir), now=NOW)
    assert (project / "project.yaml").read_bytes() == before
    assert not (request_dir / "response.yaml").exists()


@pytest.mark.parametrize("blocking", [False, True])
def test_manifest_write_failure_can_retry_identical_immutable_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, blocking: bool
) -> None:
    from healthvideo.workflows import agent_review

    project = _project(tmp_path)
    request_dir = request_second_model_review(project, reason_code="risk", now=NOW)
    issues = (
        [
            AgentReviewIssue(
                severity="blocking",
                artifact="script/script.yaml",
                problem="Mismatch",
                suggested_patch="Revise line",
            )
        ]
        if blocking
        else []
    )
    response = _response(request_dir, issues=issues)
    original_write = agent_review.write_yaml_atomic

    def fail_manifest(_path: Path, _payload: dict) -> None:
        raise OSError("injected manifest failure")

    monkeypatch.setattr(agent_review, "write_yaml_atomic", fail_manifest)
    with pytest.raises(OSError, match="injected"):
        complete_second_model_review(project, response, now=NOW)
    assert _manifest(project).state is WorkflowState.AWAITING_SECOND_MODEL_REVIEW
    persisted = (request_dir / "response.yaml").read_bytes()

    monkeypatch.setattr(agent_review, "write_yaml_atomic", original_write)
    with pytest.raises((FileExistsError, ValueError)):
        complete_second_model_review(
            project, response.model_copy(update={"summary": "different"}), now=NOW
        )
    changed = complete_second_model_review(project, response, now=NOW)
    assert changed.state is (
        WorkflowState.NEEDS_MEDICAL_REVISION if blocking else WorkflowState.DRAFT_READY
    )
    assert (request_dir / "response.yaml").read_bytes() == persisted
