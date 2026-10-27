"""Doctor feedback memory: every review comment becomes a standing standard for agents.

Entries live in ``profiles/doctor-feedback.yaml`` (versioned in Git, no secrets) and are
rendered into every agent prompt so later topics follow the same corrections.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from healthvideo.storage.files import read_yaml, write_yaml_atomic

FEEDBACK_FILE = Path('profiles') / 'doctor-feedback.yaml'
KINDS = frozenset({'reject', 'reopen', 'approve_note', 'comment'})
PROMPT_CHAR_BUDGET = 14_000
KIND_LABELS = {
    'reject': 'Từ chối, yêu cầu sửa',
    'reopen': 'Mở lại cổng',
    'approve_note': 'Ghi chú khi duyệt',
    'comment': 'Góp ý',
}


def feedback_path(root: Path) -> Path:
    return root / FEEDBACK_FILE


def load(root: Path) -> list[dict]:
    path = feedback_path(root)
    if not path.is_file():
        return []
    entries = read_yaml(path).get('entries', [])
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []


def record(root: Path, *, slug: str, gate: str, revision: str, kind: str, text: str = '',
           items: list[dict] | None = None, reviewer: str = '', at: datetime | None = None) -> dict | None:
    """Append one feedback entry; returns None when there is nothing to remember."""
    if kind not in KINDS:
        raise ValueError(f'Loại góp ý không hợp lệ: {kind}')
    clean_items = [
        {'target': str(item.get('target', '')).strip()[:40], 'text': str(item.get('text', '')).strip()}
        for item in items or [] if str(item.get('text', '')).strip()
    ]
    text = text.strip()
    if not text and not clean_items:
        return None
    entry = {
        'at': (at or datetime.now().astimezone()).isoformat(timespec='seconds'),
        'slug': slug, 'gate': gate, 'revision': revision, 'kind': kind,
        'reviewer': reviewer, 'text': text, 'items': clean_items,
    }
    entries = load(root)
    entries.append(entry)
    write_yaml_atomic(feedback_path(root), {'version': 1, 'entries': entries})
    return entry


def compose_reason(general: str, items: list[dict]) -> str:
    """Join a general note and per-item comments into one rejection reason."""
    parts = [general.strip()] if general.strip() else []
    parts.extend(f"- {item['target']}: {item['text']}" if item.get('target') else f"- {item['text']}"
                 for item in items if str(item.get('text', '')).strip())
    return '\n'.join(parts)


def remember(project_dir: Path, *, gate: str, revision: str, kind: str, text: str,
             reviewer: str, at: datetime | None = None) -> None:
    """Record a gate decision's text for the project's factory root; never raises on I/O."""
    import logging

    try:
        root = project_dir.resolve().parents[1]
        record(root, slug=project_dir.name, gate=gate, revision=revision, kind=kind,
               text=text, reviewer=reviewer, at=at)
    except (OSError, ValueError, IndexError):
        logging.getLogger(__name__).warning('Không ghi được góp ý của bác sĩ vào %s', FEEDBACK_FILE)


def _entry_markdown(entry: dict) -> str:
    head = f"- [{entry.get('at', '')[:10]} · {entry.get('slug', '')} · cổng {entry.get('gate', '')} · " \
           f"{KIND_LABELS.get(entry.get('kind', ''), entry.get('kind', ''))}]"
    lines = [head]
    if entry.get('text'):
        lines.extend(f'  {row}' for row in str(entry['text']).splitlines() if row.strip())
    for item in entry.get('items', []):
        target = f"{item['target']}: " if item.get('target') else ''
        lines.append(f"  - {target}{item['text']}")
    return '\n'.join(lines)


def prompt_block(root: Path, *, slug: str | None = None) -> str:
    """Markdown block of standing standards, newest first, within a character budget."""
    from healthvideo.workflows.factory_standards import accepted_standards

    entries = [entry for entry in load(root) if entry.get('slug') == 'chung'
               or (slug is not None and entry.get('slug') == slug)]
    accepted = accepted_standards(root)
    if slug is not None:
        projects = (root / 'projects').resolve()
        project = (projects / slug).resolve()
        if project.parent != projects:
            raise ValueError('Project slug ngoài thư mục projects.')
        manifest = project / 'project.yaml'
        if manifest.is_file():
            revision = str(read_yaml(manifest)['active_revision'])
            snapshot = (project / 'revisions' / revision / 'workflow/standards.yaml').resolve()
            if not snapshot.is_relative_to(project):
                raise ValueError('Standards snapshot ngoài project.')
            if snapshot.is_file():
                accepted = {entry['stage']: entry for entry in read_yaml(snapshot)['standards']}
    if not entries and not accepted:
        return ''
    header = (
        '## Chuẩn của bác sĩ\n'
        'Chuẩn đã nghiệm thu áp dụng toàn kênh. Góp ý chỉ áp dụng đúng chủ đề; '
        'ghi chú chung áp dụng toàn kênh. Không suy rộng góp ý của chủ đề khác.\n'
    )
    body: list[str] = []
    used = len(header)
    for stage, entry in sorted(accepted.items()):
        chunk = f"- Giai đoạn {stage} · v{entry['version']}: {entry['text']}"
        body.append(chunk)
        used += len(chunk) + 1
    for entry in reversed(entries):
        chunk = _entry_markdown(entry)
        if used + len(chunk) > PROMPT_CHAR_BUDGET:
            body.append(f'- … còn {len(entries) - len(body)} góp ý cũ hơn trong `{FEEDBACK_FILE.as_posix()}`.')
            break
        body.append(chunk)
        used += len(chunk) + 1
    return header + '\n'.join(body) + '\n'
