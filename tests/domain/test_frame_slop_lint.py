from datetime import UTC, datetime

from healthvideo.domain.frame_slop_lint import (
    allowed_numbers_from_medanim,
    lint_rendered_frame,
)
from healthvideo.domain.medanim_library import MedAnimEntry


def _sample_entry() -> MedAnimEntry:
    return MedAnimEntry.model_validate(
        {
            "schema_version": "1.0",
            "id": "liver-enzyme-leak",
            "title": "Men gan ALT/AST",
            "category": "pathophysiology",
            "summary": "Tổn thương màng tế bào gan giải phóng ALT và AST.",
            "target_duration_seconds": 50,
            "compositions": {"landscape": "MedAnimLiverEnzymeLeak", "portrait": None},
            "sources": [
                {
                    "id": "kamiike1989",
                    "pmid": "2620458",
                    "pmcid": None,
                    "doi": "10.1016/0009-8981(89)90216-7",
                    "citation": "Kamiike W, et al. Clin Chim Acta. 1989.",
                    "checked_in": "abstract",
                }
            ],
            "steps": [
                {
                    "id": "B1",
                    "narration": "Trong tế bào gan, ALT1 nằm ở bào tương.",
                    "visual": "Tế bào gan và ty thể.",
                    "claim": "Tổn thương nặng làm giải phóng enzyme ty thể.",
                    "quotes": [
                        {
                            "source_id": "kamiike1989",
                            "quote": "mitochondrial enzymes are liberated into the blood only after appreciable disintegration",
                            "locator": "Abstract",
                        }
                    ],
                }
            ],
            "assets": [
                {
                    "file": "niaid-liver-230.svg",
                    "source_page": "https://bioart.niaid.nih.gov/bioart/230",
                    "original_url": "https://bioart.niaid.nih.gov/api/bioarts/230/files/630883",
                    "author": "NIAID BioArt 230",
                    "license": "Public Domain",
                    "sha256": "a" * 64,
                }
            ],
            "medical_audit": {
                "checked_claims": True,
                "checked_anatomy": True,
                "auditor_role": "medical_expert",
                "audited_at": datetime(2026, 11, 19, 12, 0, tzinfo=UTC),
                "passed": True,
            },
        }
    )


def test_clean_style_a_frame_has_zero_slop_issues():
    entry = _sample_entry()
    allowed = allowed_numbers_from_medanim(entry)
    html = """
    <div data-format="landscape">
      <div data-medanim-title="true" style="font-size: 72px">Men gan</div>
      <div data-medanim-label="Tĩnh mạch trung tâm">
        <div style="font-size: 44px">Tĩnh mạch trung tâm</div>
        <div style="font-size: 26px; font-style: italic">Vena centralis</div>
      </div>
      <div data-medanim-underline="liver" style="height: 8px; background-color: #F4B942"></div>
      <div data-medanim-scope="kamiike1989" style="font-size: 22px">
        Mô hình gan chuột (Kamiike 1989) · ALT1 · 16:9 · 1.5x
      </div>
      <div data-style-captions="true" style="font-size: 36px">
        <div data-caption-line="true">
          <span data-word="0">Trong</span>
          <span data-term-group="true" style="background-color: #F4B942">
            <span data-word="1">tế bào</span>
          </span>
        </div>
      </div>
    </div>
    """
    issues = lint_rendered_frame(html, allowed_numbers=allowed)
    assert issues == []


def test_detects_internal_draft_notes():
    html = """
    <div>
      <p style="font-size: 28px">*Chưa có hình nội mô cửa sổ phù hợp</p>
      <text font-size="28">Lòng xoang · nội mô minh họa khái quát*</text>
      <span style="font-size: 28px">TODO: replace recoloured liver</span>
    </div>
    """
    issues = lint_rendered_frame(html)
    rules = [i.rule for i in issues]
    excerpts = " | ".join(i.excerpt.lower() for i in issues)
    assert "internal_draft_note" in rules
    assert "chưa có hình" in excerpts
    assert "minh họa khái quát" in excerpts
    assert "todo" in excerpts
    assert "recoloured" in excerpts


def test_detects_style_a_caption_and_minimap_underlines():
    html = """
    <div data-style-captions="true" style="font-size: 36px">
      <span data-word="0" style="text-decoration: underline">Gan</span>
      <span data-word="1" style="border-bottom: 3px solid #18A6A6">gồm</span>
    </div>
    <div data-mini-map="true" style="font-size: 28px">
      <span data-mini-map-step="Gan" style="text-decoration-line: underline">Gan</span>
      <u>Tiểu thùy</u>
    </div>
    """
    issues = lint_rendered_frame(html)
    underline_issues = [i for i in issues if i.rule == "style_a_underline"]
    assert len(underline_issues) >= 3


def test_detects_small_fonts_for_landscape_and_portrait():
    landscape_html = """
    <div data-format="landscape">
      <div style="font-size: 12px">Chữ siêu nhỏ</div>
      <div data-medanim-label="Xoang">
        <div style="font-size: 36px">Xoang gan</div>
      </div>
    </div>
    """
    issues_16 = lint_rendered_frame(landscape_html)
    assert any(i.rule == "small_font" and "12px" in i.excerpt for i in issues_16)
    assert any(i.rule == "small_font" and "36px" in i.excerpt for i in issues_16)

    portrait_html = """
    <div data-format="portrait">
      <div data-medanim-label="Xoang">
        <div style="font-size: 46px">Xoang gan</div>
      </div>
    </div>
    """
    issues_9 = lint_rendered_frame(portrait_html)
    assert any(i.rule == "small_font" and "46px" in i.excerpt for i in issues_9)


def test_detects_stray_numbers_and_scale_bars():
    entry = _sample_entry()
    allowed = allowed_numbers_from_medanim(entry)
    html = """
    <div style="font-size: 28px">
      <span>Scale bar 50 µm</span>
      <span>Tăng 45% nguy cơ</span>
      <span>XX% bệnh nhân</span>
    </div>
    """
    issues = lint_rendered_frame(html, allowed_numbers=allowed)
    stray = [i for i in issues if i.rule == "stray_number"]
    excerpts = " | ".join(i.excerpt for i in stray)
    assert "50 µm" in excerpts
    assert "45%" in excerpts
    assert "XX%" in excerpts
