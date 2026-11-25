import io
import json
import math
import struct
import urllib.error
import wave
from pathlib import Path

import pytest

from healthvideo.tts.base import TTSRequest
from healthvideo.tts.voicestudio import (
    VoiceStudioError,
    VoiceStudioSettings,
    VoiceStudioTTS,
)


def wav_bytes(rate=24000):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b''.join(struct.pack('<h', int(8000 * math.sin(i / 10)))
                                 for i in range(rate // 10)))
    return stream.getvalue()


def settings(tmp_path):
    ref = tmp_path / 'reference.wav'
    ref.write_bytes(wav_bytes())
    return VoiceStudioSettings(ref_audio=ref, ref_text='Lời của file mẫu.')


def test_multipart_and_resample_and_separate_usage(tmp_path):
    calls = []

    def opener(request, *, timeout):
        calls.append((request, timeout))
        return io.BytesIO(b'{"status":"ok"}' if request.get_method() == 'GET' else wav_bytes())

    tts = VoiceStudioTTS(settings(tmp_path), opener=opener)
    output = tmp_path / 'out.wav'
    result = tts.synthesize(TTSRequest(text='Xin chào.', language='vi'), output)
    assert result.provider == 'voicestudio' and result.duration_ms == 100
    with wave.open(str(output)) as wav:
        assert (wav.getframerate(), wav.getnchannels()) == (48000, 1)
    assert calls[0][0].full_url.endswith('/health')
    request = calls[1][0]
    body = request.data.decode('utf-8', errors='replace')
    for key, value in {'text': 'Xin chào.', 'language': 'vi', 'ref_text': 'Lời của file mẫu.',
                       'speed': '1.15', 'effect_preset': 'warm', 'num_step': '32',
                       'guidance_scale': '2.5', 'pronounce': 'false', 'seed': '42'}.items():
        assert f'name="{key}"\r\n\r\n{value}\r\n' in body
    assert 'name="ref_audio"; filename="reference.wav"' in body
    assert 'profile_id' not in body
    usage = json.loads((tmp_path / 'voicestudio-usage.json').read_text())
    assert usage['provider'] == 'voicestudio' and usage['characters'] == len('Xin chào.')
    assert not (tmp_path / 'tts-usage.json').exists()


def test_server_off_is_bounded_and_vietnamese(tmp_path):
    calls = []

    def offline(request, *, timeout):
        calls.append(timeout)
        raise urllib.error.URLError('connection refused')

    tts = VoiceStudioTTS(settings(tmp_path), opener=offline, sleep=lambda _: None)
    with pytest.raises(VoiceStudioError, match='Voice Studio.*không.*kết nối'):
        tts.synthesize(TTSRequest(text='Thử.', language='vi'), tmp_path / 'out.wav')
    assert calls == [2, 2]


def test_reference_and_settings_are_bound_to_cache_identity(tmp_path):
    profile = settings(tmp_path)
    tts = VoiceStudioTTS(profile)
    identity = tts.cache_identity()
    assert VoiceStudioTTS(profile.model_copy(update={'seed': 43})).cache_identity() != identity
    profile.ref_audio.write_bytes(wav_bytes(48000))
    assert tts.cache_identity() != identity
    profile.ref_audio.unlink()
    with pytest.raises(VoiceStudioError, match='Thiếu file WAV mẫu'):
        tts.cache_identity()


def test_real_local_voicestudio(tmp_path):
    from healthvideo.tts.vibi import load_voice_profile

    profile = load_voice_profile().voicestudio
    assert profile is not None
    root = Path(__file__).resolve().parents[2]
    if not (root / profile.ref_audio).is_file():
        # The reference WAV is local data (cache/ is not in Git), absent in fresh worktrees.
        pytest.skip(f'Thiếu giọng mẫu {profile.ref_audio} trong checkout này')
    tts = VoiceStudioTTS(profile, root=root)
    try:
        tts.health()
    except VoiceStudioError:
        pytest.skip('Voice Studio local không chạy')
    result = tts.synthesize(TTSRequest(text='Bác sĩ nghe thử giọng đọc trên máy.', language='vi'),
                            tmp_path / 'real.wav')
    assert result.duration_ms > 0
    with wave.open(str(result.audio_file)) as wav:
        assert (wav.getframerate(), wav.getnchannels()) == (48000, 1)
