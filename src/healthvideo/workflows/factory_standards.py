"""Versioned channel configuration, separate from medical and video approvals."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic

STANDARDS_FILE = Path('profiles/factory-standards.yaml')
STYLE_SPEC_FILE = Path('docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md')
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


def style_spec_pin(root: Path) -> dict[str, str] | None:
    """Return path + sha256 for the PYH Style A spec when present in ``root``."""
    spec = root / STYLE_SPEC_FILE
    if not spec.is_file():
        return None
    return {
        'path': STYLE_SPEC_FILE.as_posix(),
        'sha256': sha256_file(spec),
    }


def pinned_style_spec(revision_root: Path) -> dict[str, str] | None:
    """Read pinned ``style_spec`` from a revision's ``workflow/standards.yaml``, if any."""
    snapshot = revision_root / SNAPSHOT
    if not snapshot.is_file():
        return None
    data = read_yaml(snapshot)
    if not isinstance(data, dict):
        return None
    spec = data.get('style_spec')
    if not isinstance(spec, dict):
        return None
    path = spec.get('path')
    digest = spec.get('sha256')
    if (
        not isinstance(path, str)
        or not path.strip()
        or not isinstance(digest, str)
        or not digest.strip()
    ):
        return None
    return {'path': path, 'sha256': digest}


def style_a_active(revision_root: Path) -> bool:
    """Return True when ``revision_root`` pins PYH Style A in ``workflow/standards.yaml``."""
    spec = pinned_style_spec(revision_root)
    return spec is not None and spec.get('path') == STYLE_SPEC_FILE.as_posix()


def standards_hash(root: Path) -> str:
    accepted = accepted_standards(root)
    style_spec = style_spec_pin(root)
    payload: object = (
        accepted
        if style_spec is None
        else {'standards': accepted, 'style_spec': style_spec}
    )
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def pin_standards(root: Path, project_dir: Path) -> Path:
    manifest = read_yaml(project_dir / 'project.yaml')
    revision = manifest['active_revision']
    if not isinstance(revision, str) or not revision.isdigit():
        raise ValueError('Invalid revision.')
    target = project_dir / 'revisions' / revision / SNAPSHOT
    if target.is_file():
        return target
    accepted = accepted_standards(root)
    payload: dict[str, object] = {
        'version': 1,
        'standards': [accepted[s] for s in sorted(accepted)],
    }
    style_spec = style_spec_pin(root)
    if style_spec is not None:
        payload['style_spec'] = style_spec
    write_yaml_atomic(target, payload)
    return target
