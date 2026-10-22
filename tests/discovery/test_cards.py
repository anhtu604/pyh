"""Tests for discovery card building, collection, and YAML persistence."""

from __future__ import annotations

import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from healthvideo.discovery.cards import build_card, collect, write_discovered
from healthvideo.discovery.models import Signal, SourceError, SourceFailure, TopicCard
from healthvideo.discovery.reddit import fetch_signals as fetch_reddit_signals
from healthvideo.discovery.youtube import fetch_signals as fetch_youtube_signals
from healthvideo.storage.files import read_yaml

FIXED_NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)


def test_card_without_metric_has_no_heat() -> None:
    signals = [
        Signal(
            source="reddit",
            url="https://www.reddit.com/r/health/comments/1/a/",
            text="Uống giấm táo chữa trào ngược dạ dày",
            metric=None,
            fetched=FIXED_NOW,
        ),
        Signal(
            source="trends",
            url="https://trends.google.com/trending/rss?geo=VN#giam-tao",
            text="giấm táo dạ dày",
            metric=None,
            fetched=FIXED_NOW,
        ),
    ]
    card = build_card(
        "Trào ngược dạ dày thực quản và giấm táo",
        "Uống giấm táo có làm giảm trào ngược axit dạ dày không?",
        signals,
        layers=["anatomy", "physiology", "pathophysiology"],
        pubmed_count=18,
    )
    assert card.heat is None


def test_misconceptions_only_from_signals() -> None:
    signals = [
        Signal(
            source="youtube",
            url="https://www.youtube.com/watch?v=vid_101",
            text="Uống nước chanh ấm buổi sáng có giải độc gan không?",
            metric=15400.0,
            fetched=FIXED_NOW,
        ),
    ]
    card = build_card(
        "Giải độc gan bằng nước chanh",
        "Nước chanh ấm có thải độc gan như lời đồn không?",
        signals,
        layers=["anatomy", "physiology"],
        pubmed_count=12,
    )
    assert card.misconceptions == signals
    assert len(card.misconceptions) == 1
    assert card.misconceptions[0] == signals[0]
    assert card.heat == 15400.0


def test_missing_youtube_key_skips_source() -> None:
    expected_signal = Signal(
        source="reddit",
        url="https://www.reddit.com/r/vozforums/comments/abc/trao_nguoc/",
        text="Trào ngược dạ dày khi nằm nghiêng bên phải",
        metric=85.0,
        fetched=FIXED_NOW,
    )
    signals, failures = collect(
        "trào ngược dạ dày",
        fetchers={
            "youtube": lambda q: fetch_youtube_signals(q, api_key=None),
            "reddit": lambda q: [expected_signal],
        },
    )
    assert signals == [expected_signal]
    assert len(failures) == 1
    assert failures[0].source == "youtube"
    assert "YOUTUBE_API_KEY" in failures[0].reason


def test_provider_error_reported_not_swallowed() -> None:
    def failing_transport(req: urllib.request.Request) -> bytes:
        raise urllib.error.URLError("network unreachable")

    with pytest.raises(SourceError) as exc_info:
        fetch_reddit_signals("trào ngược", transport=failing_transport)
    assert exc_info.value.source == "reddit"
    assert "network unreachable" in exc_info.value.reason

    signals, failures = collect(
        "trào ngược",
        fetchers={
            "reddit": lambda q: fetch_reddit_signals(q, transport=failing_transport),
        },
    )
    assert signals == []
    assert len(failures) == 1
    assert failures[0] == SourceFailure(
        source="reddit",
        reason=exc_info.value.reason,
    )


def test_write_discovered_roundtrip_vietnamese(tmp_path: Path) -> None:
    signal = Signal(
        source="youtube",
        url="https://www.youtube.com/watch?v=vn_health_01",
        text="Tại sao ăn khuya dễ gây trào ngược dạ dày thực quản?",
        metric=3200.0,
        fetched=FIXED_NOW,
    )
    card = build_card(
        "Cơ chế đóng mở cơ vòng thực quản dưới",
        "Vì sao nằm ngay sau bữa ăn tối làm dịch vị trào lên thực quản?",
        [signal],
        layers=["anatomy", "physiology", "pathophysiology"],
        pubmed_count=42,
    )
    failure = SourceFailure(source="youtube", reason="thiếu YOUTUBE_API_KEY")
    today = date(2026, 10, 22)

    out_path = write_discovered(tmp_path, [card], [failure], today=today)

    assert out_path == tmp_path / "topics" / "discovered" / "2026-10-22.yaml"
    assert out_path.is_file()

    raw_text = out_path.read_text(encoding="utf-8")
    assert "Cơ chế đóng mở cơ vòng thực quản dưới" in raw_text
    assert "Tại sao ăn khuya dễ gây trào ngược dạ dày thực quản?" in raw_text

    loaded = read_yaml(out_path)
    loaded_cards = [TopicCard.model_validate(item) for item in loaded["cards"]]
    loaded_failures = [
        SourceFailure.model_validate(item) for item in loaded["failures"]
    ]

    assert loaded_cards == [card]
    assert loaded_failures == [failure]
