"""Authorized full text: Europe PMC OA XML or a manually supplied local PDF.

Article text stays in the repository's ignored cache, never in a revision.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from healthvideo.domain.evidence import SourceRecord
from healthvideo.evidence.clients import (
    DEFAULT_USER_AGENT,
    Transport,
    _default_transport,
)

CACHE_DIR = Path(__file__).resolve().parents[3] / "cache" / "fulltext"
BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"


class FullTextSection(BaseModel):
    heading: str
    page: int | None = Field(default=None, ge=1)
    text: str


class FullText(BaseModel):
    source_id: str
    origin: Literal["open_access", "user_pdf"]
    license: str | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sections: list[FullTextSection]
    # Cache identity prevents collisions across projects reusing IDs such as R01.
    pmid: str | None = None
    doi: str | None = None


def _safe_id(source_id: str) -> str:
    if not source_id or source_id in {".", ".."} or any(c in source_id for c in "/\\:"):
        raise ValueError("source_id must be a safe cache filename")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", source_id):
        raise ValueError("source_id must be a safe cache filename")
    return source_id


def cache_path(source_id: str) -> Path:
    return CACHE_DIR / f"{_safe_id(source_id)}.json"


def store_fulltext(fulltext: FullText) -> Path:
    path = cache_path(fulltext.source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fulltext.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_fulltext(
    source_id: str, record: SourceRecord | None = None
) -> FullText | None:
    path = cache_path(source_id)
    if not path.is_file():
        return None
    value = FullText.model_validate_json(path.read_text(encoding="utf-8"))
    if value.source_id != source_id:
        raise ValueError(f"Fulltext cache source mismatch: {source_id}")
    if record is not None and (value.pmid != record.pmid or value.doi != record.doi):
        return None
    return value


def store_abstract(
    source_id: str, text: str, *, record: SourceRecord | None = None
) -> None:
    path = CACHE_DIR / "abstracts" / f"{_safe_id(source_id)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source_id": source_id,
                "abstract": text,
                "pmid": record.pmid if record else None,
                "doi": record.doi if record else None,
            }
        ),
        encoding="utf-8",
    )


def load_abstract(source_id: str) -> str:
    path = CACHE_DIR / "abstracts" / f"{_safe_id(source_id)}.json"
    return (
        json.loads(path.read_text(encoding="utf-8")).get("abstract", "")
        if path.is_file()
        else ""
    )


def normalize_quote(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"[\u2010-\u2015\u2212]", "-", text)
    # Dehyphenate words, never numeric ranges such as 1–2 versus 12.
    text = re.sub(r"(?<=[^\W\d_])-\s*(?=[^\W\d_])", "", text)
    return " ".join(text.split())


def validate_support_records(claims, records) -> None:
    """Bind global source IDs to this ledger's paper before trusting quotes."""
    sources = {record.id: record for record in records}
    for claim in claims:
        for support in claim.support:
            record = sources.get(support.source_id)
            if record is None:
                raise ValueError(f"Unknown support source {support.source_id}")
            value = load_fulltext(support.source_id)
            if value is not None:
                matches = value.pmid == record.pmid and value.doi == record.doi
            else:
                path = CACHE_DIR / "abstracts" / f"{_safe_id(support.source_id)}.json"
                data = (
                    json.loads(path.read_text(encoding="utf-8"))
                    if path.is_file()
                    else {}
                )
                matches = (
                    data.get("pmid") == record.pmid and data.get("doi") == record.doi
                )
            if not matches:
                raise ValueError(
                    f"Support cache belongs to another paper: {support.source_id}; run step fulltext"
                )
            texts = ([section.text for section in value.sections] if value is not None
                     else [data.get("abstract", "")])
            if not any(normalize_quote(support.quote) in normalize_quote(text) for text in texts):
                raise ValueError(
                    f"Claim {claim.id}: support quote does not match cached source "
                    f"{support.source_id}; run step fulltext or supply the source PDF"
                )


def _plain(element: ET.Element | None) -> str:
    if element is None:
        return ""

    def content(node: ET.Element) -> str:
        chunks = [node.text or ""]
        for child in node:
            block = child.tag.rsplit("}", 1)[-1] in {"p", "title", "sec", "label"}
            chunks.extend(
                [
                    " " if block else "",
                    content(child),
                    " " if block else "",
                    child.tail or "",
                ]
            )
        return "".join(chunks)

    return " ".join(content(element).split())


