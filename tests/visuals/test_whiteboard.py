from pathlib import Path

import pytest

from healthvideo.domain.brand import load_brand_profile
from healthvideo.visuals.whiteboard import (
    WhiteboardPayload,
    WhiteboardTemplate,
    render_whiteboard,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def brand():
    return load_brand_profile(ROOT / "profiles/brand.vi.yaml")


@pytest.mark.parametrize(
    ("template", "labels"),
    [
        (WhiteboardTemplate.CONNECTOR, ()),
        (WhiteboardTemplate.COMPARISON, ("A < B", "C & D")),
        (WhiteboardTemplate.THREE_STEP, ("Một", "Hai", "Ba")),
        (WhiteboardTemplate.CALLOUT, ("Điểm chính",)),
    ],
)
def test_whiteboard_is_safe_and_deterministic(brand, template, labels) -> None:
    payload = WhiteboardPayload(labels=labels)
    svg = render_whiteboard(brand, template, payload)
    assert svg == render_whiteboard(brand, template, payload)
    assert svg.endswith(b"\n")
    content = svg.replace(b'xmlns="http://www.w3.org/2000/svg"', b"")
    for forbidden in (b"<script", b"<filter", b"href=", b"http:", b"https:", b"foreignObject", b"<image"):
        assert forbidden not in content


def test_whiteboard_escapes_operator_text(brand) -> None:
    svg = render_whiteboard(
        brand,
        WhiteboardTemplate.COMPARISON,
        WhiteboardPayload(labels=("A < B", "C & D")),
    )
    assert b"A &lt; B" in svg
    assert b"C &amp; D" in svg


def test_whiteboard_rejects_bad_payload_shape_and_control_text(brand) -> None:
    with pytest.raises(ValueError, match="comparison requires exactly 2 labels"):
        render_whiteboard(brand, WhiteboardTemplate.COMPARISON, WhiteboardPayload())
    with pytest.raises(ValueError, match="control"):
        WhiteboardPayload(labels=("bad\x00text",))
