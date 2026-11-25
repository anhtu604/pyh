"""Append-only factory playbook for deterministic self-healing and doctor-guided learning."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from healthvideo.storage.files import read_yaml, write_yaml_atomic

PLAYBOOK_REL = Path('profiles/factory-playbook.yaml')

DelegateRole = Literal[
    'writer',
    'medical_expert',
    'editor',
    'storyboard_director',
    'shorts_producer',
    'voice_director',
]
PlaybookAction = Literal['retry', 'retry_cycle', 'delegate']
PlaybookSource = Literal['seed', 'doctor']

TRANSIENT_BACKOFF_SECONDS: tuple[int, ...] = (300, 900, 2700)
DEFAULT_AUTO_RETRIES = 2
_REQUIRES_DOCTOR_VALUES = frozenset({'pin', 'gate', 'account', 'safety'})

_RULE_ID_RE = re.compile(r'^PB-(\d{3,})$')
_ISO_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

_INCIDENT_PREFIX_PATTERNS = (
    re.compile(r'^bước\s+\S+:\s+(?:đang chờ thử lại lúc \S+|cần sửa đầu vào hoặc cấu hình);\s*', re.IGNORECASE),
    re.compile(r'^bước\s+\S+\s+lỗi:\s*', re.IGNORECASE),
    re.compile(r'^visual_review\s+lỗi:\s*', re.IGNORECASE),
    re.compile(r'^chấm\s+kịch\s+bản\s+lỗi:\s*', re.IGNORECASE),
    re.compile(r'^(?:ValueError|RuntimeError|OSError|TimeoutError|URLError):\s*', re.IGNORECASE),
)

_TRANSIENT_NETWORK_RE = re.compile(
    r'timeouterror|timed\s+out|urlerror|connectionreset|connection\s+reset'
    r'|oa\s+retrieval\s+failed'
    r'|http(?:\s+error)?\s*[:=]?\s*(?:429|5\d\d)\b'
    r'|\bstatus(?:\s+code)?\s*[:=]?\s*(?:429|5\d\d)\b'
    r'|\bcode\s+(?:429|5\d\d)\b',
    re.IGNORECASE,
)

_FORBIDDEN_TEXT_RE = re.compile(
    r'\bpin\b'
    r'|mở\s+cổng|mo\s+cong'
    r'|duyệt\s+(?:y\s+khoa|video|cổng)|duyet\s+(?:y\s+khoa|video|cong)'
    r'|tài\s+khoản|tai\s+khoan|\boauth\b|đăng\s+nhập|dang\s+nhap|\bapi[_\s-]?key\b|\bcredential'
    r'|blocking_safety'
    r'|góp\s+ý\s+y\s+khoa\s+chưa\s+có\s+vị\s+trí'
    r'|lỗi\s+an\s+toàn',
    re.IGNORECASE,
)

_WINDOWS_PATH_RE = re.compile(r'[a-zA-Z]:[\\/](?:[^\n\r\\/,:;)\]]+[\\/])*[^\s,;)\]]+')
_POSIX_PATH_RE = re.compile(r'(?:^|(?<=[\s(\'":=]))/(?:[\w.\-]+/)+[\w.\-]+')
_REL_PATH_RE = re.compile(
    r'\b(?:projects|topics|revisions|reviews|cache|logs|src|tests|tools|profiles|video)[\\/][^\s,;)\]]+',
    re.IGNORECASE,
)
_ISO_TS_RE = re.compile(
    r'\b\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?\b'
)
_HEX_HASH_RE = re.compile(r'\b(?:dq-|repair-|sha256:)?[0-9a-f]{8,64}\b', re.IGNORECASE)
_COUNTS_RE = re.compile(
    r'\b(?:rev(?:ision)?\s*\d+|attempt\s*\d+|lần\s*\d+|vòng\s*\d+|\d+\s*vòng|\d+\s*chu\s*kỳ|\d+/\d+)\b',
    re.IGNORECASE,
)
_ERROR_KIND_RE = re.compile(r'\b([A-Z][A-Za-z0-9]*(?:Error|Exception))\b')


class PlaybookMatch(BaseModel):
    model_config = ConfigDict(extra='forbid')

    station: str = Field(default='repair', min_length=1)
    signature: str = Field(min_length=1)


class PlaybookRule(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str = Field(pattern=r'^PB-\d{3,}$')
    created: str | None = None
    source: PlaybookSource | None = None
    question_id: str | None = None
    slug: str | None = None
    match: PlaybookMatch | None = None
    action: PlaybookAction | None = None
    delegate_role: DelegateRole | None = None
    direction: str | None = None
    max_auto_per_incident: int = Field(default=1, ge=1, le=5)
    disables: str | None = Field(default=None, pattern=r'^PB-\d{3,}$')

    @field_validator('created')
    @classmethod
    def _validate_created(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _ISO_DATE_RE.fullmatch(value):
            raise ValueError('created phải theo định dạng YYYY-MM-DD.')
        date.fromisoformat(value)
        return value

    @model_validator(mode='after')
    def _validate_rule_shape(self) -> PlaybookRule:
        if self.disables is not None:
            if any(v is not None for v in (self.match, self.action, self.delegate_role)):
                raise ValueError('Mục disables không được chứa match, action hoặc delegate_role.')
            return self
        if not self.created or self.source is None or self.match is None or self.action is None:
            raise ValueError('Luật playbook cần đủ created, source, match và action.')
        if not (self.direction or '').strip():
            raise ValueError('Luật playbook cần direction không rỗng.')
        if self.action == 'delegate' and self.delegate_role is None:
            raise ValueError('action=delegate yêu cầu delegate_role.')
        if self.action != 'delegate' and self.delegate_role is not None:
            raise ValueError('Chỉ action=delegate mới được đặt delegate_role.')
        return self


class Playbook(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['1.0'] = '1.0'
    rules: list[PlaybookRule] = Field(default_factory=list)


def playbook_path(root: Path) -> Path:
    resolved_root = root.resolve()
    target = (resolved_root / PLAYBOOK_REL).resolve()
    if not target.is_relative_to(resolved_root):
        raise ValueError('Đường dẫn sổ định hướng nằm ngoài workspace.')
    return target


def load_playbook(root: Path) -> Playbook:
    path = playbook_path(root)
    if not path.is_file():
        return Playbook()
    raw = read_yaml(path)
    if not raw:
        return Playbook()
    return Playbook.model_validate(raw)


def active_rules(playbook: Playbook) -> list[PlaybookRule]:
    disabled = {rule.disables for rule in playbook.rules if rule.disables}
    return [
        rule for rule in playbook.rules
        if rule.disables is None and rule.id not in disabled
    ]


def next_rule_id(rules: Sequence[PlaybookRule]) -> str:
    highest = 0
    for rule in rules:
        match = _RULE_ID_RE.fullmatch(rule.id)
        if match:
            highest = max(highest, int(match.group(1)))
    return f'PB-{highest + 1:03d}'


def _rule_to_record(rule: PlaybookRule) -> dict[str, Any]:
    if rule.disables is not None:
        record: dict[str, Any] = {'id': rule.id}
        if rule.created:
            record['created'] = rule.created
        if rule.source:
            record['source'] = rule.source
        record['disables'] = rule.disables
        return record
    record = {
        'id': rule.id,
        'created': rule.created,
        'source': rule.source,
    }
    if rule.question_id:
        record['question_id'] = rule.question_id
    if rule.slug:
        record['slug'] = rule.slug
    record['match'] = rule.match.model_dump(mode='json') if rule.match else None
    record['action'] = rule.action
    if rule.delegate_role is not None:
        record['delegate_role'] = rule.delegate_role
    record['direction'] = rule.direction
    record['max_auto_per_incident'] = rule.max_auto_per_incident
    return record


def _append_raw_entry(root: Path, new_rule: PlaybookRule) -> PlaybookRule:
    path = playbook_path(root)
    if path.is_file():
        raw = read_yaml(path)
        Playbook.model_validate(raw)
        existing_entries = list(raw.get('rules') or [])
    else:
        existing_entries = []
    updated_entries = [*existing_entries, _rule_to_record(new_rule)]
    payload = {'schema_version': '1.0', 'rules': updated_entries}
    Playbook.model_validate(payload)
    write_yaml_atomic(path, payload)
    return new_rule


def append_rule(
    root: Path,
    *,
    source: PlaybookSource,
    station: str,
    signature: str,
    action: PlaybookAction,
    direction: str,
    delegate_role: DelegateRole | None = None,
    max_auto_per_incident: int = 1,
    question_id: str | None = None,
    slug: str | None = None,
    created: str | None = None,
) -> PlaybookRule:
    """Append a new rule without modifying or deleting any existing entry."""
    pb = load_playbook(root)
    rule = PlaybookRule(
        id=next_rule_id(pb.rules),
        created=created or datetime.now().astimezone().date().isoformat(),
        source=source,
        question_id=question_id,
        slug=slug,
        match=PlaybookMatch(station=station.strip() or 'repair', signature=signature.strip()),
        action=action,
        delegate_role=delegate_role,
        direction=direction.strip(),
        max_auto_per_incident=max_auto_per_incident,
    )
    return _append_raw_entry(root, rule)


def disable_rule(
    root: Path,
    target_id: str,
    *,
    source: PlaybookSource = 'doctor',
    created: str | None = None,
) -> PlaybookRule:
    """Append a disable tombstone for ``target_id`` without modifying old entries."""
    pb = load_playbook(root)
    rule = PlaybookRule(
        id=next_rule_id(pb.rules),
        created=created or datetime.now().astimezone().date().isoformat(),
        source=source,
        disables=target_id,
    )
    return _append_raw_entry(root, rule)


def match_rule(root: Path, *, station: str, signature: str) -> PlaybookRule | None:
    """Return the latest active rule matching ``station`` and ``signature``, if any."""
    pb = load_playbook(root)
    station_clean = station.strip()
    sig_clean = signature.strip()
    if not station_clean or not sig_clean:
        return None
    matched = [
        rule for rule in active_rules(pb)
        if rule.match is not None
        and rule.match.station == station_clean
        and rule.match.signature == sig_clean
    ]
    return matched[-1] if matched else None


def normalize_incident_reason(detail: str) -> str:
    collapsed = ' '.join(
        ' '.join(
            line for line in detail.splitlines()
            if not line.lstrip().startswith('log_path:')
        ).split()
    )
    text = collapsed
    while text:
        updated = text
        for pattern in _INCIDENT_PREFIX_PATTERNS:
            updated = pattern.sub('', updated, count=1).lstrip()
        if updated == text:
            break
        text = updated
    return text or collapsed


def is_transient_network_error(detail: str) -> bool:
    """Return True when ``detail`` describes a transient network/upstream error."""
    if not detail:
        return False
    return bool(_TRANSIENT_NETWORK_RE.search(detail))


def incident_signature(station: str, detail: str, *, error_kind: str = '') -> str:
    """Compute a pure, stable signature independent of project paths, timestamps, hashes, or counts."""
    st = (station or 'repair').strip().lower() or 'repair'
    raw = str(detail or '')
    lower = raw.lower()

    # Canonical families matching known production incidents (must stay stable across projects).
    if 'chưa có evidence/expert-brief.md' in lower or 'oa retrieval failed' in lower:
        return f'{st}:research_missing_fulltext'

    if (
        'review budget exhausted: script' in lower
        or 'trạm 07 chưa đạt sau' in lower
        or 'trạm 07 cần hướng dẫn:' in lower
    ):
        return f'{st}:station07_review_budget_style'

    if (
        'review budget exhausted: product' in lower
        or 'review budget exhausted: visual' in lower
        or 'trạm 12 cần hướng dẫn:' in lower
        or 'trạm 12 chưa đạt' in lower
        or 'storyboard cần hướng dẫn:' in lower
    ):
        return f'{st}:station12_presentation_budget'

    detected_kind = error_kind.strip()
    if not detected_kind:
        kind_match = _ERROR_KIND_RE.search(raw)
        detected_kind = kind_match.group(1) if kind_match else 'incident'
    detected_kind = detected_kind.lower()

    normalized = normalize_incident_reason(raw)
    cleaned = _WINDOWS_PATH_RE.sub('<path>', normalized)
    cleaned = _POSIX_PATH_RE.sub('<path>', cleaned)
    cleaned = _REL_PATH_RE.sub('<path>', cleaned)
    cleaned = _ISO_TS_RE.sub('<ts>', cleaned)
    cleaned = _HEX_HASH_RE.sub('<id>', cleaned)
    cleaned = _COUNTS_RE.sub('<n>', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().lower()
    cleaned = re.sub(r'(?:<path>\s*){2,}', '<path> ', cleaned).strip()
    cleaned = cleaned[:140].rstrip(' .,:;')
    return f'{st}:{detected_kind}:{cleaned or "unknown"}'


def review_budget_stage_from_detail(detail: str) -> str | None:
    """Extract the editorial review_budget stage name when ``detail`` reports a budget exhaustion."""
    match = re.search(r'Review budget exhausted:\s*([a-z0-9:_-]+)', detail or '', re.IGNORECASE)
    if match:
        stage = match.group(1).strip()
        return stage if stage in {'script', 'visual', 'product'} else None
    lower = (detail or '').lower()
    if 'trạm 07 chưa đạt sau' in lower or 'trạm 07 cần hướng dẫn:' in lower:
        return 'script'
    if 'trạm 12 cần hướng dẫn:' in lower or 'trạm 12 chưa đạt' in lower:
        return 'product'
    if 'storyboard cần hướng dẫn:' in lower:
        return 'visual'
    return None


def _has_blocking_safety_in_reviews(artifact_root: Path | None) -> bool:
    if artifact_root is None or not artifact_root.is_dir():
        return False
    for rel in ('reviews/script-review-log.yaml', 'reviews/product-review-log.yaml'):
        path = artifact_root / rel
        if not path.is_file():
            continue
        try:
            data = read_yaml(path)
        except (OSError, TypeError, ValueError, yaml.YAMLError):
            continue
        rounds = data.get('rounds') if isinstance(data, Mapping) else None
        if isinstance(rounds, list) and rounds:
            latest = rounds[-1]
            issues = latest.get('issues') if isinstance(latest, Mapping) else None
            if isinstance(issues, list) and any(
                isinstance(item, Mapping) and bool(item.get('blocking_safety', False))
                for item in issues
            ):
                return True
    budget_path = artifact_root / 'reviews/review-budget.yaml'
    if budget_path.is_file():
        try:
            budget = read_yaml(budget_path)
        except (OSError, TypeError, ValueError, yaml.YAMLError):
            budget = None
        stages = budget.get('stages') if isinstance(budget, Mapping) else None
        if isinstance(stages, Mapping):
            for events in stages.values():
                if not isinstance(events, list) or not events:
                    continue
                latest_ev = events[-1]
                ev_data = latest_ev.get('evidence') if isinstance(latest_ev, Mapping) else None
                issues = ev_data.get('issues') if isinstance(ev_data, Mapping) else None
                if isinstance(issues, list) and any(
                    isinstance(item, Mapping) and bool(item.get('blocking_safety', False))
                    for item in issues
                ):
                    return True
    return False


def is_auto_forbidden(
    *,
    kind: str = 'escalation',
    detail: str = '',
    reason: str = '',
    record: Mapping[str, Any] | None = None,
    artifact_root: Path | None = None,
    state: str | None = None,
) -> bool:
    """Hard code guard: never auto-handle non-escalations, PIN/gate/account needs, or blocking_safety."""
    if kind != 'escalation':
        return True
    if state in {
        'awaiting_medical_review',
        'awaiting_video_review',
        'video_approved',
        'packaged',
        'published_manual',
    }:
        return True
    if isinstance(record, Mapping):
        diag = record.get('diagnosis')
        if isinstance(diag, Mapping) and str(diag.get('requires_doctor') or '').strip().lower() in _REQUIRES_DOCTOR_VALUES:
            return True
        delegation = record.get('delegation')
        if isinstance(delegation, Mapping):
            if delegation.get('requires_doctor_reopen'):
                return True
            if str(delegation.get('status') or '') == 'awaiting_doctor_reopen':
                return True
    combined = '\n'.join(part for part in (detail, reason) if part)
    if _FORBIDDEN_TEXT_RE.search(combined):
        return True
    return _has_blocking_safety_in_reviews(artifact_root)
