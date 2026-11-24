import shutil
import wave

import pytest

from healthvideo.audio.align import _expand_asr_words, map_words
from healthvideo.audio.tts_qa import asr_equivalents, check_line, line_qa


def _alignment(text, heard):
    return {'L1': map_words(text, [{'word': w, 'start': i, 'end': i + 1, 'prob': .9}
                                  for i, w in enumerate(heard.split())], duration=30)}


def test_letter_bo_blocks_but_equivalent_acronym_passes():
    assert line_qa(_alignment('viêm gan bê', 'viêm gan bơ'), terms=['bê'])['blocked']
    assert not line_qa(_alignment('gan khỏe rồi', 'gan khoẻ rồi'))['blocked']
    assert not line_qa(_alignment('nước sôi', 'nước xôi'))['blocked']


def test_single_letter_itn_matches_vietnamese_letter_name():
    assert asr_equivalents({'B': 'bê', 'viêm gan B': 'viêm gan bê'})['B'] == 'bê'
    report = line_qa(_alignment('viêm gan bê', 'viêm gan B'), terms=['viêm gan bê'])
    assert not report['blocked'] and not report['flags']


@pytest.mark.parametrize(('text', 'heard'), [
    ('ây eo ti', 'AOT'), ('ai en a', 'INA'), ('xi li ma rin', 'Silly Marine'),
    ('em a ét eo đê', 'Mazda'), ('em a ét eo đê', 'MAST.'),
    ('hát bê ét a dê', 'H, B, S,'), ('hát bê ét a dê', 'HBiSAC'), ('đi', 'D'),
])
def test_latin_itn_at_term_is_unverifiable_not_blocked(text, heard):
    report = line_qa(_alignment(text, heard), terms=[text])
    assert not report['blocked']
    assert report['flags'] and all(f['reason'] == 'asr_unverifiable' for f in report['flags'])


def test_latin_source_survives_vietnamese_expansion_and_alignment():
    raw = [{'word': 'D', 'start': 0, 'end': 1, 'prob': .9}]
    expanded = _expand_asr_words(raw, asr_equivalents({}), preserve_asr_source=True)
    words = map_words('đi', expanded, duration=1)
    assert words[0]['heard'] == 'đê' and words[0]['asr_source'] == 'D'
    report = line_qa({'L1': words}, terms=['đi'])
    assert not report['blocked']
    assert report['flags'][0]['reason'] == 'asr_unverifiable'
    assert report['flags'][0]['heard'] == 'D'
    # Actual accented Vietnamese is still evidence of a different pronunciation.
    assert line_qa(_alignment('đi', 'đê'), terms=['đi'])['blocked']


def test_missing_phrase_and_low_match_block_single_word_warns():
    assert line_qa(_alignment('gan vẫn hoạt động bình thường', 'gan bình thường'))['blocked']
    assert not line_qa(_alignment('gan vẫn hoạt động bình thường', 'gan đang hoạt động bình thường'))['blocked']
    assert line_qa(_alignment('gan vẫn khỏe', 'gan vẫn rất là khỏe'))['blocked']
    assert not line_qa(_alignment('gan vẫn khỏe', 'gan vẫn rất khỏe'))['blocked']
    assert line_qa(_alignment('gan vẫn khỏe', 'tim đã yếu'))['blocked']


def test_retry_once_and_cache_success_or_failure(tmp_path):
    wav = tmp_path / 'source.wav'
    with wave.open(str(wav), 'wb') as f:
        f.setparams((1, 2, 16000, 0, 'NONE', 'none'))
        f.writeframes(b'\x01\x00' * 16000)
    calls = []

    def synth(output, force):
        calls.append(force)
        shutil.copyfile(wav, output)

    def aligner(wavs, scripts, **kwargs):
        return _alignment(scripts['L1'], 'viêm gan bơ')

    args = {'line_id': 'L1', 'text': 'viêm gan bê', 'terms': ['bê'], 'asr_lexicon': {},
                'cache_dir': tmp_path / 'cache', 'request_key': 'key', 'synthesize': synth, 'aligner': aligner}
    report, path = check_line(**args)
    assert report['blocked'] and calls == [False, True]
    assert path.is_file() and path.with_suffix('.qa.json').is_file()
    check_line(**args)
    assert calls == [False, True]
    args['accepted_hashes'] = {report['wav_sha256']}
    assert not check_line(**args)[0]['blocked']


def test_retry_correct_then_no_more_whisper(tmp_path):
    calls = []

    def synth(output, force):
        output.write_bytes(b'correct' if force else b'wrong')

    def aligner(wavs, scripts, **kwargs):
        calls.append(1)
        return _alignment(scripts['L1'], 'viêm gan bơ' if len(calls) == 1 else 'viêm gan bê')

    args = {'line_id': 'L1', 'text': 'viêm gan bê', 'terms': ['bê'], 'asr_lexicon': {},
                'cache_dir': tmp_path, 'request_key': 'key', 'synthesize': synth, 'aligner': aligner}
    assert not check_line(**args)[0]['blocked']
    check_line(**args)
    assert len(calls) == 2
