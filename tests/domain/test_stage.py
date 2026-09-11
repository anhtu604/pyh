from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from healthvideo.domain.stage import StageManifest, StageStatus

INPUT_HASH = "a" * 64
OUTPUT_HASH = "b" * 64
STARTED_AT = datetime(2026, 9, 10, 7, 30, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 9, 10, 7, 31, tzinfo=UTC)

COMPLETE_WITHOUT_OUTPUT = {
    "stage": "evidence_ledger",
    "status": StageStatus.COMPLETE,
    "input_hash": INPUT_HASH,
    "tool_version": "1.0.0",
    "agent": "claude",
    "model": "claude-sonnet-5",
    "started_at": STARTED_AT,
    "estimated_input_tokens": 100,
    "estimated_output_tokens": 200,
}


def _complete_payload(**overrides: object) -> dict[str, object]:
    payload = {
        **COMPLETE_WITHOUT_OUTPUT,
        "output_hash": OUTPUT_HASH,
        "completed_at": COMPLETED_AT,
    }
    payload.update(overrides)
    return payload


def test_complete_stage_requires_output_hash_and_completed_at() -> None:
    with pytest.raises(ValidationError):
        StageManifest(**COMPLETE_WITHOUT_OUTPUT)


def test_complete_stage_accepts_output_hash_and_completed_at() -> None:
    manifest = StageManifest(**_complete_payload())

    assert manifest.status is StageStatus.COMPLETE
    assert manifest.output_hash == OUTPUT_HASH
    assert manifest.completed_at == COMPLETED_AT


def test_running_stage_forbids_output_hash() -> None:
    payload = {
        **COMPLETE_WITHOUT_OUTPUT,
        "status": StageStatus.RUNNING,
        "output_hash": OUTPUT_HASH,
    }

    with pytest.raises(ValidationError, match="output_hash"):
        StageManifest(**payload)


def test_running_stage_does_not_require_output_hash_or_completed_at() -> None:
    manifest = StageManifest(**{**COMPLETE_WITHOUT_OUTPUT, "status": StageStatus.RUNNING})

    assert manifest.output_hash is None
    assert manifest.completed_at is None


@pytest.mark.parametrize("bad_hash", ["A" * 64, "0" * 63, "0" * 65, "not-a-hash", ""])
def test_input_hash_must_be_lowercase_sha256_hex(bad_hash: str) -> None:
    payload = {
        **COMPLETE_WITHOUT_OUTPUT,
        "status": StageStatus.RUNNING,
        "input_hash": bad_hash,
    }

    with pytest.raises(ValidationError):
        StageManifest(**payload)


def test_output_hash_must_be_lowercase_sha256_hex_when_present() -> None:
    payload = _complete_payload(output_hash="Z" * 64)

    with pytest.raises(ValidationError):
        StageManifest(**payload)


def test_started_at_must_be_timezone_aware() -> None:
    payload = {
        **COMPLETE_WITHOUT_OUTPUT,
        "status": StageStatus.RUNNING,
        "started_at": STARTED_AT.replace(tzinfo=None),
    }

    with pytest.raises(ValidationError, match="timezone"):
        StageManifest(**payload)


def test_completed_at_must_be_timezone_aware() -> None:
    payload = _complete_payload(completed_at=COMPLETED_AT.replace(tzinfo=None))

    with pytest.raises(ValidationError, match="timezone"):
        StageManifest(**payload)


def test_completed_at_cannot_precede_started_at() -> None:
    payload = _complete_payload(completed_at=datetime(2026, 9, 10, 7, 0, tzinfo=UTC))

    with pytest.raises(ValidationError, match="completed_at"):
        StageManifest(**payload)


@pytest.mark.parametrize(
    "field", ["estimated_input_tokens", "estimated_output_tokens"]
)
def test_token_estimates_cannot_be_negative(field: str) -> None:
    payload = {**COMPLETE_WITHOUT_OUTPUT, "status": StageStatus.RUNNING, field: -1}

    with pytest.raises(ValidationError):
        StageManifest(**payload)


@pytest.mark.parametrize("field", ["stage", "tool_version", "agent", "model"])
def test_identifying_fields_cannot_be_blank(field: str) -> None:
    payload = {**COMPLETE_WITHOUT_OUTPUT, "status": StageStatus.RUNNING, field: "   "}

    with pytest.raises(ValidationError):
        StageManifest(**payload)


def test_stage_manifest_is_frozen() -> None:
    manifest = StageManifest(**_complete_payload())

    with pytest.raises(ValidationError):
        manifest.status = StageStatus.FAILED


def test_stage_manifest_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        StageManifest(**_complete_payload(unexpected_field="nope"))
