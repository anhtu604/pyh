"""Google Trends RSS signal fetcher for topic discovery (§5.1)."""

from __future__ import annotations

import math
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime

from healthvideo.discovery.models import Signal, SourceError
from healthvideo.evidence.clients import (
    DEFAULT_USER_AGENT,
    Transport,
    _default_transport,
)

TRENDS_RSS_URL = "https://trends.google.com/trending/rss"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def parse_approx_traffic(raw: str | None) -> float | None:
    """Parse Google Trends `<ht:approx_traffic>` text (e.g. '2000+' -> 2000.0)."""
    if raw is None:
        return None
    cleaned = raw.strip().rstrip("+").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def _child_text(element: ET.Element, local_name: str) -> str | None:
    for child in element:
        is_match = child.tag == local_name or child.tag.endswith(f"}}{local_name}")
        if is_match and child.text is not None:
            return child.text.strip()
    return None


def fetch_signals(
    *,
    geo: str = "VN",
    transport: Transport | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> list[Signal]:
    active_transport = transport or _default_transport
    params = urllib.parse.urlencode({"geo": geo})
    url = f"{TRENDS_RSS_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    try:
        raw = active_transport(req)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise SourceError("trends", str(exc)) from exc

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise SourceError("trends", f"XML không hợp lệ: {exc}") from exc

    fetched_at = now()
    signals: list[Signal] = []
    for item in root.iter():
        if not (item.tag == "item" or item.tag.endswith("}item")):
            continue
        title = _child_text(item, "title")
        if not title:
            continue
        link = _child_text(item, "link")
        if not link:
            query_str = urllib.parse.urlencode({"q": title})
            link = f"https://www.google.com/search?{query_str}"
        traffic_raw = _child_text(item, "approx_traffic")
        signals.append(
            Signal(
                source="trends",
                url=link,
                text=title,
                metric=parse_approx_traffic(traffic_raw),
                fetched=fetched_at,
            )
        )
    return signals
