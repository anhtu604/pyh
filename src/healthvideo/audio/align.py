"""Optional offline ASR, script-word alignment and pronunciation review data.

ASR is deliberately unprompted: feeding the script to Whisper would hide errors.
Only this module's subprocess imports faster-whisper, in the dedicated venv.
"""
import hashlib
import json
import math
import os
import re
import subprocess
import unicodedata
import warnings
import wave
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
from pathlib import Path
from tempfile import TemporaryDirectory

from healthvideo.audio.music import REPO_ROOT, shared_repo_root
from healthvideo.process import run_with_deadline, timeout_diagnostic
from healthvideo.storage.files import write_text_atomic

MODEL_ID = 'Systran/faster-whisper-large-v3'
MODEL_REVISION = 'edaa852ec7e145841d8ffdb056a99866b5f0a478'
ALIGN_VERSION = '1-fw1.2.1-ct2-4.8.3'
MODEL_FILES = ('model.bin', 'config.json', 'tokenizer.json', 'preprocessor_config.json')
ALIGN_TIMEOUT = 30 * 60  # One batch for a full 10–25 minute video, including model load.


def whisper_python(repo: Path = REPO_ROOT) -> Path:
    return Path(os.environ.get('HEALTHVIDEO_WHISPER_PYTHON',
                str(shared_repo_root(repo) / 'cache/whisper-venv/Scripts/python.exe')))


def whisper_model(repo: Path = REPO_ROOT) -> Path:
    return shared_repo_root(repo) / 'cache/models/whisper-large-v3'


def model_ready(repo: Path = REPO_ROOT) -> bool:
    return all((whisper_model(repo) / name).is_file() for name in MODEL_FILES)


def alignment_identity() -> dict:
    return {'model_id': MODEL_ID, 'revision': MODEL_REVISION, 'version': ALIGN_VERSION,
            'available': whisper_python().is_file() and model_ready(),
            'device': os.environ.get('HEALTHVIDEO_WHISPER_DEVICE', 'auto'),
            'compute_type': os.environ.get('HEALTHVIDEO_WHISPER_COMPUTE_TYPE', 'auto')}


_VI_NUMBER_WORDS = {
    '0': 'không',
    '1': 'một',
    '2': 'hai',
    '3': 'ba',
    '4': 'bốn',
    '5': 'năm',
    '6': 'sáu',
    '7': 'bảy',
    '8': 'tám',
    '9': 'chín',
    '10': 'mười',
}
_IY_TRANS = str.maketrans('yỳýỷỹỵ', 'iìíỉĩị')
_VI_VOWELS = frozenset(
    'aeiouyăâêôơư'
    'àáảãạằắẳẵặầấẩẫậ'
    'èéẻẽẹềếểễệ'
    'ìíỉĩị'
    'òóỏõọồốổỗộờớởỡợ'
    'ùúủũụừứửữự'
    'ỳýỷỹỵ'
)
_VI_RIME_RE = re.compile(
    f'^[{"".join(sorted(_VI_VOWELS))}]+(?:ch|ng|nh|[cmnpt])?$'
)


def normalize_word(text: str) -> str:
    # NFC makes decomposed Vietnamese tones identical without erasing meaningful tones.
    return ''.join(c for c in unicodedata.normalize('NFC', text).casefold() if c.isalnum())


def _match_key(text: str) -> str:
    norm = normalize_word(text)
    return _VI_NUMBER_WORDS.get(norm, norm)


def _fold_iy(text: str) -> str:
    return text.translate(_IY_TRANS)


def _asr_lexicon_maps(
    asr_lexicon: Mapping[str, str],
) -> tuple[dict[tuple[str, ...], list[str]], dict[tuple[str, ...], list[str]], int]:
    exact_map: dict[tuple[str, ...], list[str]] = {}
    iy_map: dict[tuple[str, ...], list[str]] = {}
    max_len = 0
    for written, spoken in asr_lexicon.items():
        syllables = [tok for tok in str(spoken).replace('-', ' ').split() if normalize_word(tok)]
        if not syllables:
            continue
        candidates: list[tuple[str, ...]] = []
        phrase = tuple(
            part for part in (normalize_word(piece) for piece in re.split(r'[\s/\-]+', str(written)))
            if part
        )
        if phrase:
            candidates.append(phrase)
        collapsed = normalize_word(str(written))
        if collapsed and (collapsed,) != phrase:
            candidates.append((collapsed,))
        for key in candidates:
            exact_map.setdefault(key, syllables)
            max_len = max(max_len, len(key))
            if all(len(part) >= 2 for part in key):
                iy_map.setdefault(tuple(_fold_iy(part) for part in key), syllables)
    return exact_map, iy_map, max_len


