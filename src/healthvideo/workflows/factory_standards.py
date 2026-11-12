"""Versioned channel configuration, separate from medical and video approvals."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from healthvideo.storage.files import read_yaml, write_yaml_atomic

STANDARDS_FILE = Path('profiles/factory-standards.yaml')
SNAPSHOT = Path('workflow/standards.yaml')


def stage_number(stage: int) -> int:
    if type(stage) is not int or stage not in range(1, 5):
        raise ValueError('Giai đoạn phải từ 1 đến 4.')
    return stage


def _history(root: Path) -> list[dict]:
    path = root / STANDARDS_FILE
    if not path.exists():
        return []
    data = read_yaml(path)
    entries = data.get('entries')
    if not isinstance(entries, list):
        raise TypeError('Standards history invalid; restore before acceptance.')
    versions: dict[int, int] = {}
    for entry in entries:
        stage = stage_number(entry['stage'])
        if entry['version'] != versions.get(stage, 0) + 1 or entry.get('scope') != 'channel':
            raise ValueError('Standards history invalid.')
        versions[stage] = entry['version']
    return entries


def accepted_standards(root: Path) -> dict[int, dict]:
    return {entry['stage']: entry for entry in _history(root)}


def standards_hash(root: Path) -> str:
    return hashlib.sha256(json.dumps(accepted_standards(root), sort_keys=True).encode()).hexdigest()


def pin_standards(root: Path, project_dir: Path) -> Path:
    manifest = read_yaml(project_dir / 'project.yaml')
    revision = manifest['active_revision']
    if not isinstance(revision, str) or not revision.isdigit():
        raise ValueError('Invalid revision.')
    target = project_dir / 'revisions' / revision / SNAPSHOT
    if target.is_file():
        return target
    accepted = accepted_standards(root)
    write_yaml_atomic(target, {'version': 1, 'standards': [accepted[s] for s in sorted(accepted)]})
    return target
