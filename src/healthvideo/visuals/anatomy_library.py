import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

from healthvideo.storage.files import sha256_file, write_text_atomic

LIBRARY_PATH = Path("video/src/anatomy/library.json")
APPROVED_PATH = Path("video/src/anatomy/approved.json")
ComponentStatus = Literal["approved", "new", "modified"]


def _anatomy_dir(repo: Path) -> Path:
    return (repo / LIBRARY_PATH).parent


def _component_file(repo: Path, filename: str) -> Path:
    anatomy_dir = _anatomy_dir(repo).resolve()
    path = (anatomy_dir / filename).resolve()
    if not path.is_relative_to(anatomy_dir):
        raise ValueError(
            f"Anatomy component file must stay inside {anatomy_dir}: {filename}"
        )
    return path


def load_library(repo: Path) -> dict[str, dict[str, Any]]:
    raw = json.loads((repo / LIBRARY_PATH).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or not isinstance(raw.get("components"), Mapping):
        raise TypeError(f"Invalid anatomy library schema in {repo / LIBRARY_PATH}")
    components: dict[str, dict[str, Any]] = {}
    for subject, info in raw["components"].items():
        if not isinstance(subject, str) or not isinstance(info, Mapping):
            raise TypeError(f"Invalid anatomy component entry for {subject!r}")
        if not isinstance(info.get("file"), str) or not info["file"].strip():
            raise ValueError(f"Anatomy component {subject!r} is missing 'file'")
        components[subject] = dict(info)
    return components


def _load_approved(repo: Path) -> dict[str, dict[str, Any]]:
    path = repo / APPROVED_PATH
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise TypeError(f"Invalid approved anatomy file: {path}")
    entries = (
        raw.get("components")
        if isinstance(raw.get("components"), Mapping)
        else raw
    )
    return {
        str(subject): dict(record)
        for subject, record in entries.items()
        if isinstance(record, Mapping)
    }


def library_status(repo: Path) -> dict[str, ComponentStatus]:
    components = load_library(repo)
    approved = _load_approved(repo)
    statuses: dict[str, ComponentStatus] = {}
    for subject, info in components.items():
        current_sha = sha256_file(_component_file(repo, info["file"]))
        record = approved.get(subject)
        recorded_sha = record.get("sha256") if isinstance(record, Mapping) else None
        if not isinstance(recorded_sha, str) or not recorded_sha:
            statuses[subject] = "new"
        elif recorded_sha != current_sha:
            statuses[subject] = "modified"
        else:
            statuses[subject] = "approved"
    return statuses


def record_approval(
    repo: Path,
    subjects: Iterable[str],
    *,
    project: str,
    revision: str,
) -> None:
    components = load_library(repo)
    approved = _load_approved(repo)
    for subject in subjects:
        if subject not in components:
            raise KeyError(f"Unknown anatomy subject: {subject}")
        sha256 = sha256_file(_component_file(repo, components[subject]["file"]))
        approved[subject] = {
            "sha256": sha256,
            "project": project,
            "revision": revision,
        }
    payload = {
        "version": 1,
        "components": approved,
    }
    write_text_atomic(
        repo / APPROVED_PATH,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def cue_actions(repo: Path, subject: str) -> tuple[str, ...]:
    """Read the component's exported action declaration; no second allow-list."""
    info = load_library(repo).get(subject)
    if info is None:
        raise ValueError(f"Unknown anatomy subject: {subject}")
    source = _component_file(repo, info["file"]).read_text(encoding="utf-8")
    match = re.search(r"export const CUE_ACTIONS[^=]*=\s*\[([^\]]*)\]", source)
    if match is None:
        raise ValueError(f"Component {subject} must export CUE_ACTIONS")
    return tuple(re.findall(r"['\"]([^'\"]+)['\"]", match[1]))
