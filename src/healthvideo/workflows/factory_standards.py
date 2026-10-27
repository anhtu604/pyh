"""Versioned channel configuration, separate from medical and video approvals."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.factory_trials import (
    TRIAL_LOCK,
    stage_number,
    trial_bundle,
    trial_dir,
)

STANDARDS_FILE = Path('profiles/factory-standards.yaml')
SNAPSHOT = Path('workflow/standards.yaml')


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


def require_accepted(root: Path) -> dict[int, dict]:
    accepted = accepted_standards(root)
    if set(accepted) != {1, 2, 3, 4}:
        raise ValueError('Cần chấp nhận đủ 4 chuẩn trong Nghiệm thu xưởng trước khi Bật xưởng.')
    return accepted


def evidence_hash(bundle: dict) -> str:
    data = {'input_hash': bundle['input_hash'], 'outputs': bundle['outputs']}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def save_standard_draft(root: Path, stage: int, text: str, trial_id: str) -> dict:
    stage_number(stage)
    if not isinstance(text, str) or not text.strip() or len(text) > 8000:
        raise ValueError('Nhập chuẩn nháp (tối đa 8000 ký tự).')
    with TRIAL_LOCK:
        bundle = trial_bundle(root, trial_id)
        if bundle['stage'] != stage or bundle['status'] != 'ready':
            raise ValueError('Mẫu chưa ready hoặc sai giai đoạn.')
        draft = {'stage': stage, 'trial_id': trial_id, 'text': text.strip(),
                 'evidence_hash': evidence_hash(bundle), 'scope': 'draft'}
        write_yaml_atomic(trial_dir(root, trial_id) / 'standard-draft.yaml', draft)
        return draft


def accept_standard(root: Path, stage: int, *, trial_id: str, expected_input_hash: str,
                    expected_version: int, reviewer: str, now: datetime,
                    expected_text: str | None = None, expected_standards_hash: str | None = None) -> dict:
    stage_number(stage)
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError('Nhập tên người chấp nhận chuẩn.')
    if type(expected_version) is not int or expected_version < 0:
        raise ValueError('Version không hợp lệ.')
    with TRIAL_LOCK:
        history = _history(root)
        if expected_standards_hash is not None and expected_standards_hash != standards_hash(root):
            raise ValueError('Chuẩn đã thay đổi trong tab khác; tải lại và xem lại mẫu.')
        current = accepted_standards(root)
        if any(previous not in current for previous in range(1, stage)):
            raise ValueError('Chấp nhận theo thứ tự giai đoạn 1 → 4.')
        if current.get(stage, {}).get('version', 0) != expected_version:
            raise ValueError('Version stale; tải lại mẫu và chuẩn.')
        bundle = trial_bundle(root, trial_id)
        draft = bundle['draft']
        if expected_text is not None and expected_text != draft.get('text'):
            raise ValueError('Nháp đã thay đổi trong tab khác; tải lại trước khi chấp nhận.')
        if (bundle['stage'] != stage or bundle['status'] != 'ready' or not bundle['outputs']
                or bundle['input_hash'] != expected_input_hash
                or draft.get('evidence_hash') != evidence_hash(bundle)):
            raise ValueError('Mẫu failed/stale hoặc nháp không còn khớp bằng chứng.')
        entry = {'id': uuid4().hex, 'stage': stage, 'version': expected_version + 1,
                 'text': draft['text'], 'reviewer': reviewer.strip(), 'accepted_at': now.isoformat(),
                 'trial_id': trial_id, 'evidence_hash': evidence_hash(bundle), 'scope': 'channel'}
        history.append(entry)
        write_yaml_atomic(root / STANDARDS_FILE, {'version': 1, 'entries': history,
                          'feedback_scope': 'Only chung and matching project slug; history preserved.'})
        return entry


def pin_standards(root: Path, project_dir: Path) -> Path:
    manifest = read_yaml(project_dir / 'project.yaml')
    revision = manifest['active_revision']
    if not isinstance(revision, str) or not revision.isdigit():
        raise ValueError('Invalid revision.')
    target = project_dir / 'revisions' / revision / SNAPSHOT
    if target.is_file():
        return target
    accepted = require_accepted(root)
    write_yaml_atomic(target, {'version': 1, 'standards': [accepted[s] for s in range(1, 5)]})
    return target
