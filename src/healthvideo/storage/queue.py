"""YAML storage for the topic queue."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from healthvideo.domain.queue import QueueEntry, QueueError
from healthvideo.storage.files import read_yaml, write_yaml_atomic

_QUEUE_VERSION = 1


def queue_path(root: Path) -> Path:
    """Return the path to the topic queue YAML file under ``root``."""
    return root / "topics" / "queue.yaml"


def _serialize_entry(entry: QueueEntry) -> dict[str, Any]:
    return {
        "slug": entry.slug,
        "title": entry.title,
        "question": entry.question,
        "doctor_note": entry.doctor_note,
        "added": entry.added.isoformat(),
    }


def load_queue(root: Path) -> list[QueueEntry]:
    """Load the topic queue from ``root / 'topics' / 'queue.yaml'``."""
    path = queue_path(root)
    if not path.exists():
        return []
    data = read_yaml(path)
    if data.get("version") != _QUEUE_VERSION:
        raise QueueError(f"Unsupported queue version in {path}: {data.get('version')}")
    raw_entries = data.get("entries", [])
    if not isinstance(raw_entries, list):
        raise QueueError(f"Invalid queue entries list in {path}")
    return [QueueEntry.model_validate(item) for item in raw_entries]


def add_to_queue(root: Path, entry: QueueEntry) -> None:
    """Append an entry to the topic queue atomically, rejecting duplicate slugs."""
    entries = load_queue(root)
    if any(existing.slug == entry.slug for existing in entries):
        raise QueueError(f"Slug already in queue: {entry.slug}")
    if (root / "projects" / entry.slug).exists():
        raise QueueError(f"Project already exists for slug: {entry.slug}")

    entries.append(entry)
    payload = {
        "version": _QUEUE_VERSION,
        "entries": [_serialize_entry(item) for item in entries],
    }
    write_yaml_atomic(queue_path(root), payload)
