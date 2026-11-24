"""Shared incremental-review protocol; no gate, score threshold or timing changes."""

from copy import deepcopy
from difflib import SequenceMatcher, unified_diff
from hashlib import sha256

import yaml
from pydantic import BaseModel, ConfigDict, Field

from healthvideo.storage.files import validate_agent_text


def normalize_issue_statuses(value: object) -> object:
    """Accept an unambiguous agent row list; leave legacy mappings to Pydantic."""
    if not isinstance(value, list):
        return value
    statuses: dict[str, str] = {}
    for item in value:
        if (not isinstance(item, dict) or 'status' not in item
                or not ({'issue_id', 'id'} & item.keys())
                or item.keys() - {'issue_id', 'id', 'status'}):
            raise ValueError('issue_statuses rows require issue_id (or id) and status only')
        if 'issue_id' in item and 'id' in item and item['issue_id'] != item['id']:
            raise ValueError('issue_statuses row has conflicting issue_id and id')
        issue_id = item['issue_id'] if 'issue_id' in item else item['id']
        status = item['status']
        if not isinstance(issue_id, str) or not issue_id.strip():
            raise ValueError('issue_statuses issue_id must be a nonempty string')
        if not isinstance(status, str) or status not in {'resolved', 'still_open'}:
            raise ValueError('issue_statuses status must be resolved or still_open')
        if issue_id in statuses and statuses[issue_id] != status:
            raise ValueError(f'issue_statuses has conflicting statuses for {issue_id}')
        statuses[issue_id] = status
    return statuses


class EditScope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


def check_edits(before: dict[str, bytes], after: dict[str, bytes], scopes: list[dict]) -> None:
    """Only explicit original line ranges may change; creation/deletion is forbidden."""
    if before.keys() != after.keys():
        raise ValueError('Repair scope violation: file creation/deletion')
    for path, raw in before.items():
        if raw == after[path]:
            continue
        allowed = [s for s in scopes if s['path'] == path]
        old, new = raw.splitlines(keepends=True), after[path].splitlines(keepends=True)
        for tag, start, end, _, _ in SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag == 'equal':
                continue
            if not any(s['start_line'] - 1 <= start and end <= s['end_line']
                       and start < s['end_line'] for s in allowed):
                raise ValueError(f'Repair scope violation: {path}:{start + 1}-{end}')


def identify(item: dict, location: str) -> dict:
    item = dict(item)
    item['issue_id'] = item.get('issue_id') or 'I-' + sha256(
        f"{item[location]}:{item['criterion']}".encode()).hexdigest()[:16]
    return item


def reconcile(previous: dict | None, report: dict, location: str) -> dict:
    """Freeze accepted work and trace unsolicited issues without failing the review."""
    report = deepcopy(report)
    report['issues'] = [identify(item, location) for item in report.get('issues', [])]
    ids = [item['issue_id'] for item in report['issues']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate issue_id')
    if not previous:
        report['issue_statuses'] = dict.fromkeys(ids, 'still_open')
        return report
    old = [identify(item, location) for item in previous.get('issues', [])]
    by_id = {item['issue_id']: item for item in old}
    active = {item['criterion'] for item in old}
    kept = []
    for item in report['issues']:
        prior = by_id.get(item['issue_id'])
        safety = bool(item.get('blocking_safety') or (prior or {}).get('blocking_safety'))
        if prior is None and not item.get('blocking_safety'):
            report.setdefault('dropped_issues', []).append({
                'issue': item, 'reason': 'New issue outside previously open issues'})
            continue
        if prior is not None and (
            (item[location], item['criterion']) != (prior[location], prior['criterion'])
            or any(item.get(key, []) != prior.get(key, []) for key in ('related_lines', 'edits'))
        ):
            report.setdefault('dropped_issues', []).append({
                'issue': item, 'reason': 'Changed location, criterion or repair scope; kept previous issue'})
            item = deepcopy(prior)
        if safety:
            item['blocking_safety'] = True
        if item.get('blocking_safety'):
            active.add(item['criterion'])
        kept.append(item)
    report['issues'] = kept
    ids = [item['issue_id'] for item in kept]
    for criterion, score in previous['scores'].items():
        if criterion not in active:
            report['scores'][criterion] = score
    affected = {str(item[location]).split('@')[0] for item in old}
    affected.update(line for item in old for line in item.get('related_lines', []))
    for decision in previous.get('decisions', []):
        if str(decision['where']).split('@')[0] in affected:
            continue
        report['decisions'] = [item for item in report.get('decisions', [])
                               if item['id'] != decision['id']]
        report['decisions'].append(deepcopy(decision))
    statuses = dict(previous.get('issue_statuses', {}))
    statuses.update({item['issue_id']: ('still_open' if item['issue_id'] in ids else 'resolved')
                     for item in old})
    statuses.update(dict.fromkeys(ids, 'still_open'))
    report['issue_statuses'] = statuses
    return report


def stuck(rounds: list[dict]) -> set[str]:
    """Two consecutive reviews with the same open issue stop the automatic loop."""
    if len(rounds) < 2:
        return set()
    return ({key for key, value in rounds[-1].get('issue_statuses', {}).items()
             if value == 'still_open'} &
            {key for key, value in rounds[-2].get('issue_statuses', {}).items()
             if value == 'still_open'})


def packet(issues: list[dict], before: dict[str, str], after: dict[str, str],
           *, context: int = 2) -> str:
    diffs = []
    for path in sorted(before.keys() | after.keys()):
        diffs.extend(unified_diff(before.get(path, '').splitlines(keepends=True),
                                  after.get(path, '').splitlines(keepends=True),
                                  fromfile=path + ':before', tofile=path + ':after', n=context))
    return ('Open issues:\n' + yaml.safe_dump(issues, allow_unicode=True, sort_keys=False)
            + '\nDiff (context is read-only):\n' + ''.join(diffs))


def check_nodes(before: bytes, after: bytes, allowed: set[str], collection: str) -> None:
    """Compare exact YAML source outside explicitly editable line nodes, not reserialized text."""
    def masked(raw):
        text = raw.decode('utf-8')
        doc = yaml.compose(text)
        fields = {key.value: value for key, value in doc.value}
        lines = fields[collection].value
        ids, spans = [], []
        for node in lines:
            values = {key.value: value.value for key, value in node.value}
            identity = values.get('id') or values['path']
            ids.append(identity)
            if identity in allowed:
                spans.append((node.start_mark.index, node.end_mark.index, identity))
        for start, end, identity in reversed(spans):
            text = text[:start] + '<editable:' + identity + '>' + text[end:]
        return ids, text
    try:
        changed = masked(before) != masked(after)
    except (yaml.YAMLError, UnicodeError, AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError('Repair scope violation: malformed document') from exc
    if changed:
        raise ValueError('Repair scope violation: unchanged script lines/metadata must remain exact')
    if before != after:
        validate_agent_text(yaml.safe_load(after), 'repair')


def check_script(before: bytes, after: bytes, allowed: set[str]) -> None:
    check_nodes(before, after, allowed, 'lines')
