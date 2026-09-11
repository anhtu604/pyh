import json
from pathlib import Path
from urllib.request import Request

import pytest

from healthvideo.evidence.clients import (
    CrossrefClient,
    EuropePMCClient,
    PubMedClient,
    ScopusPolicyError,
    check_scopus_policy,
    get_cached_response,
    store_cached_response,
)


def test_scopus_policy_raises_scopus_policy_error() -> None:
    with pytest.raises(ScopusPolicyError, match="Section 17"):
        check_scopus_policy()


def test_pubmed_search_and_fetch_summaries() -> None:
    esearch_response = json.dumps({
        "esearchresult": {
            "idlist": ["12345678", "87654321"],
            "count": "2",
        }
    }).encode("utf-8")

    esummary_response = json.dumps({
        "result": {
            "uids": ["12345678"],
            "12345678": {
                "title": "Dietary sodium reduction and cardiovascular disease.",
                "authors": [{"name": "Smith J", "authtype": "Author"}],
                "pubdate": "2023 Nov",
                "source": "New England Journal of Medicine",
                "articleids": [{"idtype": "doi", "value": "10.1056/NEJMoa123456"}],
            },
        }
    }).encode("utf-8")

    def mock_transport(req: Request) -> bytes:
        url = req.full_url
        if "esearch.fcgi" in url:
            return esearch_response
        if "esummary.fcgi" in url:
            return esummary_response
        return b"{}"

    client = PubMedClient(email="doctor@example.org", transport=mock_transport)
    pmids = client.search("sodium reduction", limit=5)
    assert pmids == ["12345678", "87654321"]

    candidates = client.fetch_summaries(["12345678"])
    assert len(candidates) == 1
    assert candidates[0].source_id == "pubmed-12345678"
    assert candidates[0].title.startswith("Dietary sodium reduction")
    assert candidates[0].doi == "10.1056/NEJMoa123456"
    assert candidates[0].year == 2023


def test_europepmc_search_and_retraction_check() -> None:
    search_response = json.dumps({
        "hitCount": 1,
        "resultList": {
            "result": [
                {
                    "id": "23456789",
                    "pmid": "23456789",
                    "doi": "10.1001/jama.2022.0001",
                    "title": "Salt intake and hypertension risk in Asia",
                    "authorString": "Nguyen A, Tran B",
                    "pubYear": "2022",
                    "journalTitle": "JAMA",
                }
            ]
        },
    }).encode("utf-8")

    def mock_transport(req: Request) -> bytes:
        return search_response

    client = EuropePMCClient(transport=mock_transport)
    candidates = client.search("salt intake hypertension", limit=5)
    assert len(candidates) == 1
    assert candidates[0].source_id == "europepmc-23456789"
    assert candidates[0].year == 2022
    assert candidates[0].venue == "JAMA"


def test_crossref_lookup_doi() -> None:
    crossref_response = json.dumps({
        "status": "ok",
        "message": {
            "DOI": "10.1001/jama.2022.0001",
            "title": ["Salt intake and hypertension risk in Asia"],
            "author": [{"given": "A", "family": "Nguyen"}],
            "published": {"date-parts": [[2022, 5, 1]]},
            "container-title": ["JAMA"],
        },
    }).encode("utf-8")

    def mock_transport(req: Request) -> bytes:
        return crossref_response

    client = CrossrefClient(mailto="doctor@example.org", transport=mock_transport)
    candidate = client.lookup_doi("10.1001/jama.2022.0001")
    assert candidate is not None
    assert candidate.doi == "10.1001/jama.2022.0001"
    assert candidate.year == 2022
    assert "Nguyen" in candidate.authors[0]


def test_local_source_caching(tmp_path: Path) -> None:
    cache_dir = tmp_path / "source-cache"
    key = "pubmed-12345678"
    data = b'{"mock": "data"}'

    assert get_cached_response(cache_dir, key) is None
    store_cached_response(cache_dir, key, data)
    assert get_cached_response(cache_dir, key) == data