def _expand_asr_words(raw_words: Sequence[dict], asr_lexicon: Mapping[str, str]) -> list[dict]:
    """Expand Whisper ITN tokens matching ``asr_lexicon`` into timed spoken syllables."""
    if not asr_lexicon or not raw_words:
        return [dict(item) for item in raw_words]
    exact_map, iy_map, max_len = _asr_lexicon_maps(asr_lexicon)
    if not exact_map:
        return [dict(item) for item in raw_words]
    norms = [normalize_word(str(item['word'])) for item in raw_words]
    iy_norms = [_fold_iy(norm) for norm in norms]
    expanded: list[dict] = []
    idx = 0
    total = len(raw_words)
    while idx < total:
        matched_n = 0
        syllables: list[str] | None = None
        for n in range(min(max_len, total - idx), 0, -1):
            window_exact = tuple(norms[idx : idx + n])
            syllables = exact_map.get(window_exact)
            if syllables is None and all(len(part) >= 2 for part in window_exact):
                syllables = iy_map.get(tuple(iy_norms[idx : idx + n]))
            if syllables is not None:
                matched_n = n
                break
        if syllables is None:
            expanded.append(dict(raw_words[idx]))
            idx += 1
            continue
        start = float(raw_words[idx]['start'])
        end = float(raw_words[idx + matched_n - 1]['end'])
        prob = min(float(item['prob']) for item in raw_words[idx : idx + matched_n])
        count = len(syllables)
        for k, syllable in enumerate(syllables):
            syl_start = start + (end - start) * k / count
            syl_end = end if k == count - 1 else start + (end - start) * (k + 1) / count
            expanded.append({'word': syllable, 'start': syl_start, 'end': syl_end, 'prob': prob})
        idx += matched_n
    return expanded


def _clean_asr(words: Sequence[dict], duration: float) -> list[dict]:
    cleaned = []
    previous = 0.0
    for item in words:
        start, end, prob = float(item['start']), float(item['end']), float(item['prob'])
        if not all(math.isfinite(v) for v in (start, end, prob)) or not 0 <= prob <= 1:
            raise ValueError('Invalid ASR timestamp/probability')
        if start < 0 or end < start or end > duration + .15 or start + .001 < previous:
            raise ValueError('ASR timestamps outside WAV or out of order')
        previous = end
        tokens = str(item['word']).split()
        for i, token in enumerate(tokens):
            if normalize_word(token):
                cleaned.append({'word': token, 'start': min(duration, start + (end-start)*i/len(tokens)),
                                    'end': min(duration, start + (end-start)*(i+1)/len(tokens)), 'prob': prob})
    return cleaned


def map_words(script: str, asr_words: Sequence[dict], *, duration: float) -> list[dict]:
    """Align canonical script tokens with difflib; interpolate every unmatched run."""
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('WAV duration must be positive')
    tokens = script.split()
    heard = _clean_asr(asr_words, duration)
    result = [{'word': t, 'start': 0., 'end': 0., 'prob': 0., 'matched': False, 'heard': ''} for t in tokens]
    matcher = SequenceMatcher(None, [_match_key(t) for t in tokens],
                              [_match_key(w['word']) for w in heard], autojunk=False)
    for tag, a, b, c, d in matcher.get_opcodes():
        if tag == 'equal':
            for i, j in zip(range(a, b), range(c, d), strict=True):
                result[i].update(heard[j], word=tokens[i], heard=heard[j]['word'], matched=True)
        elif b > a:
            recognized = ' '.join(w['word'] for w in heard[c:d])
            for i in range(a, b):
                result[i]['heard'] = recognized
        elif c < d and result:
            # Retain inserted ASR speech for QA without creating non-script captions.
            i = max(0, a - 1)
            result[i]['extra_heard'] = ' '.join(w['word'] for w in heard[c:d])
            result[i]['extra_start'] = heard[c]['start']
            result[i]['extra_end'] = heard[d-1]['end']
    i = 0
    while i < len(result):
        if result[i]['matched']:
            i += 1
            continue
        end = i
        while end < len(result) and not result[end]['matched']:
            end += 1
        left = result[i-1]['end'] if i else 0.
        right = result[end]['start'] if end < len(result) else duration
        for j in range(i, end):
            result[j]['start'] = left + (right-left)*(j-i)/(end-i)
            result[j]['end'] = left + (right-left)*(j-i+1)/(end-i)
        i = end
    return result


