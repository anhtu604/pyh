"""Doctor question gate outside medical/video approvals; never touches PINs or approvals."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from healthvideo.storage.files import read_yaml, write_yaml_atomic

QUESTION_FILE = 'doctor-question.yaml'
HISTORY_FILE = 'doctor-questions-history.yaml'
MAX_SUMMARY_CHARS = 200
MAX_FREE_TEXT_CHARS = 4000
_SLUG_RE = re.compile(r'^[a-z0-9-]+$')


def inside(base: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError('Đường dẫn nằm ngoài thư mục cho phép.')
    return resolved


def _validate_slug(slug: str) -> str:
    if (
        not isinstance(slug, str)
        or not slug
        or len(slug) > 80
        or '/' in slug
        or '\\' in slug
        or '..' in slug
        or not _SLUG_RE.fullmatch(slug)
    ):
        raise ValueError(f'Slug không hợp lệ: {slug!r}')
    return slug


def question_path(root: Path, slug: str) -> Path:
    _validate_slug(slug)
    logs_base = root / 'topics' / 'logs'
    log_dir = inside(logs_base, logs_base / slug)
    return inside(log_dir, log_dir / QUESTION_FILE)


def history_path(root: Path, slug: str) -> Path:
    _validate_slug(slug)
    logs_base = root / 'topics' / 'logs'
    log_dir = inside(logs_base, logs_base / slug)
    return inside(log_dir, log_dir / HISTORY_FILE)


def history(root: Path, slug: str) -> list[dict[str, Any]]:
    path = history_path(root, slug)
    if not path.is_file():
        return []
    try:
        data = read_yaml(path)
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return []
    entries = data.get('entries')
    return [dict(item) for item in entries if isinstance(item, Mapping)] if isinstance(entries, list) else []


def open_question(root: Path, slug: str) -> dict[str, Any] | None:
    """Return the active open question for ``slug``, or None if none is open."""
    path = question_path(root, slug)
    if not path.is_file():
        return None
    try:
        data = read_yaml(path)
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return None
    if data.get('status') != 'open':
        return None
    return data


def _normalize_context(items: Sequence[Mapping[str, Any]] | None) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in items or ():
        if not isinstance(item, Mapping):
            continue
        code = str(item.get('code') or item.get('id') or '').strip()[:40]
        location = str(item.get('location') or item.get('at') or '').strip()[:80]
        summary = ' '.join(str(item.get('summary') or item.get('description') or '').split()).strip()
        if len(summary) > MAX_SUMMARY_CHARS:
            summary = summary[: MAX_SUMMARY_CHARS - 1].rstrip() + '…'
        normalized.append({'code': code, 'location': location, 'summary': summary})
    return normalized


def _normalize_options(options: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    if not isinstance(options, Sequence) or isinstance(options, (str, bytes)) or not 2 <= len(options) <= 4:
        raise ValueError('Câu hỏi bác sĩ cần từ 2 đến 4 phương án.')
    normalized: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for item in options:
        if not isinstance(item, Mapping):
            raise TypeError('Mỗi phương án phải là đối tượng hợp lệ.')
        opt_id = str(item.get('id') or '').strip()
        label = str(item.get('label') or '').strip()
        detail = str(item.get('detail') or '').strip()
        if not opt_id or not label:
            raise ValueError('Mỗi phương án cần có id và label không rỗng.')
        if opt_id in seen_ids:
            raise ValueError(f'Trùng mã phương án: {opt_id}')
        seen_ids.add(opt_id)
        normalized.append({'id': opt_id, 'label': label, 'detail': detail})
    return normalized


def _parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _context_signature(items: Sequence[Mapping[str, Any]] | None) -> list[tuple[str, str]]:
    normalized = _normalize_context(items)
    return sorted((item['code'], item['location']) for item in normalized)


def answered_for_fingerprint(root: Path, slug: str, fingerprint: str) -> dict[str, Any] | None:
    """Return the latest answered history entry matching ``fingerprint``, if any."""
    fp = str(fingerprint or '').strip()
    if not fp:
        return None
    for entry in reversed(history(root, slug)):
        if entry.get('status') == 'answered' and str(entry.get('fingerprint') or '').strip() == fp:
            return entry
    return None


def has_matching_answered_history(
    root: Path,
    slug: str,
    question: Mapping[str, Any],
    *,
    min_answered_at: datetime | None = None,
) -> dict[str, Any] | None:
    """Match an answered history entry by fingerprint or same station+kind+context."""
    fp = str(question.get('fingerprint') or '').strip()
    if fp:
        matched = answered_for_fingerprint(root, slug, fp)
        if matched is not None:
            return matched

    station = str(question.get('station') or '').strip()
    kind = str(question.get('kind') or '').strip()
    target_sig = _context_signature(question.get('context') if isinstance(question.get('context'), Sequence) else None)
    if not station or not kind or not target_sig:
        return None

    min_utc = min_answered_at.astimezone(UTC) if min_answered_at is not None else None
    for entry in reversed(history(root, slug)):
        if entry.get('status') != 'answered':
            continue
        if str(entry.get('station') or '').strip() != station or str(entry.get('kind') or '').strip() != kind:
            continue
        ans = entry.get('answer')
        ans_at = _parse_iso_datetime(ans.get('at')) if isinstance(ans, Mapping) else None
        if min_utc is not None and (ans_at is None or ans_at < min_utc):
            continue
        entry_ctx = entry.get('context') if isinstance(entry.get('context'), Sequence) else None
        if _context_signature(entry_ctx) == target_sig:
            return entry
    return None


def supersede(
    root: Path,
    slug: str,
    *,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Archive an obsolete open question as superseded and clear ``doctor-question.yaml``."""
    path = question_path(root, slug)
    if not path.is_file():
        return None
    try:
        data = read_yaml(path)
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return None
    if not isinstance(data, Mapping) or data.get('status') != 'open':
        return None
    superseded_at = (now or datetime.now(UTC)).isoformat(timespec='seconds')
    archived: dict[str, Any] = {
        **dict(data),
        'status': 'superseded',
        'superseded_reason': str(reason or '').strip(),
        'superseded_at': superseded_at,
    }
    hist_entries = history(root, slug)
    hist_entries.append(archived)
    write_yaml_atomic(history_path(root, slug), {'version': 1, 'entries': hist_entries})
    path.unlink(missing_ok=True)
    return archived


