from hashlib import sha256
from pathlib import Path

import pytest

from healthvideo.domain.brand import LogoVariant, load_brand_profile
from healthvideo.visuals.brand import render_phy_logo

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def brand():
    return load_brand_profile(ROOT / "profiles/brand.vi.yaml")


@pytest.mark.parametrize("variant", list(LogoVariant))
def test_phy_logo_is_safe_and_deterministic(brand, variant: LogoVariant) -> None:
    first = render_phy_logo(brand, variant)
    assert first == render_phy_logo(brand, variant)
    assert sha256(first).hexdigest() == sha256(render_phy_logo(brand, variant)).hexdigest()
    assert first.endswith(b"\n")
    content = first.replace(b'xmlns="http://www.w3.org/2000/svg"', b"")
    for forbidden in (
        b"<script",
        b"<filter",
        b"href=",
        b"http:",
        b"https:",
        b"foreignObject",
        b"<image",
        b"@font-face",
    ):
        assert forbidden not in content


def test_logo_variants_have_distinct_font_free_geometry(brand) -> None:
    outputs = {variant: render_phy_logo(brand, variant) for variant in LogoVariant}
    assert len(set(outputs.values())) == 3
    assert b"<text" not in outputs[LogoVariant.HORIZONTAL]
    assert b"phy-p-bubble" in outputs[LogoVariant.HORIZONTAL]
    assert b"phy-h-plus" in outputs[LogoVariant.HORIZONTAL]
    assert b"phy-y-check" in outputs[LogoVariant.HORIZONTAL]
    assert brand.colors.navy.encode() in outputs[LogoVariant.HORIZONTAL]
    assert brand.colors.yellow.encode() in outputs[LogoVariant.HORIZONTAL]


def test_logo_avoids_generic_health_motif_identifiers(brand) -> None:
    svg = render_phy_logo(brand, LogoVariant.HORIZONTAL).lower()
    for forbidden in (b"heartbeat", b"ecg", b"shield", b"dna", b"caduceus"):
        assert forbidden not in svg
