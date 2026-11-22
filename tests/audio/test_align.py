import json
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from healthvideo.audio.align import align_lines, map_words, pronunciation_qa


def test_alignment_timeout_uses_estimated_timing_and_cleans_staging(tmp_path, monkeypatch):
    from healthvideo.audio import align

    python = tmp_path / 'python.exe'
    python.touch()
    monkeypatch.setattr(align, 'whisper_python', lambda: python)
    monkeypatch.setattr(align, 'model_ready', lambda: True)
    wav = tmp_path / 'line.wav'
    with wave.open(str(wav), 'wb') as stream:
        stream.setparams((1, 2, 8000, 0, 'NONE', ''))
        stream.writeframes(b'\x01\x00' * 8000)

    def hang(argv, **kwargs):
        assert kwargs['timeout'] > 0
        raise subprocess.TimeoutExpired(argv, kwargs['timeout'], stderr=b'loading ASR')

    with pytest.warns(UserWarning, match='Whisper.*timed out.*loading ASR'):
        assert align_lines({'LN01': wav}, {'LN01': 'Urat'}, out_dir=tmp_path / 'out',
                           cache_dir=tmp_path / 'cache', runner=hang) == {}
    assert not list((tmp_path / 'cache').iterdir())


def words(*texts):
    return [{'word': t, 'start': i * .5, 'end': (i + 1) * .5, 'prob': .95} for i, t in enumerate(texts)]


def test_alignment_maps_asr_words_to_script_words():
    result = map_words('Tinh thể URAT.', words('tinh', 'thể', 'urat'), duration=2)
    assert [w['word'] for w in result] == ['Tinh', 'thể', 'URAT.']
    assert all(w['matched'] for w in result)
    assert result[2]['start'] == 1


def test_alignment_interpolates_unmatched():
    result = map_words('một tinh thể nhỏ', words('một', 'nhỏ'), duration=2)
    assert [w['matched'] for w in result] == [True, False, False, True]
    assert result[0]['end'] <= result[1]['start'] <= result[1]['end'] <= result[2]['start']
    assert result[2]['end'] <= result[3]['start']
    assert all(0 <= w['start'] <= w['end'] <= 2 for w in result)


def test_alignment_cached_by_hash(tmp_path, monkeypatch):
    from healthvideo.audio import align
    python = tmp_path / 'python.exe'
    python.touch()
    monkeypatch.setattr(align, 'whisper_python', lambda: python)
    monkeypatch.setattr(align, 'model_ready', lambda: True)
    wav = tmp_path / 'line.wav'
    with wave.open(str(wav), 'wb') as f:
        f.setparams((1, 2, 8000, 0, 'NONE', ''))
        f.writeframes(b'\x01\x00' * 8000)
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        request = json.loads(Path(argv[argv.index('--request') + 1]).read_text())
        output = {item['id']: words('Urat') for item in request['lines']}
        Path(argv[argv.index('--out') + 1]).write_text(json.dumps(output))
        return SimpleNamespace(returncode=0, stderr='')

    args = {'line_wavs': {'LN01': wav}, 'scripts': {'LN01': 'Urat'}, 'out_dir': tmp_path/'out',
                'cache_dir': tmp_path/'cache', 'runner': run}
    first = align_lines(**args)
    assert first['LN01'][0]['matched']
    assert align_lines(**args) == first
    assert len(calls) == 1
    args['scripts'] = {'LN01': 'khác'}
    assert not align_lines(**args)['LN01'][0]['matched']
    assert len(calls) == 1
    monkeypatch.setattr(align, 'ALIGN_VERSION', 'test-v2')
    align_lines(**args)
    assert len(calls) == 2
    wav.write_bytes(wav.read_bytes() + b'changed')
    align_lines(**args)
    assert len(calls) == 3


def test_missing_whisper_falls_back(tmp_path, monkeypatch):
    from healthvideo.audio import align
    monkeypatch.setattr(align, 'whisper_python', lambda: tmp_path/'absent')
    with pytest.warns(UserWarning, match='Whisper'):
        assert align_lines({'LN01': tmp_path/'absent.wav'}, {'LN01': 'Urat'},
                           out_dir=tmp_path/'out') == {}


