from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from healthvideo.domain.revision import RevisionRecord

CREATED_AT = datetime(2026, 9, 10, 7, 30, tzinfo=UTC)


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "revision": "002",
        "parent_revision": "001",
        "reason": "Sửa luận điểm",
        "created_at": CREATED_AT,
    }
    payload.update(overrides)
    return payload


def test_revision_record_holds_the_documented_fields() -> None:
    record = RevisionRecord(**_payload())

    assert record.schema_version == "2.0"
    assert record.revision == "002"
    assert record.parent_revision == "001"
    assert record.reason == "Sửa luận điểm"
    assert record.created_at == CREATED_AT


def test_revision_record_is_frozen() -> None:
    record = RevisionRecord(**_payload())

    with pytest.raises(ValidationError):
        record.reason = "Khác"


def test_revision_record_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        RevisionRecord(**_payload(unexpected_field="nope"))


@pytest.mark.parametrize("field", ["revision", "parent_revision"])
@pytest.mark.parametrize("bad_value", ["2", "0002", "abc", ""])
def test_revision_ids_must_be_exactly_three_digits(field: str, bad_value: str) -> None:
    with pytest.raises(ValidationError):
        RevisionRecord(**_payload(**{field: bad_value}))


@pytest.mark.parametrize("blank_reason", ["", "   ", "\t\n"])
def test_reason_cannot_be_blank_or_whitespace(blank_reason: str) -> None:
    with pytest.raises(ValidationError):
        RevisionRecord(**_payload(reason=blank_reason))


def test_created_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        RevisionRecord(**_payload(created_at=CREATED_AT.replace(tzinfo=None)))