def _xml_sections(raw: bytes) -> list[FullTextSection]:
    root = ET.fromstring(raw)
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    result = []
    for heading, node in [
        ("Title", root.find(".//article-title")),
        ("Abstract", root.find(".//abstract")),
    ]:
        if _plain(node):
            result.append(FullTextSection(heading=heading, text=_plain(node)))

    def walk(node: ET.Element, heading: str) -> None:
        if node.tag == "sec" and (
            node.get("sec-type") in {"ref-list", "references"}
            or _plain(node.find("title")).casefold() in {"references", "bibliography"}
        ):
            return
        chunks = []
        children = []

        def collect(element):
            for child in element:
                if child.tag in {"ref-list", "ref", "title", "table"}:
                    continue
                if child.tag == "sec":
                    children.append(child)
                elif child.tag == "table-wrap":
                    chunks.extend(_plain(c) for c in child.findall("caption"))
                elif child.tag in {"p", "caption"}:
                    chunks.append(_plain(child))
                else:
                    collect(child)

        collect(node)
        if any(chunks):
            result.append(FullTextSection(heading=heading, text="\n".join(chunks)))
        for child in children:
            walk(child, _plain(child.find("title")) or heading)

    body = root.find(".//body")
    if body is not None:
        walk(body, "Body")
    return result


def fetch_open_access(
    record: SourceRecord, *, transport: Transport = _default_transport
) -> FullText | None:
    """Verify OA metadata before requesting XML; never fetch publisher pages."""
    if not record.pmid and not record.pmcid:
        return None
    query = (
        f"EXT_ID:{record.pmid} AND SRC:MED" if record.pmid else f"PMCID:{record.pmcid}"
    )
    params = urllib.parse.urlencode(
        {"query": query, "resultType": "core", "format": "json"}
    )

    def get(url):
        return transport(
            urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        )

    data = json.loads(get(f"{BASE_URL}/search?{params}"))
    rows = data.get("resultList", {}).get("result", [])
    metadata = next(
        (
            r
            for r in rows
            if (
                str(r.get("id")) == record.pmid
                if record.pmid
                else r.get("pmcid") == record.pmcid
            )
        ),
        None,
    )
    if metadata is None:
        return None
    abstract = metadata.get("abstractText", "")
    if abstract:
        # Europe PMC abstracts can contain JATS markup.
        try:
            abstract = _plain(ET.fromstring(f"<abstract>{abstract}</abstract>"))
        except ET.ParseError:
            pass
        store_abstract(record.id, abstract, record=record)
    pmcid = metadata.get("pmcid")
    if metadata.get("isOpenAccess") != "Y" or not pmcid:
        return None
    if not re.fullmatch(r"PMC\d+", pmcid):
        raise ValueError("Invalid PMCID from Europe PMC")
    raw = get(f"{BASE_URL}/{pmcid}/fullTextXML")
    sections = _xml_sections(raw)
    if not sections:
        return None
    value = FullText(
        source_id=record.id,
        origin="open_access",
        license=metadata.get("license") or None,
        sha256=hashlib.sha256(raw).hexdigest(),
        sections=sections,
        pmid=record.pmid,
        doi=record.doi,
    )
    store_fulltext(value)
    return value


def pdf_names(record: SourceRecord) -> list[str]:
    names = []
    if record.pmid and re.fullmatch(r"\d+", record.pmid):
        names.append(f"{record.pmid}.pdf")
    if record.doi:
        doi = record.doi.removeprefix("https://doi.org/")
        filename = doi.replace("/", "_") + ".pdf"
        if not any(c in filename for c in '\\:<>"|?*') and filename not in {".", ".."}:
            names.append(filename)
    return names


def extract_user_pdf(record: SourceRecord, inbox: Path) -> FullText | None:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    for name in pdf_names(record):
        path = inbox / name
        if not path.is_file() or not path.resolve().is_relative_to(inbox.resolve()):
            continue
        try:
            raw = path.read_bytes()
            reader = PdfReader(path)
            sections = [
                FullTextSection(
                    heading=f"Page {i}", page=i, text=page.extract_text() or ""
                )
                for i, page in enumerate(reader.pages, 1)
            ]
        except (PdfReadError, OSError, ValueError):
            continue
        if not any(s.text.strip() for s in sections):
            continue
        value = FullText(
            source_id=record.id,
            origin="user_pdf",
            license=None,
            sha256=hashlib.sha256(raw).hexdigest(),
            sections=sections,
            pmid=record.pmid,
            doi=record.doi,
        )
        store_fulltext(value)
        return value
    return None


def search_fulltext(source_id: str, query: str) -> list[dict]:
    if not query.strip():
        raise ValueError("query must be nonblank")
    value = load_fulltext(source_id)
    if value is None:
        return []
    matches = []
    for section in value.sections:
        text = normalize_quote(section.text)
        for match in re.finditer(
            re.escape(normalize_quote(query)), text, flags=re.IGNORECASE
        ):
            start = max(0, match.start() - 180)
            locator = section.heading + (f", p.{section.page}" if section.page else "")
            matches.append({"locator": locator, "text": text[start : start + 600]})
            if len(matches) == 5:
                return matches
    return matches