def _duration(path: Path) -> float:
    with wave.open(str(path), 'rb') as wav:
        return wav.getnframes() / wav.getframerate()


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def align_lines(line_wavs: Mapping[str, Path], scripts: Mapping[str, str], *, out_dir: Path,
                cache_dir: Path | None = None, runner=subprocess.run,
                asr_lexicon: Mapping[str, str] | None = None) -> dict[str, list[dict]]:
    """Load one ASR model per batch; raw transcripts cache by WAV/model/version hash.

    Missing runtime or inference failure is nonblocking. Per-line JSON contains
    script words; the shared cache contains the unmodified ASR words.
    """
    if not whisper_python().is_file() or not model_ready():
        warnings.warn('Whisper unavailable (venv/model missing); using estimated timing', stacklevel=2)
        return {}
    cache = cache_dir or shared_repo_root() / 'cache/whisper-alignment'
    cache.mkdir(parents=True, exist_ok=True)
    raw, pending, keys, durations = {}, [], {}, {}
    try:
        for line, wav in line_wavs.items():
            if Path(line).name != line or any(c in line for c in '/\\:') or line in {'.', '..'}:
                raise ValueError('Unsafe alignment line id')
            durations[line] = _duration(wav)
            key = hashlib.sha256(wav.read_bytes() + json.dumps(alignment_identity(), sort_keys=True).encode()).hexdigest()
            keys[line] = key
            try:
                data = json.loads((cache / f'{key}.json').read_text(encoding='utf-8'))
                raw[line] = _clean_asr(data, durations[line])
            except (OSError, ValueError, KeyError, TypeError):
                pending.append({'id': line, 'wav': str(wav.resolve())})
        if pending:
            with TemporaryDirectory(prefix='.whisper-', dir=cache) as temporary:
                request, output = Path(temporary)/'request.json', Path(temporary)/'output.json'
                _write_json(request, {'model': str(whisper_model()), 'lines': pending})
                process = run_with_deadline([str(whisper_python()), '-X', 'utf8',
                                  str(REPO_ROOT/'tools/whisper/transcribe.py'),
                                  '--request', str(request), '--out', str(output)],
                                 timeout=ALIGN_TIMEOUT, runner=runner,
                                 shell=False, check=False, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace')
                if process.returncode:
                    raise RuntimeError((process.stderr or 'ASR failed')[-2000:])
                received = json.loads(output.read_text(encoding='utf-8'))
                for item in pending:
                    line = item['id']
                    raw[line] = _clean_asr(received[line], durations[line])
                    _write_json(cache/f'{keys[line]}.json', raw[line])
        result = {}
        for line in line_wavs:
            if not raw[line]:
                warnings.warn(f'Whisper heard no words for {line}; using estimated timing', stacklevel=2)
            heard_words = _expand_asr_words(raw[line], asr_lexicon) if asr_lexicon else raw[line]
            result[line] = map_words(scripts[line], heard_words, duration=durations[line])
            _write_json(out_dir/f'{line}.json', result[line])
            _write_json(out_dir/f'{line}.meta.json', {'cache_key': keys[line], **alignment_identity()})
        return result
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, wave.Error, subprocess.TimeoutExpired) as error:
        detail = timeout_diagnostic(error) if isinstance(error, subprocess.TimeoutExpired) else str(error)
        warnings.warn(f'Whisper alignment skipped: {detail}; using estimated timing', stacklevel=2)
        return {}


