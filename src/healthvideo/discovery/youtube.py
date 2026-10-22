"""YouTube Data API v3 signal fetcher for topic discovery (§5.1)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime

from healthvideo.discovery.models import MissingApiKey, Signal, SourceError
from healthvideo.evidence.clients import (
    DEFAULT_USER_AGENT,
    Transport,
    _default_transport,
)

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _request_json(url: str, transport: Transport) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    try:
        raw = transport(req)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise SourceError("youtube", str(exc)) from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SourceError("youtube", f"JSON không hợp lệ: {exc}") from exc
    if not isinstance(data, dict):
        raise SourceError("youtube", "Phản hồi YouTube không phải JSON object")
    if "error" in data:
        err = data["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise SourceError("youtube", msg)
    return data


def fetch_signals(
    query: str,
    *,
    api_key: str | None,
    transport: Transport | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> list[Signal]:
    if not api_key:
        raise MissingApiKey("thiếu YOUTUBE_API_KEY")

    active_transport = transport or _default_transport
    search_params = urllib.parse.urlencode(
        {
            "part": "snippet",
            "type": "video",
            "q": query,
            "regionCode": "VN",
            "relevanceLanguage": "vi",
            "maxResults": "10",
            "key": api_key,
        }
    )
    search_url = f"{YOUTUBE_SEARCH_URL}?{search_params}"
    search_data = _request_json(search_url, active_transport)
    items = search_data.get("items")
    if not isinstance(items, list):
        raise SourceError("youtube", "Thiếu danh sách items trong phản hồi search")

    video_entries: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        id_obj = item.get("id")
        video_id = id_obj.get("videoId") if isinstance(id_obj, dict) else None
        snippet = item.get("snippet")
        title = snippet.get("title") if isinstance(snippet, dict) else None
        if (
            isinstance(video_id, str)
            and video_id
            and isinstance(title, str)
            and title
        ):
            video_entries.append((video_id, title))

    if not video_entries:
        return []

    stats_params = urllib.parse.urlencode(
        {
            "part": "statistics",
            "id": ",".join(vid for vid, _ in video_entries),
            "key": api_key,
        }
    )
    stats_url = f"{YOUTUBE_VIDEOS_URL}?{stats_params}"
    stats_data = _request_json(stats_url, active_transport)
    stats_items = stats_data.get("items")
    if not isinstance(stats_items, list):
        raise SourceError("youtube", "Thiếu danh sách items trong phản hồi videos")

    view_counts: dict[str, float | None] = {}
    for item in stats_items:
        if not isinstance(item, dict):
            continue
        vid = item.get("id")
        stats = item.get("statistics")
        if not isinstance(vid, str) or not isinstance(stats, dict):
            continue
        raw_views = stats.get("viewCount")
        if raw_views is None:
            view_counts[vid] = None
            continue
        try:
            view_counts[vid] = float(raw_views)
        except (TypeError, ValueError):
            view_counts[vid] = None

    fetched_at = now()
    return [
        Signal(
            source="youtube",
            url=f"https://www.youtube.com/watch?v={vid}",
            text=title,
            metric=view_counts.get(vid),
            fetched=fetched_at,
        )
        for vid, title in video_entries
    ]
