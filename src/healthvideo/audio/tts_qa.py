"""R5 pre-render TTS checks. Never prompt ASR with the expected narration."""

import inspect
import json
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from healthvideo.audio.align import alignment_identity, normalize_word, pronunciation_qa
from healthvideo.storage.files import (
    canonical_json_hash,
    sha256_file,
    write_text_atomic,
)

QA_VERSION = 'r5-line-2'
WHISPER_UNAVAILABLE = 'Whisper unavailable'
LETTER_NAMES = dict(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ',
    ('a', 'bê', 'xê', 'đê', 'e', 'ép', 'giê', 'hát', 'i', 'giây', 'ca', 'e lờ',
     'em', 'en', 'o', 'pê', 'quy', 'e rờ', 'ét', 'tê', 'u', 'vê', 'vê kép', 'ích', 'i', 'dét'), strict=True))


def equivalents(text: str, lexicon: Mapping[str, str]) -> dict[str, str]:
    """Only expand letters actually present as names, never treat bơ as bê."""
    result = dict(lexicon)
    for letter in re.findall(r'(?<!\w)[A-Z](?!\w)', text):
        result.setdefault(letter, LETTER_NAMES[letter])
    return result


def asr_equivalents(lexicon: Mapping[str, str]) -> dict[str, str]:
    """Honor approved aliases and Vietnamese letter names in Whisper ITN."""
    return {**LETTER_NAMES, **lexicon}


def _latin_itn(heard: str) -> bool:
    # Spoken slash is ITN of a symbol, not evidence of a changed Vietnamese
    # medical syllable (e.g. PT/INR -> PT gạch chéo INA).
    heard = re.sub(r'\bgạch chéo\b', '/', heard, flags=re.IGNORECASE)
    return bool(re.search(r'[A-Za-z]', heard)) and heard.isascii()


def line_qa(alignment: Mapping[str, list[dict]], *, terms: Sequence[str] = ()) -> dict:
    """Sensitive phrases, missing/extra runs and catastrophic mismatch block.

    Ordinary substitutions remain listening advisories. Matching entire sensitive
    phrases avoids marking every occurrence of a common syllable as a medical term.
    """
    report = pronunciation_qa(alignment)
    advisory = {(f['line'], f['script_word'], f['start'], f['end'])
                for f in report['flags'] if f['severity'] == 'warn'}
    flags = []
    for line, words in alignment.items():
        norms = [normalize_word(w['word']) for w in words]
        sensitive = set()
        for term in terms:
            tokens = [normalize_word(t) for t in term.replace('-', ' ').split()]
            if not tokens:
                continue
            for i in range(len(words) - len(tokens) + 1):
                if norms[i:i + len(tokens)] == tokens:
                    sensitive.update(range(i, i + len(tokens)))
        sensitive.update(i for i, w in enumerate(words) if re.search(r'[A-Z]{2,}', w['word']))
        equivalent, unverifiable = set(), set()
        for i, word in enumerate(words):
            if word['matched']:
                continue
            heard = word.get('asr_source', word.get('heard', ''))
            letter = normalize_word(heard).upper()
            if len(letter) == 1 and letter in LETTER_NAMES and norms[i] == normalize_word(LETTER_NAMES[letter]):
                equivalent.add(i)
            elif i in sensitive and _latin_itn(heard):
                unverifiable.add(i)
        missing = set()
        i = 0
        while i < len(words):
            j = i
            while j < len(words) and not words[j]['matched'] and not words[j].get('heard'):
                j += 1
            if j - i >= 2:
                missing.update(range(i, j))
            i = max(i + 1, j)
        effective_matches = sum(w['matched'] or i in equivalent or i in unverifiable
                                or (line, w['word'], w['start'], w['end']) in advisory
                                for i, w in enumerate(words))
        low = not words or effective_matches / len(words) < .55
        for flag in report['flags']:
            if flag['line'] != line:
                continue
            indices = [i for i, w in enumerate(words)
                       if w['word'] == flag['script_word']
                       and (w['start'] == flag['start'] or w.get('extra_start') == flag['start'])]
            if indices and all(i in equivalent for i in indices) and not any(words[i].get('extra_heard') for i in indices):
                continue
            extra = any(w['word'] == flag['script_word'] and len(w.get('extra_heard', '').split()) >= 2
                        for w in words)
            source = next((words[i].get('extra_asr_source', words[i].get('asr_source', flag['heard']))
                           for i in indices), flag['heard'])
            uncertain = any(i in unverifiable for i in indices) or (
                any(i in sensitive for i in indices) and _latin_itn(source))
            changed_vietnamese = any(i in sensitive for i in indices) and bool(flag['heard']) and not flag['heard'].isascii()
            flag['severity'] = 'warn'
            if low or (extra and not uncertain) or any(i in missing for i in indices) or (changed_vietnamese and not uncertain):
                flag['severity'] = 'block'
                flag['priority'] = 'term' if any(i in sensitive for i in indices) else 'normal'
                flag['reason'] = ('low_line_match' if low else 'missing_phrase' if any(i in missing for i in indices)
                                  else 'extra_phrase' if extra else 'changed_vietnamese_term')
            elif uncertain:
                flag.update(reason='asr_unverifiable', warning_level='low', priority='normal', asr_source=source,
                            heard_expanded=flag['heard'], heard=source,
                            suggestion='Whisper viết lại bằng chữ Latin; không xác nhận được cách đọc Việt của thuật ngữ.')
            flags.append(flag)
        if not words:
            flags.append({'line': line, 'script_word': '', 'heard': '', 'severity': 'block',
                          'priority': 'normal', 'start': 0, 'end': 0, 'suggestion': 'Không nghe thấy lời.'})
    report['flags'] = flags
    report['blocked'] = not alignment or any(f['severity'] == 'block' for f in report['flags'])
    return report


