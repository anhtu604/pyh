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
from healthvideo.storage.files import write_text_atomic

MODEL_ID = 'Systran/faster-whisper-large-v3'
MODEL_REVISION = 'edaa852ec7e145841d8ffdb056a99866b5f0a478'
ALIGN_VERSION = '1-fw1.2.1-ct2-4.8.3'
MODEL_FILES = ('model.bin', 'config.json', 'tokenizer.json', 'preprocessor_config.json')


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


def normalize_word(text: str) -> str:
    # NFC makes decomposed Vietnamese tones identical without erasing meaningful tones.
    return ''.join(c for c in unicodedata.normalize('NFC', text).casefold() if c.isalnum())


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
    matcher = SequenceMatcher(None, [normalize_word(t) for t in tokens],
                              [normalize_word(w['word']) for w in heard], autojunk=False)
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
                cache_dir: Path | None = None, runner=subprocess.run) -> dict[str, list[dict]]:
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
                process = runner([str(whisper_python()), '-X', 'utf8',
                                  str(REPO_ROOT/'tools/whisper/transcribe.py'),
                                  '--request', str(request), '--out', str(output)],
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
            result[line] = map_words(scripts[line], raw[line], duration=durations[line])
            _write_json(out_dir/f'{line}.json', result[line])
            _write_json(out_dir/f'{line}.meta.json', {'cache_key': keys[line], **alignment_identity()})
        return result
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, wave.Error) as error:
        warnings.warn(f'Whisper alignment skipped: {error}; using estimated timing', stacklevel=2)
        return {}


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
            def without_accents(value: str) -> str:
                return ''.join(c for c in unicodedata.normalize('NFD', normalize_word(value))
                               if not unicodedata.combining(c)).replace('đ', 'd')
            # Only a plausible accent confusion in an ordinary Vietnamese word is
            # advisory. Missing speech, inserted speech and changed terms block.
            tone_only = (normalize_word(text) not in term_words
                         and not re.search(r'[A-Z]{2,}', text)
                         and not word.get('extra_heard')
                         and bool(heard) and without_accents(text) == without_accents(heard)
                         and (normalize_word(text) != without_accents(text)
                              or normalize_word(heard) != without_accents(heard)))
            if tone_only:
                priority = 'normal'
            flags.append({'line': line, 'script_word': text,
                          'heard': heard, 'severity': 'warn' if tone_only else 'block',
                          'start': word.get('extra_start', word['start']),
                          'end': word.get('extra_end', word['end']), 'priority': priority,
                          'suggestion': f'Nghe lại; nếu cần, thêm {text!r} vào pronunciation.vi.yaml.'})
    flags.sort(key=lambda flag: flag['priority'] != 'term')
    return {'schema_version': '1.0', 'model_id': MODEL_ID, 'lines': lines, 'flags': flags,
            'blocked': any(flag['severity'] == 'block' for flag in flags),
            'status': 'aligned' if alignment else 'unavailable',
            'note': 'ASR có thể nghe sai; bác sĩ nghe lại trước khi quyết định. Không tự sửa kịch bản.'}
