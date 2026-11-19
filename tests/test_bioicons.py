import hashlib
import json
import xml.etree.ElementTree as ET

import pytest
import yaml

from tools.medanim import bioicons

SAMPLE_ICONS_JSON = [
    {"name": "macrophage", "category": "Blood_Immunology", "license": "cc-by-4.0", "author": "Simon Duerr"},
    {"name": "macrophage_sa", "category": "Blood_Immunology", "license": "cc-by-sa-4.0", "author": "Other Author"},
    {"name": "alveolus", "category": "Human_physiology", "license": "cc-0", "author": "Marcel Tisch"},
    {"name": "bacterium_sa3", "category": "Microbiology", "license": "cc-by-sa-3.0", "author": "Someone"},
]

SAMPLE_AUTHORS_JSON = {
    "Simon Duerr": "https://bioicons.com",
    "Marcel Tisch": "https://twitter.com/MarcelTisch",
}

RAW_INKSCAPE_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
     viewBox="0 0 120 120">
  <sodipodi:namedview id="base" pagecolor="#ffffff" inkscape:zoom="2" />
  <metadata id="meta1">internal</metadata>
  <defs>
    <style>.cls-1{fill:url(#grad1);clip-path:url(#clip1);}</style>
    <linearGradient id="grad1"><stop offset="0%" stop-color="#18A6A6"/></linearGradient>
    <clipPath id="clip1"><rect x="0" y="0" width="100" height="100"/></clipPath>
    <mask id="mask1"><rect x="0" y="0" width="50" height="50" fill="white"/></mask>
  </defs>
  <g id="layer1" inkscape:groupmode="layer" inkscape:label="Main">
    <path id="cell-body" class="cls-1" mask="url(#mask1)" d="M10 10 H90 V90 Z" sodipodi:nodetypes="ccc"/>
    <use xlink:href="#cell-body" x="5" y="5"/>
  </g>
</svg>
"""


def _fake_fetcher(url: str) -> bytes:
    if url == bioicons.BIOICONS_ICONS_URL:
        return json.dumps(SAMPLE_ICONS_JSON).encode("utf-8")
    if url == bioicons.BIOICONS_AUTHORS_URL:
        return json.dumps(SAMPLE_AUTHORS_JSON).encode("utf-8")
    if url.endswith(".svg"):
        return RAW_INKSCAPE_SVG.encode("utf-8")
    raise AssertionError(f"Unexpected URL: {url}")


def test_search_rejects_cc_by_sa_by_default():
    hits = bioicons.search_icons("macrophage", fetcher=_fake_fetcher)
    assert [h.name for h in hits] == ["macrophage"]
    assert hits[0].license == "CC BY 4.0"

    with pytest.raises(ValueError, match="rejected by default"):
        bioicons.search_icons("macrophage", license_filter="cc-by-sa-4.0", fetcher=_fake_fetcher)

    hits_with_sa = bioicons.search_icons("macrophage", allow_sharealike=True, fetcher=_fake_fetcher)
    assert [h.name for h in hits_with_sa] == ["macrophage", "macrophage_sa"]


def test_sanitize_svg_strips_inkscape_prefixes_ids_and_rejects_scripts():
    cleaned = bioicons.sanitize_svg(RAW_INKSCAPE_SVG, prefix="bio-macro")
    assert "inkscape" not in cleaned.lower()
    assert "sodipodi" not in cleaned.lower()
    assert "<metadata" not in cleaned.lower()
    assert 'id="bio-macro-grad1"' in cleaned
    assert 'id="bio-macro-clip1"' in cleaned
    assert 'id="bio-macro-mask1"' in cleaned
    assert 'id="bio-macro-cell-body"' in cleaned
    assert "url(#bio-macro-grad1)" in cleaned
    assert "url(#bio-macro-clip1)" in cleaned
    assert "url(#bio-macro-mask1)" in cleaned
    assert "#bio-macro-cell-body" in cleaned
    ET.fromstring(cleaned)

    with pytest.raises(ValueError, match="Unsafe SVG"):
        bioicons.sanitize_svg('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', prefix="x")

    with pytest.raises(ValueError, match="Unsafe SVG"):
        bioicons.sanitize_svg('<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>', prefix="x")


def test_get_icon_rejects_sa_downloads_cleans_hashes_and_emits_manifest(tmp_path):
    with pytest.raises(ValueError, match="CC BY-SA"):
        bioicons.get_icon(
            "macrophage_sa",
            out_dir=tmp_path / "assets",
            fetcher=_fake_fetcher,
        )

    out_dir = tmp_path / "library/medanim/macrophage-phagocytosis/assets"
    pub_dir = tmp_path / "video/public/medanim/macrophage-phagocytosis"
    result = bioicons.get_icon(
        "macrophage",
        out_dir=out_dir,
        public_dir=pub_dir,
        fetcher=_fake_fetcher,
    )

    out_file = out_dir / "bioicons-macrophage.svg"
    pub_file = pub_dir / "bioicons-macrophage.svg"
    assert out_file.is_file()
    assert pub_file.is_file()
    assert out_file.read_bytes() == pub_file.read_bytes()

    expected_sha = hashlib.sha256(out_file.read_bytes()).hexdigest()
    assert result["asset"]["sha256"] == expected_sha
    assert result["asset"]["license"] == "CC BY 4.0"
    assert result["asset"]["author"] == "Simon Duerr"
    assert result["viewBox"] == "0 0 120 120"
    assert "Bioicons" in result["attribution_line"]

    snippet = bioicons.format_manifest_yaml_snippet(result)
    parsed = yaml.safe_load(snippet)
    assert isinstance(parsed, list) and parsed[0]["sha256"] == expected_sha
