from hashlib import sha256
from pathlib import Path

import pytest

from healthvideo.domain.brand import LogoVariant, load_brand_profile
from healthvideo.visuals.brand import render_pyh_logo

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def brand(brand_profile_path):
    return load_brand_profile(brand_profile_path)


@pytest.mark.parametrize("variant", list(LogoVariant))
def test_pyh_logo_is_safe_and_deterministic(brand, variant: LogoVariant) -> None:
    first = render_pyh_logo(brand, variant)
    assert first == render_pyh_logo(brand, variant)
    assert sha256(first).hexdigest() == sha256(render_pyh_logo(brand, variant)).hexdigest()
    assert first.endswith(b"\n")
    content = first.replace(b'xmlns="http://www.w3.org/2000/svg"', b"")
    for forbidden in (
        b"<script",
        b"<filter",
        b"<mask",
        b"<clipPath",
        b"<style",
        b"<linearGradient",
        b"<radialGradient",
        b"href=",
        b"http:",
        b"https:",
        b"foreignObject",
        b"<image",
        b"@font-face",
    ):
        assert forbidden not in content


def test_logo_variants_have_distinct_font_free_geometry(brand) -> None:
    outputs = {variant: render_pyh_logo(brand, variant) for variant in LogoVariant}
    assert len(set(outputs.values())) == 4
    assert b"<text" not in outputs[LogoVariant.HORIZONTAL]
    assert b'aria-label="PYH"' in outputs[LogoVariant.HORIZONTAL]
    assert b"pyh-bubble" in outputs[LogoVariant.HORIZONTAL]
    assert b"pyh-check" in outputs[LogoVariant.HORIZONTAL]
    assert b"pyh-wordmark" in outputs[LogoVariant.HORIZONTAL]
    assert b"phy-" not in outputs[LogoVariant.HORIZONTAL]
    assert brand.colors.navy.encode() in outputs[LogoVariant.HORIZONTAL]
    assert brand.colors.yellow.encode() in outputs[LogoVariant.HORIZONTAL]


def test_logo_avoids_generic_health_motif_identifiers(brand) -> None:
    svg = render_pyh_logo(brand, LogoVariant.HORIZONTAL).lower()
    for forbidden in (b"heartbeat", b"ecg", b"shield", b"dna", b"caduceus"):
        assert forbidden not in svg


@pytest.mark.parametrize("variant", list(LogoVariant))
def test_logo_geometry_respects_safe_margin(brand, variant) -> None:
    import re
    from xml.etree import ElementTree as ET

    root = ET.fromstring(render_pyh_logo(brand, variant))
    _, _, width, height = map(float, root.attrib["viewBox"].split())
    assert (width, height) == ((320, 320) if variant == LogoVariant.MONOGRAM else (760, 300))
    for node in root.iter():
        assert "transform" not in node.attrib
        pad = float(node.get("stroke-width", "0")) / 2
        points = []
        if node.tag.endswith("path"):
            path = node.attrib["d"]
            assert set(re.findall(r"[A-Za-z]", path)) <= set("MLHVCQZ")
            tokens = iter(re.findall(r"[MLHVCQZ]|-?\d+(?:\.\d+)?", path))
            x = y = 0.0
            for token in tokens:
                if token == "Z":
                    continue
                if token in ("M", "L", "Q", "C"):
                    for _ in range({"Q": 2, "C": 3}.get(token, 1)):
                        x, y = float(next(tokens)), float(next(tokens))
                        points.append((x, y))
                elif token == "H":
                    x = float(next(tokens))
                    points.append((x, y))
                elif token == "V":
                    y = float(next(tokens))
                    points.append((x, y))
                else:
                    pytest.fail(f"unsupported path token {token}")
        elif node.tag.endswith("rect"):
            x, y = float(node.get("x", "0")), float(node.get("y", "0"))
            points = [(x, y), (x + float(node.attrib["width"]), y + float(node.attrib["height"]))]
        elif node.tag.endswith("circle"):
            x, y, r = (float(node.attrib[key]) for key in ("cx", "cy", "r"))
            points = [(x-r, y-r), (x+r, y+r)]
        for x, y in points:
            assert 40 + pad <= x <= width - 40 - pad
            assert 40 + pad <= y <= height - 40 - pad


@pytest.mark.parametrize("variant, colors", [
    ("horizontal", {"#12304A", "#F4B942", "#18A6A6", "#263238"}),
    ("one_color", {"#12304A"}),
    ("reverse", {"#F7F4EC", "#F4B942", "#18A6A6"}),
    ("monogram", {"#12304A", "#18A6A6", "#F4B942"}),
])
def test_logo_variant_colors(brand, variant, colors) -> None:
    from xml.etree import ElementTree as ET

    root = ET.fromstring(render_pyh_logo(brand, LogoVariant(variant)))
    actual = {value for node in root.iter() for key, value in node.attrib.items()
              if key in ("fill", "stroke") and value != "none"}
    assert actual == colors
    if variant == "monogram":
        assert root.find("{http://www.w3.org/2000/svg}rect").attrib["fill"] == "#12304A"
    for forbidden in (b"gradient", b"filter", b"<text", b"href", b"<image"):
        assert forbidden not in render_pyh_logo(brand, LogoVariant(variant))


def test_legacy_logo_alias_is_removed() -> None:
    from healthvideo.visuals import brand

    assert not hasattr(brand, "render_phy_logo")


def test_one_color_check_is_a_real_knockout(brand) -> None:
    from xml.etree import ElementTree as ET

    root = ET.fromstring(render_pyh_logo(brand, LogoVariant.ONE_COLOR))
    bubble = root.find("{http://www.w3.org/2000/svg}path")
    assert bubble.attrib["fill-rule"] == "evenodd"
    assert bubble.attrib["d"].count("M") == 2
    assert all("stroke" not in node.attrib for node in root.iter())
