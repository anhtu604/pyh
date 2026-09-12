from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from healthvideo.domain.agent_review import (
    AgentReviewIssue,
    AgentReviewRequest,
    AgentReviewResponse,
)


def _response(**changes):
    data = {
        "request_id": "20260912T110523123456Z-a91cf22d4b30",
        "revision": "001",
        "request_hash": "a" * 64,
        "reviewer": "Claude",
        "model": "sonnet",
        "reviewed_at": datetime(2026, 9, 12, tzinfo=UTC),
        "issues": [],
        "summary": "No blocking issue",
    }
    data.update(changes)
    return AgentReviewResponse(**data)


def test_review_response_rejects_blank_identity_and_naive_time() -> None:
    for change in (
        {"reviewer": " "},
        {"model": " "},
        {"reviewed_at": datetime(2026, 9, 12, tzinfo=UTC).replace(tzinfo=None)},
    ):
        with pytest.raises(ValidationError):
            _response(**change)


def test_issue_severity_is_bounded_and_patch_oriented() -> None:
    for severity in ("info", "warning", "blocking"):
        issue = AgentReviewIssue(
            severity=severity,
            artifact="script/script.yaml",
            problem="Claim wording needs checking",
            suggested_patch="Revise only line C01",
        )
        assert _response(issues=[issue]).issues[0].severity == severity
    with pytest.raises(ValidationError):
        AgentReviewIssue(
            severity="approved",
            artifact="script/script.yaml",
            problem="x",
            suggested_patch="y",
        )


def test_review_response_has_versioned_json_schema() -> None:
    schema = AgentReviewResponse.model_json_schema()
    assert "schema_version" in schema["properties"]
    assert "AgentReviewIssue" in schema["$defs"]


def test_request_rejects_undeclared_source_path() -> None:
    with pytest.raises(ValidationError):
        AgentReviewRequest(
            request_id="20260912T110523123456Z-a91cf22d4b30",
            project_slug="fixture",
            revision="001",
            reason_code="risk",
            created_at=datetime(2026, 9, 12, tzinfo=UTC),
            source_state="draft_ready",
            artifact_hashes={
                "author/brief.yaml": "a" * 64,
                "evidence/ledger.yaml": "a" * 64,
                "../../secrets.yaml": "a" * 64,
            },
            packet_sha256="a" * 64,
        )
