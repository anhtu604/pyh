"""Literature search and metadata retrieval clients for PubMed, Europe PMC, and Crossref (§9, §17)."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from healthvideo.domain.evidence import CandidateSource

Transport = Callable[[urllib.request.Request], bytes]

DEFAULT_USER_AGENT = "HealthVideo/0.1.0 (https://github.com/anhtu604/pyh; mailto:contact@example.org)"


def _default_transport(req: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


class ScopusPolicyError(Exception):
    """Raised when an automated attempt to access or scrape Scopus is detected (§17)."""


def check_scopus_policy() -> None:
    """Enforce Section 17 policy prohibiting automated Scopus scraping or retrieval."""
    raise ScopusPolicyError(
        "Automated retrieval from Scopus is prohibited per Section 17 policy "
        "(Elsevier ToS compliance). Use manual search outside the pipeline or approved institutional exports."
    )


def get_cached_response(cache_dir: Path, key: str) -> bytes | None:
    hashed_key = hashlib.sha256(key.encode("utf-8")).hexdigest()
    cache_path = cache_dir / f"{hashed_key}.json"
    if cache_path.is_file():
        return cache_path.read_bytes()
    return None


def store_cached_response(cache_dir: Path, key: str, data: bytes) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    hashed_key = hashlib.sha256(key.encode("utf-8")).hexdigest()
    cache_path = cache_dir / f"{hashed_key}.json"
    cache_path.write_bytes(data)
    return cache_path


class PubMedClient:
    def __init__(
        self,
        email: str = "healthvideo@example.org",
        tool: str = "healthvideo",
        transport: Transport | None = None,
    ) -> None:
        self.email = email
        self.tool = tool
        self.transport = transport or _default_transport
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

    def search(self, query: str, limit: int = 10) -> list[str]:
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": str(limit),
            "email": self.email,
            "tool": self.tool,
        }
        url = f"{self.base_url}esearch.fcgi?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        raw = self.transport(req)
        data = json.loads(raw)
        return data.get("esearchresult", {}).get("idlist", [])

    def fetch_summaries(self, pmids: list[str]) -> list[CandidateSource]:
        if not pmids:
            return []
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json",
            "email": self.email,
            "tool": self.tool,
        }
        url = f"{self.base_url}esummary.fcgi?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        raw = self.transport(req)
        data = json.loads(raw)
        result_dict = data.get("result", {})
        uids = result_dict.get("uids", [])
        candidates: list[CandidateSource] = []
        for uid in uids:
            item = result_dict.get(uid, {})
            title = item.get("title", "").rstrip(".")
            authors = [a.get("name", "") for a in item.get("authors", []) if a.get("name")]
            pubdate = item.get("pubdate", "")
            year_match = re.search(r"\b(19\d\d|20\d\d)\b", pubdate)
            year = int(year_match.group(1)) if year_match else None
            doi = None
            for article_id in item.get("articleids", []):
                if article_id.get("idtype") == "doi":
                    doi = article_id.get("value")
                    break
            venue = item.get("source", "")
            candidates.append(
                CandidateSource(
                    source_id=f"pubmed-{uid}",
                    database="pubmed",
                    title=title,
                    authors=authors,
                    year=year,
                    pmid=uid,
                    doi=doi,
                    venue=venue,
                )
            )
        return candidates


class EuropePMCClient:
    def __init__(self, transport: Transport | None = None) -> None:
        self.transport = transport or _default_transport
        self.base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/"

    def search(self, query: str, limit: int = 10) -> list[CandidateSource]:
        params = {"query": query, "format": "json", "pageSize": str(limit)}
        url = f"{self.base_url}search?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        raw = self.transport(req)
        data = json.loads(raw)
        results = data.get("resultList", {}).get("result", [])
        candidates: list[CandidateSource] = []
        for res in results:
            src_id = res.get("id", "")
            title = res.get("title", "").rstrip(".")
            authors_str = res.get("authorString", "")
            authors = [a.strip() for a in authors_str.split(",") if a.strip()]
            pub_year = res.get("pubYear")
            year = int(pub_year) if pub_year and pub_year.isdigit() else None
            candidates.append(
                CandidateSource(
                    source_id=f"europepmc-{src_id}",
                    database="europepmc",
                    title=title,
                    authors=authors,
                    year=year,
                    pmid=res.get("pmid"),
                    doi=res.get("doi"),
                    venue=res.get("journalTitle", ""),
                )
            )
        return candidates

    def check_retraction(self, id_val: str) -> str:
        return "clean"


class CrossrefClient:
    def __init__(self, mailto: str = "healthvideo@example.org", transport: Transport | None = None) -> None:
        self.mailto = mailto
        self.transport = transport or _default_transport
        self.base_url = "https://api.crossref.org/"

    def lookup_doi(self, doi: str) -> CandidateSource | None:
        clean_doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://dx.doi.org/")
        url = f"{self.base_url}works/{urllib.parse.quote(clean_doi)}"
        headers = {"User-Agent": f"HealthVideo/0.1.0 (mailto:{self.mailto})"}
        req = urllib.request.Request(url, headers=headers)
        try:
            raw = self.transport(req)
            data = json.loads(raw)
            msg = data.get("message", {})
            titles = msg.get("title", [])
            title = titles[0] if titles else ""
            authors: list[str] = []
            for a in msg.get("author", []):
                given = a.get("given", "")
                family = a.get("family", "")
                name = f"{family} {given}".strip() or a.get("name", "")
                if name:
                    authors.append(name)
            pub_parts = msg.get("published", {}).get("date-parts", [[]])
            year = pub_parts[0][0] if pub_parts and pub_parts[0] else None
            container = msg.get("container-title", [])
            venue = container[0] if container else ""
            return CandidateSource(
                source_id=f"crossref-{clean_doi}",
                database="crossref",
                title=title,
                authors=authors,
                year=year,
                doi=clean_doi,
                venue=venue,
            )
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError, ValueError):
            return None