def check_line(*, line_id: str, text: str, terms: Sequence[str], asr_lexicon: Mapping[str, str],
               cache_dir: Path, request_key: str, synthesize: Callable, aligner: Callable,
               accepted_hashes: set[str] | None = None, retry_id: str = '') -> tuple[dict, Path]:
    """Persist paid audio, retry budget, ASR result and exact-WAV acceptance."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    wav = cache_dir / f'{request_key}.wav'
    receipt = wav.with_suffix('.qa.json')
    identity = canonical_json_hash({'version': QA_VERSION, 'asr': alignment_identity(),
                                    'text': text, 'terms': list(terms), 'lexicon': dict(asr_lexicon)})
    state = {}
    try:
        state = json.loads(receipt.read_text(encoding='utf-8'))
        if state['wav_sha256'] != sha256_file(wav) or state['identity'] != identity:
            state = {}
    except (OSError, ValueError, KeyError, TypeError):
        state = {}
    accepted_hashes = accepted_hashes or set()

    def align(attempts: int) -> tuple[dict, dict]:
        params = inspect.signature(aligner).parameters
        kwargs = ({'preserve_asr_source': True} if 'preserve_asr_source' in params
                  or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()) else {})
        result = aligner({line_id: wav}, {line_id: text},
                         out_dir=cache_dir / 'alignment', asr_lexicon=asr_lexicon, **kwargs)
        checked = {**line_qa(result, terms=terms), 'identity': identity,
                   'wav_sha256': sha256_file(wav), 'attempts': attempts,
                   'retry_id': retry_id, 'text': text}
        if not result:
            checked['flags'] = [{'line': line_id, 'script_word': text,
                                 'heard': WHISPER_UNAVAILABLE, 'severity': 'block',
                                 'priority': 'normal', 'start': 0, 'end': 0,
                                 'suggestion': 'Khôi phục Whisper hoặc nghe lại audio.'}]
        write_text_atomic(receipt, json.dumps(checked, ensure_ascii=False, indent=2))
        return result, checked

    if not state or (retry_id and state.get('retry_id') != retry_id):
        # A later render failure must not reset this line's paid retry budget.
        for attempt in range(2):
            synthesize(wav, bool(attempt or retry_id))
            result, state = align(attempt + 1)
            if not state['blocked'] or state['wav_sha256'] in accepted_hashes or not result:
                break
    elif any(f.get('heard') == WHISPER_UNAVAILABLE for f in state.get('flags', [])):
        # A Whisper outage says nothing about the audio: re-check the paid WAV, never re-synthesize.
        _, state = align(state.get('attempts', 1))
    result = json.loads(json.dumps(state))
    if result['wav_sha256'] in accepted_hashes:
        result['doctor_accepted'] = True
        result['blocked'] = False
        for flag in result['flags']:
            flag['severity'] = 'warn'
    return result, wav


def aggregate(reports: Sequence[dict]) -> dict:
    return {**pronunciation_qa({}),
            'status': 'unavailable' if any(r['status'] == 'unavailable' for r in reports) else 'aligned',
            'lines': [line for r in reports for line in r['lines']],
            'flags': [flag for r in reports for flag in r['flags']],
            'blocked': any(r['blocked'] for r in reports),
            'wav_checks': [{k: r.get(k) for k in ('wav_sha256', 'attempts', 'doctor_accepted')}
                           for r in reports]}
