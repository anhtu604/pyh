"""Tests for Reddit search JSON discovery signal fetcher."""

from __future__ import annotations

import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.discovery.models import SourceError
from healthvideo.discovery.reddit import fetch_signals
from healthvideo.evidence.clients import DEFAULT_USER_AGENT

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXED_NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)


def test_reddit_parse_fixture() -> None:
    json_bytes = (FIXTURES_DIR / "reddit_search.json").read_bytes()
    seen_requests: list[urllib.request.Request] = []

    def fake_transport(req: urllib.request.Request) -> bytes:
        seen_requests.append(req)
        return json_bytes

    signals = fetch_signals(
        "đau dạ dày",
        transport=fake_transport,
        now=lambda: FIXED_NOW,
    )

    assert len(seen_requests) == 1
    req = seen_requests[0]
    assert req.full_url.startswith("https://www.reddit.com/search.json?")
    assert "sort=top" in req.full_url
    assert "t=month" in req.full_url
    assert "limit=25" in req.full_url
    assert req.get_header("User-agent") == DEFAULT_USER_AGENT

    assert len(signals) == 2
    assert signals[0].source == "reddit"
    assert signals[0].text == "Có ai bị đau dạ dày khi uống cà phê sáng không?"
    assert signals[0].url == (
        "https://www.reddit.com/r/vozforums/comments/abc123/dau_da_day_ca_phe/"
    )
    assert signals[0].metric == 142.0
    assert signals[0].fetched == FIXED_NOW

    assert signals[1].source == "reddit"
    assert signals[1].text == "Hỏi về cơ chế trào ngược axit ban đêm"
    assert signals[1].url == (
        "https://www.reddit.com/r/health/comments/def456/trao_nguoc_axit/"
    )
    assert signals[1].metric is None
    assert signals[1].fetched == FIXED_NOW


def test_reddit_error_raises_source_error() -> None:
    def failing_transport(req: urllib.request.Request) -> bytes:
        raise urllib.error.URLError("timeout")

    with pytest.raises(SourceError) as exc_info:
        fetch_signals("đau dạ dày", transport=failing_transport)
    assert exc_info.value.source == "reddit"
    assert "timeout" in exc_info.value.reason


def test_reddit_bad_json_raises_source_error() -> None:
    def bad_json_transport(req: urllib.request.Request) -> bytes:
        return b"<html>Rate limited</html>"

    with pytest.raises(SourceError) as exc_info:
        fetch_signals("đau dạ dày", transport=bad_json_transport)
    assert exc_info.value.source == "reddit"