def test_pronunciation_qa_flags_term_mismatch():
    aligned = map_words('Tinh thể URAT', words('tinh', 'thể', 'u', 'rát'), duration=2)
    report = pronunciation_qa({'LN01': aligned}, terms=['URAT'])
    assert report['lines'][0]['match_ratio'] == pytest.approx(2 / 3)
    flag = report['flags'][0]
    assert flag['script_word'] == 'URAT'
    assert flag['heard'] == 'u rát'
    assert flag['priority'] == 'term'
    assert flag['severity'] == 'block'
    assert report['blocked'] is True
    assert 'pronunciation.vi.yaml' in flag['suggestion']


def test_only_vietnamese_tone_mismatch_warns():
    tone = pronunciation_qa({'LN01': map_words('mỡ', words('mô'), duration=1)})
    assert tone['flags'][0]['severity'] == 'warn'
    missing = pronunciation_qa({'LN01': map_words('mỡ', [], duration=1)})
    assert missing['flags'][0]['severity'] == 'block'
    term = pronunciation_qa({'LN01': map_words('gút', words('gót'), duration=1)}, terms=['gút'])
    assert term['flags'][0]['severity'] == 'block'


@pytest.mark.parametrize(('script', 'heard'), [('ma', 'má'), ('tim', 'tím'), ('mai', 'mái')])
def test_unaccented_vietnamese_tone_mismatch_warns(script, heard):
    report = pronunciation_qa({'LN01': map_words(script, words(heard), duration=1)})
    assert report['flags'][0]['severity'] == 'warn'
    assert report['blocked'] is False


def test_dictionary_term_with_tone_only_mismatch_still_blocks():
    report = pronunciation_qa({'LN01': map_words('urat', words('urát'), duration=1)}, terms=['urat'])
    assert report['flags'][0]['severity'] == 'block'


def test_english_word_mismatch_still_blocks():
    report = pronunciation_qa({'LN01': map_words('pain', words('pen'), duration=1)})
    assert report['flags'][0]['severity'] == 'block'


def test_pronunciation_insertions_keep_real_audio_time():
    aligned = map_words('one two', [
        {'word': 'one', 'start': 0, 'end': .1, 'prob': .9},
        {'word': 'urat', 'start': 8, 'end': 8.3, 'prob': .9},
        {'word': 'two', 'start': 9, 'end': 9.2, 'prob': .9},
    ], duration=10)
    flag = pronunciation_qa({'LN01': aligned})['flags'][0]
    assert (flag['heard'], flag['start'], flag['end']) == ('urat', 8, 8.3)


def test_no_speech_is_retained_in_pronunciation_qa():
    aligned = map_words('Tinh thể URAT', [], duration=2)
    report = pronunciation_qa({'LN01': aligned}, terms=['URAT'])
    assert report['lines'][0]['match_ratio'] == 0
    assert len(report['flags']) == 3
    assert all(not w['matched'] for w in aligned)


def test_alignment_normalization_preserves_meaningful_vietnamese_tones():
    import unicodedata
    aligned = map_words('mỡ', words(unicodedata.normalize('NFD', 'MỠ')), duration=1)
    assert aligned[0]['matched']
    assert not map_words('mỡ', words('mô'), duration=1)[0]['matched']


def test_missing_whisper_model_falls_back(tmp_path, monkeypatch):
    from healthvideo.audio import align
    python = tmp_path/'python.exe'
    python.touch()
    monkeypatch.setattr(align, 'whisper_python', lambda: python)
    monkeypatch.setattr(align, 'model_ready', lambda: False)
    with pytest.warns(UserWarning, match='Whisper'):
        assert align_lines({'LN01': tmp_path/'absent.wav'}, {'LN01': 'word'},
                           out_dir=tmp_path/'out') == {}


@pytest.mark.parametrize(
    ('digit', 'word'),
    [
        ('0', 'không'), ('1', 'một'), ('2', 'hai'), ('3', 'ba'),
        ('4', 'bốn'), ('5', 'năm'), ('6', 'sáu'), ('7', 'bảy'),
        ('8', 'tám'), ('9', 'chín'), ('10', 'mười'),
    ],
)
def test_map_words_matches_vietnamese_digits_0_to_10(digit, word):
    spoken_to_digit = map_words(f'gấp {word}, lần', words('gấp', f'{digit},', 'lần'), duration=1.5)
    assert all(entry['matched'] for entry in spoken_to_digit)
    assert spoken_to_digit[1]['heard'] == f'{digit},'
    assert pronunciation_qa({'LN01': spoken_to_digit})['flags'] == []

    digit_to_spoken = map_words(f'gấp {digit} lần', words('gấp', word, 'lần'), duration=1.5)
    assert all(entry['matched'] for entry in digit_to_spoken)
    assert digit_to_spoken[1]['heard'] == word

    mismatch = map_words('gấp sáu lần', words('gấp', '7', 'lần'), duration=1.5)
    assert not mismatch[1]['matched']


