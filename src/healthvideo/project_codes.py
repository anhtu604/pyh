"""Persistent, human-readable project codes independent of revision and title."""

import re
import threading
from pathlib import Path

import yaml

from healthvideo.agents import _quota_lock
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.queue import load_queue

_LOCK = threading.Lock()


def _read_codes(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = read_yaml(path)
        codes = data.get('codes')
        if data.get('version') != 1 or not isinstance(codes, dict):
            raise ValueError('Invalid project-code registry')
        for slug, code in codes.items():
            if (not isinstance(slug, str) or not slug
                    or not isinstance(code, str) or not re.fullmatch(r'PYH-[0-9]{3,}', code)
                    or int(code[4:]) < 1 or code != f'PYH-{int(code[4:]):03d}'):
                raise ValueError('Invalid project-code mapping')
        if len(set(codes.values())) != len(codes):
            raise ValueError('Duplicate project-code mapping')
        return dict(codes)
    except (TypeError, yaml.YAMLError) as exc:
        raise ValueError('Invalid project-code registry') from exc


def project_codes(root: Path) -> dict[str, str]:
    """Allocate codes once; retain retired entries and never reuse their numbers."""
    path = root / 'topics/project-codes.yaml'
    with _LOCK, _quota_lock(root / 'cache/project-codes'):
        codes = _read_codes(path)
        projects = sorted(p.parent.name for p in (root / 'projects').glob('*/project.yaml'))
        try:
            queued = [entry.slug for entry in sorted(load_queue(root),
                                                    key=lambda entry: (entry.added, entry.slug))]
        except (OSError, ValueError, TypeError, yaml.YAMLError):
            # A broken queue must not hide codes of existing projects.
            queued = []
        number = max((int(code[4:]) for code in codes.values()), default=0)
        changed = False
        for slug in dict.fromkeys([*queued, *projects]):
            if slug not in codes:
                number += 1
                codes[slug] = f'PYH-{number:03d}'
                changed = True
        if changed:
            write_yaml_atomic(path, {'version': 1, 'codes': codes})
        return codes
