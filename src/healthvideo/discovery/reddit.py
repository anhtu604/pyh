"""Reddit JSON search signal fetcher for topic discovery (§5.1)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime

from healthvideo.discovery.models import Signal, SourceError
from healthvideo.evidence.clients import (
    DEFAULT_USER_AGENT,
    Transport,
    _default_transport,
)

REDDIT_SEARCH_URL = "https://www.reddit.com/search.json"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def fetch_signals(
    query: str,
    *,
    transport: Transport | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> list[Signal]:
    active_transport = transport or _default_transport
    params = urllib.parse.urlencode(
        {
            "q": query,
            "sort": "top",
            "t": "month",
            "limit": "25",
        }
    )
    url = f"{REDDIT_SEARCH_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    try:
        raw = active_transport(req)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise SourceError("reddit", str(exc)) from exc

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SourceError("reddit", f"JSON không hợp lệ: {exc}") from exc

    if not isinstance(payload, dict):
        raise SourceError("reddit", "Phản hồi Reddit không phải JSON object")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("children"), list):
        raise SourceError("reddit", "Thiếu data.children trong phản hồi Reddit")

    fetched_at = now()
    signals: list[Signal] = []
    for child in data["children"]:
        if not isinstance(child, dict):
            continue
        post = child.get("data")
        if not isinstance(post, dict):
            continue
        title = post.get("title")
        permalink = post.get("permalink")
        if (
            not isinstance(title, str)
            or not title
            or not isinstance(permalink, str)
            or not permalink
        ):
            continue
        post_url = (
            permalink
            if permalink.startswith(("http://", "https://"))
            else f"https://www.reddit.com{permalink}"
        )
        raw_score = post.get("score")
        metric: float | None = None
        if isinstance(raw_score, int | float) and not isinstance(raw_score, bool):
            metric = float(raw_score)
        signals.append(
            Signal(
                source="reddit",
                url=post_url,
                text=title,
                metric=metric,
                fetched=fetched_at,
            )
        )
    return signals