def _without_accents(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', normalize_word(value))
                   if not unicodedata.combining(c)).replace('đ', 'd')


def _onset_rime(word: str) -> tuple[str, str] | None:
    """Split Vietnamese homophone onset groups (s/x, tr/ch, d/gi/r) from rime+tone."""
    norm = normalize_word(word)
    if len(norm) < 2:
        return None
    group: str | None = None
    rime = ''
    if norm.startswith(('s', 'x')):
        group, rime = 's_x', norm[1:]
    elif norm.startswith(('tr', 'ch')):
        group, rime = 'tr_ch', norm[2:]
    elif norm.startswith('gi'):
        if len(norm) == 2:
            group, rime = 'd_gi_r', 'i'
        elif norm[2] in 'êềếểễệ':
            group, rime = 'd_gi_r', 'i' + norm[2:]
        elif norm[2] in _VI_VOWELS:
            group, rime = 'd_gi_r', norm[2:]
        else:
            group, rime = 'd_gi_r', norm[1:]
    elif (
        (norm[0] == 'g' and norm[1] in 'iìíỉĩị' and (len(norm) == 2 or norm[2] not in _VI_VOWELS))
        or norm.startswith(('d', 'r'))
    ):
        group, rime = 'd_gi_r', norm[1:]
    if group is None or not rime or not _VI_RIME_RE.match(rime):
        return None
    return group, rime


def _is_homophone_onset_confusion(text: str, heard: str) -> bool:
    if len(heard.split()) != 1:
        return False
    norm_text, norm_heard = normalize_word(text), normalize_word(heard)
    if not norm_text or not norm_heard or norm_text == norm_heard:
        return False
    text_parts = _onset_rime(text)
    heard_parts = _onset_rime(heard)
    return text_parts is not None and text_parts == heard_parts


def pronunciation_qa(alignment: Mapping[str, list[dict]], *, terms: Sequence[str] = ()) -> dict:
    term_words = {normalize_word(w) for term in terms for w in term.split()}
    flags, lines = [], []
    for line, words in alignment.items():
        lines.append({'line': line, 'match_ratio': sum(w['matched'] for w in words)/len(words) if words else 0,
                      'word_count': len(words)})
        for word in words:
            if word['matched'] and not word.get('extra_heard'):
                continue
            text = word['word']
            # ASCII biomedical/English tokens and abbreviations deserve first review.
            priority = ('term' if normalize_word(text) in term_words or
                        re.search(r'[A-Z]{2,}', text) or re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{2,}[.,;:!?]?', text)
                        else 'normal')
            heard = word.get('extra_heard') or word['heard']
            norm_text = normalize_word(text)
            eligible_for_warn = (
                norm_text not in term_words
                and not re.search(r'[A-Z]{2,}', text)
                and not word.get('extra_heard')
                and bool(heard)
            )
            # Only a plausible accent or Vietnamese homophone-onset confusion in an
            # ordinary Vietnamese word is advisory. Missing speech, inserted speech
            # and changed terms block.
            tone_only = (
                eligible_for_warn
                and _without_accents(text) == _without_accents(heard)
                and (norm_text != _without_accents(text)
                     or normalize_word(heard) != _without_accents(heard))
            )
            onset_confused = eligible_for_warn and _is_homophone_onset_confusion(text, heard)
            if tone_only or onset_confused:
                priority = 'normal'
            flags.append({'line': line, 'script_word': text,
                          'heard': heard, 'severity': 'warn' if (tone_only or onset_confused) else 'block',
                          'start': word.get('extra_start', word['start']),
                          'end': word.get('extra_end', word['end']), 'priority': priority,
                          'suggestion': f'Nghe lại; nếu cần, thêm {text!r} vào pronunciation.vi.yaml.'})
    flags.sort(key=lambda flag: flag['priority'] != 'term')
    return {'schema_version': '1.0', 'model_id': MODEL_ID, 'lines': lines, 'flags': flags,
            'blocked': any(flag['severity'] == 'block' for flag in flags),
            'status': 'aligned' if alignment else 'unavailable',
            'note': 'ASR có thể nghe sai; bác sĩ nghe lại trước khi quyết định. Không tự sửa kịch bản.'}
