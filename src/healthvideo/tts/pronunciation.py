"""Literal, word-boundary-aware pronunciation resolution."""

import re
from collections.abc import Mapping
from pathlib import Path

import yaml

from healthvideo.domain.pronunciation import PronunciationLexicon
from healthvideo.storage.files import canonical_json_hash, read_yaml, write_text_atomic
from healthvideo.storage.revision_lock import revision_lock

PRONUNCIATION_PROFILE_PATH = (
    Path(__file__).resolve().parents[3] / "profiles" / "pronunciation.vi.yaml"
)


def load_pronunciation_lexicon(path: Path) -> PronunciationLexicon:
    return PronunciationLexicon.model_validate(read_yaml(path))


def pronunciation_hash(lexicon: PronunciationLexicon) -> str:
    return canonical_json_hash(lexicon.model_dump(mode="json"))


def apply_pronunciation(text: str, lexicon: PronunciationLexicon) -> str:
    if not lexicon.entries:
        return text
    choices = sorted(lexicon.entries, key=lambda entry: -len(entry.written))
    pattern = re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(e.written) for e in choices) + r")(?!\w)",
        flags=re.IGNORECASE | re.UNICODE,
    )
    mapping = {entry.written.casefold(): entry.spoken for entry in choices}
    return pattern.sub(lambda match: mapping[match.group().casefold()], text)


def used_pronunciation_hash(lexicon_path: Path, script_path: Path) -> str:
    """Hash only the entries the script can speak, so choices for other projects keep this approval valid.

    Matches the raw script file (a superset of the TTS text), with apply_pronunciation's word boundaries.
    """
    text = script_path.read_text(encoding="utf-8")
    used = sorted({
        (entry.written.casefold(), entry.spoken)
        for entry in load_pronunciation_lexicon(lexicon_path).entries
        if re.search(r"(?<!\w)" + re.escape(entry.written) + r"(?!\w)", text, flags=re.IGNORECASE | re.UNICODE)
    })
    return canonical_json_hash([list(pair) for pair in used])


def save_doctor_pronunciations(path: Path, choices: Mapping[str, str], date: str) -> None:
    """Patch YAML nodes, preserving existing order, comments and unrelated formatting."""
    with revision_lock(path):
        original = path.read_bytes().decode('utf-8-sig')
        data = yaml.safe_load(original)
        PronunciationLexicon.model_validate(data)
        document = yaml.compose(original)
        sequence = next(value for key, value in document.value if key.value == 'entries')
        edits: list[tuple[int, int, str]] = []
        remaining = {term.casefold(): (term, spoken) for term, spoken in choices.items()}

        def scalar(value: object, style: str | None = None) -> str:
            return yaml.safe_dump(value, allow_unicode=True, default_style=style,
                                  default_flow_style=True, width=10000).removesuffix('...\n').rstrip('\n')

        newline = '\r\n' if '\r\n' in original else '\n'
        for node, entry in zip(sequence.value, data['entries'], strict=True):
            chosen = remaining.pop(entry['written'].casefold(), None)
            if chosen is None:
                continue
            fields = {'spoken': chosen[1], 'needs_doctor_review': False, 'note': f'Bác sĩ chọn {date}'}
            nodes = {key.value: value for key, value in node.value}
            for key, value in fields.items():
                entry[key] = value
                if key in nodes:
                    value_node = nodes[key]
                    edits.append((value_node.start_mark.index, value_node.end_mark.index,
                                  scalar(value, value_node.style if isinstance(value, str) else None)))
            missing = {key: value for key, value in fields.items() if key not in nodes}
            if missing:
                if node.flow_style:
                    # Preserve flow mappings too, inserting before their closing brace.
                    at = node.end_mark.index - 1
                    extra = ', '.join(f'{key}: {scalar(value)}' for key, value in missing.items())
                    edits.append((at, at, ', ' + extra))
                else:
                    last = node.value[-1][1].end_mark.index
                    at = original.find('\n', last)
                    at = len(original) if at < 0 else at + 1
                    indent = ' ' * node.start_mark.column
                    extra = ''.join(f'{indent}{key}: {scalar(value)}{newline}' for key, value in missing.items())
                    edits.append((at, at, (newline if at == len(original) and not original.endswith('\n') else '') + extra))
        additions = [
            {'written': term, 'spoken': spoken, 'needs_doctor_review': False, 'note': f'Bác sĩ chọn {date}'}
            for term, spoken in remaining.values()
        ]
        if additions:
            data['entries'].extend(additions)
            if sequence.flow_style:
                at = sequence.end_mark.index - 1
                extra = ', '.join(yaml.safe_dump(e, allow_unicode=True, default_flow_style=True,
                                               width=10000).strip() for e in additions)
                edits.append((at, at, (', ' if sequence.value else '') + extra))
            else:
                last = sequence.value[-1].value[-1][1].end_mark.index
                at = original.find('\n', last)
                at = len(original) if at < 0 else at + 1
                dumped = yaml.safe_dump(additions, allow_unicode=True, sort_keys=False, width=10000)
                indent = ' ' * sequence.start_mark.column
                extra = ''.join(indent + line + newline for line in dumped.splitlines())
                edits.append((at, at, (newline if at == len(original) and not original.endswith('\n') else '') + extra))
        # Stable reverse order also handles two insertions at the same boundary.
        result = original
        ordered = sorted(enumerate(edits), key=lambda item: (item[1][0], item[0]), reverse=True)
        for _, (start, end, replacement) in ordered:
            result = result[:start] + replacement + result[end:]
        PronunciationLexicon.model_validate(yaml.safe_load(result))
        if yaml.safe_load(result) != data:
            raise ValueError('Không thể lưu cách đọc mà giữ nguyên từ điển; vui lòng thử lại.')
        write_text_atomic(path, result)
