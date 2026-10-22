"""Tests for YouTube discovery signal fetcher."""

from __future__ import annotations

import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.discovery.models import MissingApiKey, SourceError
from healthvideo.discovery.youtube import fetch_signals

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXED_NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)


def test_youtube_parse_fixture() -> None:
    search_bytes = (FIXTURES_DIR / "youtube_search.json").read_bytes()
    videos_bytes = (FIXTURES_DIR / "youtube_videos.json").read_bytes()
    seen_urls: list[str] = []

    def fake_transport(req: urllib.request.Request) -> bytes:
        seen_urls.append(req.full_url)
        if "/youtube/v3/search?" in req.full_url:
            return search_bytes
        if "/youtube/v3/videos?" in req.full_url:
            return videos_bytes
        raise AssertionError(f"Unexpected URL: {req.full_url}")

    signals = fetch_signals(
        "trào ngược dạ dày",
        api_key="test-key-123",
        transport=fake_transport,
        now=lambda: FIXED_NOW,
    )

    assert len(seen_urls) == 2
    assert "regionCode=VN" in seen_urls[0]
    assert "relevanceLanguage=vi" in seen_urls[0]
    assert "id=vid_101%2Cvid_202" in seen_urls[1]

    assert len(signals) == 2
    assert signals[0].source == "youtube"
    assert signals[0].url == "https://www.youtube.com/watch?v=vid_101"
    assert signals[0].text == "Uống nước chanh ấm buổi sáng có giải độc gan không?"
    assert signals[0].metric == 15400.0
    assert signals[0].fetched == FIXED_NOW

    assert signals[1].source == "youtube"
    assert signals[1].url == "https://www.youtube.com/watch?v=vid_202"
    assert signals[1].text == "Nhịn ăn gián đoạn và trào ngược dạ dày"
    assert signals[1].metric is None
    assert signals[1].fetched == FIXED_NOW


def test_youtube_missing_api_key_raises() -> None:
    with pytest.raises(MissingApiKey):
        fetch_signals("trào ngược", api_key=None)


def test_youtube_network_error_raises_source_error() -> None:
    def failing_transport(req: urllib.request.Request) -> bytes:
        raise urllib.error.URLError("connection refused")

    with pytest.raises(SourceError) as exc_info:
        fetch_signals("trào ngược", api_key="key", transport=failing_transport)
    assert exc_info.value.source == "youtube"
    assert "connection refused" in exc_info.value.reason


def test_youtube_malformed_json_raises_source_error() -> None:
    def bad_json_transport(req: urllib.request.Request) -> bytes:
        return b"{not-valid-json"

    with pytest.raises(SourceError) as exc_info:
        fetch_signals("trào ngược", api_key="key", transport=bad_json_transport)
    assert exc_info.value.source == "youtube"
