from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from healthvideo.domain.ai_clip import AIClipProvenance


def provenance_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "provider": "google_vertex_ai",
        "model": "veo-3.1-fast-generate-001",
        "prompt": "  Minh họa bàn tay chọn món ít muối.  ",
        "requested_seed": 42,
        "generated_at": datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        "request_sha256": "a" * 64,
        "output_sha256": "b" * 64,
        "mime_type": "video/mp4",
        "container": "mp4",
        "width": 1080,
        "height": 1920,
        "source_fps": 24,
        "duration_ms": 4000,
        "source_frame_count": 96,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("duration_ms", "source_frame_count"),
    [(4000, 96), (6000, 144), (8000, 192)],
)
def test_ai_clip_provenance_accepts_exact_media_pairs(
    duration_ms: int, source_frame_count: int
) -> None:
    provenance = AIClipProvenance.model_validate(
        provenance_payload(
            duration_ms=duration_ms, source_frame_count=source_frame_count
        )
    )

    assert provenance.prompt == "  Minh họa bàn tay chọn món ít muối.  "
    assert provenance.duration_ms == duration_ms
    assert provenance.source_frame_count == source_frame_count


@pytest.mark.parametrize(
    "overrides",
    [
        {"duration_ms": 4000, "source_frame_count": 144},
        {"width": 720},
        {"height": 1280},
        {"source_fps": 30},
        {"mime_type": "video/webm"},
        {"container": "webm"},
    ],
)
def test_ai_clip_provenance_rejects_media_contract_mismatch(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AIClipProvenance.model_validate(provenance_payload(**overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        {"model": "  "},
        {"prompt": "\t"},
        {"generated_at": "2026-09-14T12:00:00"},
        {"request_sha256": "A" * 64},
        {"output_sha256": "b" * 63},
        {"unexpected": "field"},
    ],
)
def test_ai_clip_provenance_rejects_unreviewable_metadata(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AIClipProvenance.model_validate(provenance_payload(**overrides))


def test_ai_clip_provenance_allows_missing_requested_seed_and_is_frozen() -> None:
    payload = provenance_payload()
    payload.pop("requested_seed")
    provenance = AIClipProvenance.model_validate(payload)

    assert provenance.requested_seed is None
    with pytest.raises(ValidationError):
        provenance.duration_ms = 6000  # type: ignore[misc]