def test_align_lines_asr_lexicon_expands_itn_and_iy_without_polluting_cache(tmp_path, monkeypatch):
    from healthvideo.audio import align

    python = tmp_path / 'python.exe'
    python.touch()
    monkeypatch.setattr(align, 'whisper_python', lambda: python)
    monkeypatch.setattr(align, 'model_ready', lambda: True)
    wav = tmp_path / 'line.wav'
    with wave.open(str(wav), 'wb') as stream:
        stream.setparams((1, 2, 8000, 0, 'NONE', ''))
        stream.writeframes(b'\x01\x00' * 8000 * 6)

    asr_output = [
        {'word': 'ALT,', 'start': 0.0, 'end': 0.9, 'prob': 0.9},
        {'word': 'virus', 'start': 1.0, 'end': 1.6, 'prob': 0.92},
        {'word': 'silimarin', 'start': 2.0, 'end': 3.2, 'prob': 0.88},
        {'word': 'acid', 'start': 3.5, 'end': 4.0, 'prob': 0.85},
        {'word': 'uric', 'start': 4.0, 'end': 4.7, 'prob': 0.91},
    ]
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        request = json.loads(Path(argv[argv.index('--request') + 1]).read_text(encoding='utf-8'))
        output = {item['id']: asr_output for item in request['lines']}
        Path(argv[argv.index('--out') + 1]).write_text(json.dumps(output), encoding='utf-8')
        return SimpleNamespace(returncode=0, stderr='')

    cache_dir = tmp_path / 'cache'
    lexicon = {
        'ALT': 'a lờ tê',
        'virus': 'vi rút',
        'silymarin': 'xi li ma rin',
        'acid uric': 'a xít u ríc',
    }
    spoken_script = 'a lờ tê, vi rút xi li ma rin a xít u ríc'
    canonical_script = 'ALT, virus silymarin acid uric'

    # First call WITHOUT asr_lexicon (captions) populates cache with raw ASR tokens.
    captions = align_lines(
        {'LN01': wav}, {'LN01': canonical_script},
        out_dir=tmp_path / 'align-captions', cache_dir=cache_dir, runner=run,
    )
    assert [w['word'] for w in captions['LN01']] == canonical_script.split()
    assert [w['matched'] for w in captions['LN01']] == [True, True, False, True, True]
    assert captions['LN01'][0]['heard'] == 'ALT,'

    # Second call WITH asr_lexicon (QA) reuses raw cache and expands syllables evenly.
    qa = align_lines(
        {'LN01': wav}, {'LN01': spoken_script},
        out_dir=tmp_path / 'align-qa', cache_dir=cache_dir, runner=run, asr_lexicon=lexicon,
    )
    assert len(calls) == 1
    assert all(w['matched'] for w in qa['LN01'])
    assert [w['word'] for w in qa['LN01']] == spoken_script.split()
    assert qa['LN01'][0]['start'] == pytest.approx(0.0)
    assert qa['LN01'][0]['end'] == pytest.approx(0.3)
    assert qa['LN01'][1]['start'] == pytest.approx(0.3)
    assert qa['LN01'][1]['end'] == pytest.approx(0.6)
    assert qa['LN01'][2]['start'] == pytest.approx(0.6)
    assert qa['LN01'][2]['end'] == pytest.approx(0.9)
    assert qa['LN01'][5]['heard'] == 'xi'
    assert qa['LN01'][5]['start'] == pytest.approx(2.0)
    assert qa['LN01'][8]['end'] == pytest.approx(3.2)
    assert qa['LN01'][9]['start'] == pytest.approx(3.5)
    assert qa['LN01'][12]['end'] == pytest.approx(4.7)
    assert qa['LN01'][9]['prob'] == pytest.approx(0.85)
    assert pronunciation_qa({'LN01': qa['LN01']}, terms=[*lexicon.keys(), *lexicon.values()])['flags'] == []

    # Even if QA runs first on a cold cache, raw cache remains unexpanded for captions.
    cold_cache = tmp_path / 'cold-cache'
    qa_first = align_lines(
        {'LN01': wav}, {'LN01': spoken_script},
        out_dir=tmp_path / 'align-qa-first', cache_dir=cold_cache, runner=run, asr_lexicon=lexicon,
    )
    captions_second = align_lines(
        {'LN01': wav}, {'LN01': canonical_script},
        out_dir=tmp_path / 'align-captions-second', cache_dir=cold_cache, runner=run,
    )
    assert len(calls) == 2
    assert all(w['matched'] for w in qa_first['LN01'])
    assert captions_second['LN01'][0]['heard'] == 'ALT,'


