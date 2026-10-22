"""Tests for Google Trends RSS discovery signal fetcher."""

from __future__ import annotations

import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.discovery.models import SourceError
from healthvideo.discovery.trends import fetch_signals, parse_approx_traffic

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXED_NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)


def test_trends_parse_fixture() -> None:
    rss_bytes = (FIXTURES_DIR / "trends_rss.xml").read_bytes()
    seen_urls: list[str] = []

    def fake_transport(req: urllib.request.Request) -> bytes:
        seen_urls.append(req.full_url)
        return rss_bytes

    signals = fetch_signals(geo="VN", transport=fake_transport, now=lambda: FIXED_NOW)

    assert seen_urls == ["https://trends.google.com/trending/rss?geo=VN"]
    assert len(signals) == 2

    assert signals[0].source == "trends"
    assert signals[0].text == "trào ngược dạ dày"
    assert signals[0].url == "https://trends.google.com/trending/rss?geo=VN#trao-nguoc"
    assert signals[0].metric == 2000.0
    assert signals[0].fetched == FIXED_NOW

    assert signals[1].source == "trends"
    assert signals[1].text == "men gan cao"
    assert signals[1].url.startswith("https://www.google.com/search?q=")
    assert signals[1].metric is None
    assert signals[1].fetched == FIXED_NOW


def test_trends_traffic_parse() -> None:
    assert parse_approx_traffic("2000+") == 2000.0
    assert parse_approx_traffic("2,000+") == 2000.0
    assert parse_approx_traffic("500") == 500.0
    assert parse_approx_traffic("abc") is None
    assert parse_approx_traffic("") is None
    assert parse_approx_traffic(None) is None


def test_trends_error_raises_source_error() -> None:
    def failing_transport(req: urllib.request.Request) -> bytes:
        raise urllib.error.URLError("dns lookup failed")

    with pytest.raises(SourceError) as exc_info:
        fetch_signals(geo="VN", transport=failing_transport)
    assert exc_info.value.source == "trends"
    assert "dns lookup failed" in exc_info.value.reason


def test_trends_bad_xml_raises_source_error() -> None:
    def bad_xml_transport(req: urllib.request.Request) -> bytes:
        return b"<rss><unclosed>"

    with pytest.raises(SourceError) as exc_info:
        fetch_signals(geo="VN", transport=bad_xml_transport)
    assert exc_info.value.source == "trends"