def supersede_kind(
    root: Path,
    slug: str,
    kind: str,
    *,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Supersede an active open question only when its ``kind`` matches ``kind``."""
    existing = open_question(root, slug)
    if existing is None or str(existing.get('kind') or '').strip() != str(kind or '').strip():
        return None
    return supersede(root, slug, reason=reason, now=now)


def ask(
    root: Path,
    slug: str,
    *,
    station: str,
    kind: str,
    question: str,
    context: Sequence[Mapping[str, Any]] | None = None,
    options: Sequence[Mapping[str, Any]],
    allow_free_text: bool = True,
    fingerprint: str | None = None,
    now: datetime | None = None,
    pronunciation_terms: Sequence[Mapping[str, Any]] | None = None,
    tts_lines: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create an open question atomically; deduplicate open or answered questions."""
    path = question_path(root, slug)
    station_clean = str(station or '').strip()
    kind_clean = str(kind or '').strip()
    question_clean = str(question or '').strip()
    if not station_clean:
        raise ValueError('Thiếu mã trạm cho câu hỏi bác sĩ.')
    if not kind_clean:
        raise ValueError('Thiếu loại câu hỏi bác sĩ.')
    if not question_clean:
        raise ValueError('Thiếu nội dung câu hỏi bác sĩ.')

    normalized_options = _normalize_options(options)
    normalized_context = _normalize_context(context)
    fp_clean = str(fingerprint or '').strip()

    existing = open_question(root, slug)
    if (
        existing is not None
        and str(existing.get('kind') or '') == kind_clean
        and str(existing.get('station') or '') == station_clean
    ):
        return existing

    if fp_clean:
        prior = answered_for_fingerprint(root, slug, fp_clean)
        if prior is not None:
            return prior

    payload: dict[str, Any] = {
        'id': f'dq-{uuid4().hex[:12]}',
        'station': station_clean,
        'kind': kind_clean,
        'question': question_clean,
        'context': normalized_context,
        'options': normalized_options,
        'allow_free_text': bool(allow_free_text),
        **({'fingerprint': fp_clean} if fp_clean else {}),
        'created_at': (now or datetime.now(UTC)).isoformat(timespec='seconds'),
        'status': 'open',
        'answer': None,
        **({'pronunciation_terms': list(pronunciation_terms)} if pronunciation_terms is not None else {}),
        **({'tts_lines': list(tts_lines)} if tts_lines is not None else {}),
    }
    from healthvideo.workflows.external_revision import external_revision_id

    revision = external_revision_id(root / 'projects' / slug)
    if revision is not None:
        payload['revision'] = revision
    write_yaml_atomic(path, payload)
    return payload


def answer(
    root: Path,
    slug: str,
    question_id: str,
    option_id: str | None = None,
    text: str = '',
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record the doctor's answer, append it to history, and clear the waiting marker."""
    path = question_path(root, slug)
    qid = str(question_id or '').strip()
    if not qid:
        raise ValueError('Thiếu mã câu hỏi (question_id).')

    if not path.is_file():
        if any(str(item.get('id') or '') == qid for item in history(root, slug)):
            raise ValueError('Câu hỏi này đã được trả lời.')
        raise LookupError('Không có câu hỏi nào đang chờ bác sĩ.')

    data = read_yaml(path)
    if data.get('status') != 'open':
        raise ValueError('Câu hỏi này đã được trả lời.')
    if str(data.get('id') or '') != qid:
        raise ValueError('Mã câu hỏi không khớp; vui lòng tải lại trang.')

    opt_id = str(option_id).strip() if option_id is not None else ''
    clean_text = str(text or '').strip()[:MAX_FREE_TEXT_CHARS]
    options = data.get('options') or []
    matched = next((o for o in options if isinstance(o, Mapping) and o.get('id') == opt_id), None) if opt_id else None
    if opt_id and matched is None:
        raise ValueError(f'Phương án không hợp lệ: {opt_id}')
    if not opt_id:
        if not data.get('allow_free_text'):
            raise ValueError('Câu hỏi này yêu cầu chọn một phương án.')
        if not clean_text:
            raise ValueError('Chọn một phương án hoặc nhập ý kiến trả lời.')
    elif clean_text and not data.get('allow_free_text'):
        raise ValueError('Câu hỏi này không cho phép nhập chữ tự do.')

    answered_at = (now or datetime.now(UTC)).isoformat(timespec='seconds')
    if data.get('kind') == 'tts_qa':
        if opt_id not in {'accept', 'change', 'retry'}:
            raise ValueError('Chọn dùng tiếp, đổi cách đọc hoặc đọc lại.')
        if opt_id == 'change':
            from healthvideo.tts import pronunciation as pronunciation_module

            try:
                choices = json.loads(clean_text)
            except (ValueError, TypeError):
                raise ValueError('Nhập cách đọc dạng JSON: {"từ": "cách đọc"}. Cần duyệt lại y khoa.') from None
            if (len(str(text or '')) > MAX_FREE_TEXT_CHARS or not isinstance(choices, dict) or not choices
                    or any(not isinstance(k, str) or not k.strip() or len(k) > 200
                           or not isinstance(v, str) or not v.strip() or len(v) > 200
                           or any(ord(c) < 32 for c in k + v) for k, v in choices.items())):
                raise ValueError('Cách đọc không hợp lệ; cần nhập từ và cách đọc đầy đủ.')
            # The profile is a medical-reviewed artifact. Updating it deliberately
            # invalidates the medical approval; produce checks it before any TTS.
            pronunciation_module.save_doctor_pronunciations(
                pronunciation_module.PRONUNCIATION_PROFILE_PATH, choices, answered_at[:10])
    if data.get('kind') == 'pronunciation':
        from healthvideo.tts.pronunciation import save_doctor_pronunciations

        terms = data.get('pronunciation_terms') or []
        if opt_id and not clean_text:
            index = {'spelling': 0, 'joined': 1}.get(opt_id)
            if index is None:
                raise ValueError('Phương án cách đọc không hợp lệ.')
            choices = {term['written']: term['options'][index] for term in terms}
        else:
            try:
                choices = json.loads(clean_text)
            except (ValueError, TypeError):
                raise ValueError('Câu trả lời cách đọc không đúng định dạng; vui lòng chọn hoặc nhập từng từ.') from None
        if (
            len(str(text or '')) > MAX_FREE_TEXT_CHARS
            or not isinstance(choices, dict)
            or set(choices) != {term['written'] for term in terms}
            or not choices
            or any(not isinstance(value, str) or not value.strip() or len(value) > 200
                   or any(ord(ch) < 32 for ch in value) for value in choices.values())
        ):
            raise ValueError('Cần nhập đầy đủ cách đọc hợp lệ cho từng từ (tối đa 200 ký tự mỗi từ).')
        save_doctor_pronunciations(root / 'profiles/pronunciation.vi.yaml', choices, answered_at[:10])
    answered: dict[str, Any] = {
        **data,
        'status': 'answered',
        'answer': {
            'option_id': opt_id or None,
            'option_label': str(matched.get('label') or '') if matched else '',
            'text': clean_text,
            'at': answered_at,
        },
    }
    write_yaml_atomic(path, answered)

    hist_entries = history(root, slug)
    hist_entries.append(answered)
    write_yaml_atomic(history_path(root, slug), {'version': 1, 'entries': hist_entries})
    path.unlink(missing_ok=True)
    if data.get('kind') == 'tts_qa' and opt_id in {'accept', 'retry'}:
        from healthvideo.workflows.production_retry import clear_retry

        # The runner records a validation hold after produce raises. The doctor's
        # explicit listening/retry decision releases only this TTS hold, so the
        # normal scheduler can resume without a separate technical retry button.
        marker = 'Whisper TTS QA blocked before render'
        hold = path.parent / 'production-retry.yaml'
        if hold.is_file() and marker in str(read_yaml(hold).get('reason', '')):
            clear_retry(root, slug)
        blocked = path.parent / 'blocked.txt'
        if blocked.is_file() and marker in blocked.read_text(encoding='utf-8'):
            blocked.unlink(missing_ok=True)
    return answered
