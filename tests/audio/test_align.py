import json
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from healthvideo.audio.align import align_lines, map_words, pronunciation_qa


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
