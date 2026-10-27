import io
import json
import subprocess
import urllib.error
import wave

import pytest

from healthvideo.tts.base import TTSRequest, provider_identity
from healthvideo.tts.elevenlabs import VoiceProfile, load_voice_profile
from healthvideo.tts.vibi import VibiError, VibiTTS
from healthvideo.workflows import factory_deps
from healthvideo.workflows.doctor import _vibi_check

PROFILE = VoiceProfile.model_validate({
    "provider": "vibi_minimax", "model_id": "speech-2.8-hd", "voice_id": "clone-1",
    "settings": {"speed": 1.0, "pitch": 0, "vol": 1.0}})


def _decode(argv, **kwargs):
    with wave.open(argv[-1], "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(b"\x01\x00" * 4800)
    return subprocess.CompletedProcess(argv, 0)


def _opener(statuses, audio_url="https://api.vibi.pro/audio/t1.mp3", fail_first=None):
    calls = []

    def opener(request, *, timeout):
        calls.append(request)
        if fail_first and len(calls) == 1:
            raise urllib.error.HTTPError(request.full_url, fail_first, "busy", {}, None)
        if request.get_method() == "POST":
            return io.BytesIO(b'{"id": "t1"}')
        if "/v1/history/" in request.full_url:
            status = statuses.pop(0)
            return io.BytesIO(json.dumps({"status": status, "result": {"audio_url": audio_url}}).encode())
        return io.BytesIO(b"mp3")
    return opener, calls


def _tts(opener):
    return VibiTTS(PROFILE, api_key="secret-key", opener=opener, runner=_decode, sleep=lambda s: None)


def test_submits_polls_and_downloads(tmp_path):
    opener, calls = _opener(["processing", "completed"])
    result = _tts(opener).synthesize(TTSRequest(text="[sarcastic] Gút  đau?", language="vi"), tmp_path / "l.wav")
    body = json.loads(calls[0].data)
    assert calls[0].full_url == "https://api.vibi.pro/v1/text-to-speech/clone-1"
    assert body == {"text": "Gút đau?", "model_id": "speech-2.8-hd", "provider": "minimax",
                    "language_code": "Vietnamese", "voice_settings": {"speed": 1.0, "pitch": 0, "vol": 1.0}}
    assert all(c.get_header("User-agent") and c.get_header("Xi-api-key") == "secret-key" for c in calls)
    assert calls[-1].full_url == "https://api.vibi.pro/audio/t1.mp3"
    assert result.provider == "vibi_minimax" and result.duration_ms == 100
    assert provider_identity(_tts(opener))["model_id"] == "speech-2.8-hd"


def test_failed_task_error_hides_key(tmp_path):
    opener, _ = _opener(["failed"])
    with pytest.raises(VibiError) as error:
        _tts(opener).synthesize(TTSRequest(text="Gút", language="vi"), tmp_path / "l.wav")
    assert "secret-key" not in str(error.value)


def test_retries_transient_error(tmp_path):
    opener, calls = _opener(["completed"], fail_first=429)
    _tts(opener).synthesize(TTSRequest(text="Gút", language="vi"), tmp_path / "l.wav")
    assert len(calls) == 4


def test_rejects_foreign_audio_host_and_unknown_tag(tmp_path):
    opener, calls = _opener(["completed"], audio_url="https://evil.example/a.mp3")
    with pytest.raises(VibiError, match="unexpected audio location"):
        _tts(opener).synthesize(TTSRequest(text="Gút", language="vi"), tmp_path / "l.wav")
    assert not any("evil" in c.full_url for c in calls)
    with pytest.raises(ValueError, match="unsupported audio tag"):
        _tts(opener).synthesize(TTSRequest(text="[shouts] Gút", language="vi"), tmp_path / "l.wav")
    with pytest.raises(ValueError, match="speed"):
        _tts(opener).synthesize(TTSRequest(text="Gút", language="vi", speed=2.5), tmp_path / "l.wav")


@pytest.mark.parametrize("mode", ["silent", "unreadable"])
def test_silent_or_unreadable_decoded_audio_is_retryable_vibi_error(tmp_path, mode):
    opener, _ = _opener(["completed"])

    def bad_decode(argv, **kwargs):
        out = argv[-1]
        if mode == "unreadable":
            with open(out, "wb") as stream:
                stream.write(b"not-a-wav")
        else:
            with wave.open(out, "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(48000)
                audio.writeframes(b"\x00\x00" * 4800)
        return subprocess.CompletedProcess(argv, 0)

    tts = VibiTTS(PROFILE, api_key="secret-key", opener=opener, runner=bad_decode, sleep=lambda s: None)
    output = tmp_path / "bad.wav"
    with pytest.raises(VibiError) as caught:
        tts.synthesize(TTSRequest(text="Gút", language="vi"), output)
    assert not isinstance(caught.value, ValueError)
    assert "secret-key" not in str(caught.value)
    assert not output.exists()


def test_repo_profile_is_the_cloned_voice():
    profile = load_voice_profile()
    assert profile.provider == "vibi_minimax" and profile.settings.vol == 1.0


def test_auto_selects_vibi_or_falls_back(monkeypatch):
    monkeypatch.setenv("VIBI_API_KEY", "key")
    assert provider_identity(factory_deps.build_tts_provider())["provider"] == "vibi_minimax"
    monkeypatch.delenv("VIBI_API_KEY")
    sentinel = object()
    monkeypatch.setattr(factory_deps, "_build_vieneu_tts", lambda **kwargs: sentinel)
    with pytest.warns(RuntimeWarning, match="using VieNeu"):
        assert factory_deps.build_tts_provider() is sentinel
    with pytest.raises(ValueError, match="VIBI_API_KEY"):
        factory_deps.build_tts_provider(tts="vibi")


def test_doctor_reports_credit(monkeypatch):
    monkeypatch.setenv("VIBI_API_KEY", "key")
    monkeypatch.setattr("healthvideo.tts.vibi.account", lambda **kwargs: {"credit_balance": 127368})
    assert _vibi_check().detected == "127368 credits remaining"
