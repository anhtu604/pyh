import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.storage.files import read_yaml, write_yaml_atomic


@pytest.fixture
def project_dir(tmp_path):
    import shutil

    path = tmp_path / "project"
    shutil.copytree(Path("tests/fixtures/golden-project-v2"), path)
    return path


def record(**kwargs):
    return SourceRecord(
        id="R01", title="Synthetic test", pmid="123", doi="10.0/test", **kwargs
    )


def test_open_access_xml_to_sections(monkeypatch, tmp_path):
    from healthvideo.evidence import fulltext as ft

    monkeypatch.setattr(ft, "CACHE_DIR", tmp_path / "cache/fulltext")
    xml = b"""<article><front><article-meta><title-group><article-title>Test title</article-title></title-group><abstract><p>Abstract text.</p></abstract></article-meta></front><body><sec><title>Results</title><p>First <italic>result</italic>.</p><sec><title>Subgroup</title><p>Nested result.</p></sec><table-wrap><caption><p>Table caption.</p></caption><table><tr><td>Secret cell</td></tr></table></table-wrap></sec><sec sec-type="ref-list"><title>References</title><p>Excluded reference.</p></sec></body><back><ref-list><ref>Excluded citation</ref></ref-list></back></article>"""

    def transport(req):
        if "fullTextXML" in req.full_url:
            return xml
        return json.dumps(
            {
                "resultList": {
                    "result": [
                        {
                            "id": "123",
                            "pmcid": "PMC123",
                            "isOpenAccess": "Y",
                            "license": "CC BY",
                            "abstractText": "Abstract text.",
                        }
                    ]
                }
            }
        ).encode()

    result = ft.fetch_open_access(record(), transport=transport)
    assert result.origin == "open_access" and result.license == "CC BY"
    sections = {s.heading: s.text for s in result.sections}
    assert sections["Subgroup"] == "Nested result."
    assert "Table caption." in sections["Results"]
    assert "Nested result" not in sections["Results"]
    assert "Secret cell" not in str(sections) and "Excluded" not in str(sections)


def test_non_oa_never_requests_xml(monkeypatch, tmp_path):
    from healthvideo.evidence import fulltext as ft

    monkeypatch.setattr(ft, "CACHE_DIR", tmp_path / "cache/fulltext")

    def transport(req):
        assert "fullTextXML" not in req.full_url
        return b'{"resultList":{"result":[{"id":"123","pmcid":"PMC123","isOpenAccess":"N","abstractText":"Only abstract."}]}}'

    assert ft.fetch_open_access(record(), transport=transport) is None