@pytest.mark.parametrize(
    ('script', 'heard'),
    [
        ('xơ', 'sơ'),
        ('xưởng,', 'sưởng,'),
        ('trứng', 'chứng'),
        ('chuyện', 'truyện'),
        ('dùng', 'rùng'),
        ('giả', 'dả'),
        ('gì', 'rì'),
        ('giết', 'riết'),
        ('gia', 'ra'),
    ],
)
def test_vietnamese_homophone_onset_confusion_warns_only(script, heard):
    report = pronunciation_qa({'LN01': map_words(script, words(heard), duration=1)})
    assert len(report['flags']) == 1
    flag = report['flags'][0]
    assert flag['severity'] == 'warn'
    assert flag['priority'] == 'normal'
    assert report['blocked'] is False


@pytest.mark.parametrize(
    ('script', 'heard', 'terms'),
    [
        ('gút', 'gót', ['gút']),
        ('urat', 'urát', ['urat']),
        ('xơ', 'sơ', ['xơ']),
        ('rai', 'dài', ['sắp cờ rai']),
        ('pain', 'pen', []),
        ('URAT', 'u rát', []),
        ('SA', 'xa', []),
        ('xơ', 'sờ', []),
        ('giả', 'rà', []),
        ('đầu', 'rầu', []),
        ('đầu', 'giầu', []),
        ('xơ', 'tơ', []),
        ('gia', 'ria', []),
        ('gãy', 'dãy', []),
        ('silymarin', 'xilymarin', []),
    ],
)
def test_homophone_exceptions_terms_english_and_abbreviations_still_block(script, heard, terms):
    report = pronunciation_qa({'LN01': map_words(script, words(*heard.split()), duration=1)}, terms=terms)
    assert report['blocked'] is True
    assert any(flag['severity'] == 'block' for flag in report['flags'])


def test_homophone_onset_with_extra_heard_still_blocks():
    aligned = map_words('xơ', words('sơ', 'thêm'), duration=1)
    aligned[0]['extra_heard'] = 'thêm'
    report = pronunciation_qa({'LN01': aligned})
    assert report['blocked'] is True
    assert report['flags'][0]['severity'] == 'block'


def test_produce_passes_asr_lexicon_only_to_qa_alignment(tmp_path, monkeypatch):
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.domain.project_v2 import WorkflowState
    from healthvideo.storage.files import read_yaml, write_yaml_atomic
    from healthvideo.tts import pronunciation as pronunciation_module
    from healthvideo.tts.silent import SilentTTS
    from healthvideo.workflows import produce
    from healthvideo.workflows.gate_review import approve_gate
    from tests.helpers import create_v2_project_fixture
    from tests.workflows.test_produce import V2_REVIEWED_AT, _write_synthetic_output

    profile = tmp_path / 'pronunciation.vi.yaml'
    write_yaml_atomic(profile, {
        'schema_version': '1.0', 'language': 'vi', 'version': 'test',
        'entries': [{'written': 'Synthetic', 'spoken': 'sin-thét-tíc'}],
    })
    monkeypatch.setattr(pronunciation_module, 'PRONUNCIATION_PROFILE_PATH', profile)

    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    approve_gate(project, GateKind.MEDICAL, reviewer='doctor', now=V2_REVIEWED_AT)

    align_calls = []

    def spy_align(line_wavs, scripts, *, out_dir, asr_lexicon=None):
        align_calls.append({
            'out_dir': Path(out_dir).name,
            'scripts': dict(scripts),
            'asr_lexicon': dict(asr_lexicon) if asr_lexicon is not None else None,
        })
        return {}

    monkeypatch.setattr(produce, 'align_lines', spy_align)
    produce.produce_project(project, SilentTTS(), lambda argv: (_write_synthetic_output(argv) or 0))

    assert len(align_calls) == 2
    assert align_calls[0]['out_dir'] == 'alignment'
    assert align_calls[0]['asr_lexicon'] is None
    assert align_calls[1]['out_dir'] == 'pronunciation-alignment'
    assert align_calls[1]['asr_lexicon'] == {'Synthetic': 'sin thét tíc'}
    rendered = read_yaml(project / 'revisions/001/renders/render-input.json')
    assert 'Synthetic' in rendered['scenes'][0]['narration']
