"""Topic card aggregation and atomic YAML persistence for discovery (§5.1)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path

from healthvideo.discovery.models import (
    MissingApiKey,
    Signal,
    SignalSource,
    SourceError,
    SourceFailure,
    TopicCard,
)
from healthvideo.storage.files import write_yaml_atomic


def collect(
    query: str,
    *,
    fetchers: Mapping[SignalSource, Callable[[str], list[Signal]]],
) -> tuple[list[Signal], list[SourceFailure]]:
    signals: list[Signal] = []
    failures: list[SourceFailure] = []
    for source, fetcher in fetchers.items():
        try:
            signals.extend(fetcher(query))
        except MissingApiKey as exc:
            reason = str(exc).strip() or (
                "thiếu YOUTUBE_API_KEY"
                if source == "youtube"
                else f"thiếu API key cho {source}"
            )
            failures.append(SourceFailure(source=source, reason=reason))
        except SourceError as exc:
            failures.append(SourceFailure(source=source, reason=exc.reason))
    return signals, failures


def build_card(
    title: str,
    question: str,
    signals: list[Signal],
    *,
    layers: list[str],
    pubmed_count: int | None,
) -> TopicCard:
    metrics = [signal.metric for signal in signals if signal.metric is not None]
    heat = float(sum(metrics)) if metrics else None
    return TopicCard(
        title=title,
        question=question,
        misconceptions=list(signals),
        heat=heat,
        layers=list(layers),
        pubmed_count=pubmed_count,
    )


def write_discovered(
    root: Path,
    cards: list[TopicCard],
    failures: list[SourceFailure],
    *,
    today: date,
) -> Path:
    path = root / "topics" / "discovered" / f"{today.isoformat()}.yaml"
    payload = {
        "cards": [card.model_dump(mode="json") for card in cards],
        "failures": [failure.model_dump(mode="json") for failure in failures],
    }
    write_yaml_atomic(path, payload)
    return path