def test_user_pdf_extracted_with_pages(monkeypatch, tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    from healthvideo.evidence import fulltext as ft

    monkeypatch.setattr(ft, "CACHE_DIR", tmp_path / "cache/fulltext")
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    for text in ["First page result", "Second page result"]:
        page = writer.add_blank_page(width=300, height=300)
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(inbox / "123.pdf")
    result = ft.extract_user_pdf(record(), inbox)
    assert [s.page for s in result.sections] == [1, 2]
    assert "Second page result" in result.sections[1].text
    assert result.license is None


def cached(monkeypatch, tmp_path):
    from healthvideo.evidence import fulltext as ft

    monkeypatch.setattr(ft, "CACHE_DIR", tmp_path / "cache/fulltext")
    value = ft.FullText(
        source_id="R01",
        origin="user_pdf",
        license=None,
        sha256="a" * 64,
        pmid="123",
        doi="10.0/test",
        sections=[
            {
                "heading": "Results",
                "page": 5,
                "text": "A well-\nbeing result with <synthetic> text.",
            }
        ],
    )
    ft.store_fulltext(value)
    return ft


def test_fulltext_cached_outside_project(monkeypatch, tmp_path):
    ft = cached(monkeypatch, tmp_path)
    assert ft.cache_path("R01").is_file()
    assert ft.cache_path("R01").is_relative_to(tmp_path / "cache")
    assert not (tmp_path / "projects").exists()
    with pytest.raises(ValueError):
        ft.cache_path("../escape")


def claim(quote):
    return EvidenceClaim(
        id="C01",
        type="evidence",
        text_public="Synthetic",
        text_technical="Synthetic",
        sources=["R01"],
        support=[{"source_id": "R01", "locator": "Results, p.5", "quote": quote}],
    )


def test_support_quote_must_match_fulltext(monkeypatch, tmp_path):
    ft = cached(monkeypatch, tmp_path)
    ft.validate_support_records([claim("A well-being result")], [record()])
    with pytest.raises(ValueError, match="quote.*R01"):
        ft.validate_support_records([claim("Invented findings")], [record()])


def test_ledger_loads_without_cache(monkeypatch, tmp_path):
    from healthvideo.evidence import fulltext as ft

    monkeypatch.setattr(ft, "CACHE_DIR", tmp_path / "empty")
    assert claim("Anything quoted earlier").support


def test_support_quote_over_25_words_rejected():
    with pytest.raises(ValidationError, match="25 words"):
        claim(" ".join(["word"] * 26))


def test_abstract_fallback_only_without_fulltext(monkeypatch, tmp_path):
    ft = cached(monkeypatch, tmp_path)
    ft.store_abstract("R01", "Only abstract result", record=record())
    with pytest.raises(ValueError, match="quote"):
        ft.validate_support_records([claim("Only abstract result")], [record()])
    ft.cache_path("R01").unlink()
    ft.validate_support_records([claim("Only abstract result")], [record()])


def test_step_fulltext_reports_missing_with_doi(project_dir, monkeypatch, tmp_path):
    from healthvideo.evidence import fulltext as ft

    monkeypatch.setattr(ft, "CACHE_DIR", tmp_path / "cache/fulltext")
    monkeypatch.setattr(ft, "fetch_open_access", lambda *a, **kw: None)
    path = project_dir / "revisions/001/evidence/ledger.yaml"
    write_yaml_atomic(path, {"records": [record().model_dump()], "claims": []})
    result = CliRunner().invoke(app, ["step", "fulltext", str(project_dir)])
    assert result.exit_code == 0, result.output
    assert "https://doi.org/10.0/test" in result.output and "123.pdf" in result.output
    index = read_yaml(project_dir / "revisions/001/research/fulltext-index.yaml")
    assert index["sources"][0]["origin"] == "missing"


def test_fulltext_search_returns_locator(project_dir, monkeypatch, tmp_path):
    ft = cached(monkeypatch, tmp_path)
    write_yaml_atomic(
        project_dir / "revisions/001/evidence/ledger.yaml",
        {"records": [record().model_dump()], "claims": []},
    )
    result = CliRunner().invoke(
        app,
        [
            "step",
            "fulltext-search",
            str(project_dir),
            "--source",
            "R01",
            "--query",
            "result",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Results" in result.output and "5" in result.output
    matches = ft.search_fulltext("R01", "result")
    assert len(matches) <= 5 and len(matches[0]["text"]) <= 600


@pytest.mark.parametrize("claim_type", ["evidence", "mechanism"])
def test_medical_packet_shows_support(project_dir, monkeypatch, tmp_path, claim_type):
    cached(monkeypatch, tmp_path)
    path = project_dir / "revisions/001/evidence/ledger.yaml"
    data = read_yaml(path)
    data["records"] = [record().model_dump()]
    data["claims"][0]["type"] = claim_type
    data["claims"][0]["support"] = [
        {
            "source_id": "R01",
            "locator": "Results, p.5 <x>",
            "quote": "<synthetic> text.",
        }
    ]
    write_yaml_atomic(path, data)
    from healthvideo.workflows.review_html import render_medical_packet

    html = render_medical_packet(project_dir / "revisions/001")
    assert "&lt;synthetic&gt; text." in html and "Results, p.5 &lt;x&gt;" in html
    assert "user_pdf" in html


def test_support_normalizes_linebreak_hyphen(monkeypatch, tmp_path):
    cached(monkeypatch, tmp_path)
    assert claim("A wellbeing result").support


def test_support_cache_cannot_belong_to_another_paper(
    monkeypatch, tmp_path, project_dir
):
    ft = cached(monkeypatch, tmp_path)
    from healthvideo.workflows.evidence import build_evidence_ledger

    evidence = claim("A well-being result")
    wrong = record().model_copy(update={"doi": "10.0/other"})
    with pytest.raises(ValueError, match="cache.*R01"):
        build_evidence_ledger(project_dir, [evidence], [wrong])
    assert ft.load_fulltext("R01", wrong) is None


def test_search_is_bounded_and_blank_query_rejected(monkeypatch, tmp_path):
    ft = cached(monkeypatch, tmp_path)
    value = ft.load_fulltext("R01")
    value.sections[0].text = ("result " + "x" * 1000 + " ") * 10
    ft.store_fulltext(value)
    matches = ft.search_fulltext("R01", "result")
    assert len(matches) == 5
    assert all(len(m["text"]) <= 600 for m in matches)
    with pytest.raises(ValueError, match="nonblank"):
        ft.search_fulltext("R01", " ")


def test_crop_license_rejects_nc_without_explicit_permission(monkeypatch, tmp_path):
    ft = cached(monkeypatch, tmp_path)
    from healthvideo.domain.license_ledger import LicenseEntry

    value = ft.load_fulltext("R01")
    value.origin = "open_access"
    value.license = "cc by-nc"
    ft.store_fulltext(value)
    args = {
        "path": "assets/crop.png",
        "source": "R01",
        "creator": "Synthetic",
        "revision": "001",
        "sha256": "a" * 64,
        "source_license": "cc by-nc",
    }
    with pytest.raises(ValueError, match="permission"):
        LicenseEntry(**args, license="cc by-nc", rights_basis="Open access")
    entry = LicenseEntry(
        **args,
        license="Permission from rights holder",
        rights_basis="Doctor recorded written permission for commercial crop",
    )
    assert entry.source_license == "cc by-nc"


@pytest.mark.parametrize(
    "license", ["cc by", "CC BY-SA 4.0", "https://creativecommons.org/licenses/by/4.0/"]
)
def test_crop_license_accepts_by_or_by_sa(license):
    from healthvideo.domain.license_ledger import LicenseEntry

    entry = LicenseEntry(
        path="assets/crop.png",
        source="R01",
        creator="Synthetic",
        revision="001",
        sha256="a" * 64,
        source_license=license,
        license=license,
        rights_basis="Open access license",
    )
    assert entry.source_license == license


def test_normalization_does_not_turn_numeric_range_into_number():
    from healthvideo.evidence.fulltext import normalize_quote

    assert normalize_quote("1-2 patients") != normalize_quote("12 patients")


def test_oa_abstract_preserves_paragraph_boundaries(monkeypatch, tmp_path):
    from healthvideo.evidence import fulltext as ft

    monkeypatch.setattr(ft, "CACHE_DIR", tmp_path / "cache/fulltext")

    def transport(req):
        return json.dumps(
            {
                "resultList": {
                    "result": [
                        {
                            "id": "123",
                            "isOpenAccess": "N",
                            "abstractText": "<p>First sentence.</p><p>Second sentence.</p>",
                        }
                    ]
                }
            }
        ).encode()

    assert ft.fetch_open_access(record(), transport=transport) is None
    assert ft.load_abstract("R01") == "First sentence. Second sentence."


def test_fulltext_network_failure_reports_missing_and_preserves_state(
    project_dir, monkeypatch, tmp_path
):
    from healthvideo.evidence import fulltext as ft

    monkeypatch.setattr(ft, "CACHE_DIR", tmp_path / "cache/fulltext")

    def unavailable(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(ft, "fetch_open_access", unavailable)
    write_yaml_atomic(
        project_dir / "revisions/001/evidence/ledger.yaml",
        {"records": [record().model_dump()], "claims": []},
    )
    before = (project_dir / "project.yaml").read_bytes()
    result = CliRunner().invoke(app, ["step", "fulltext", str(project_dir)])
    assert result.exit_code == 0 and "missing" in result.output
    assert (project_dir / "project.yaml").read_bytes() == before
