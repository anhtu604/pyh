import io
import json
import subprocess
import urllib.error
import wave

import pytest

from healthvideo.tts.base import TTSRequest, provider_identity
from healthvideo.tts.elevenlabs import (
    ElevenLabsError,
    ElevenLabsTTS,
    VoiceProfile,
    api_request,
)
from healthvideo.tts.normalize import NormalizedTTS
from healthvideo.workflows import factory_deps
from healthvideo.workflows.doctor import _elevenlabs_check


def _decode(argv, **kwargs):
    with wave.open(argv[-1], "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(b"\x01\x00" * 4800)
    return subprocess.CompletedProcess(argv, 0)


def test_elevenlabs_request_shape(tmp_path):
    captured = []

    def opener(request, *, timeout):
        captured.append((request, timeout))
        return io.BytesIO(b"mp3")

    provider = ElevenLabsTTS(VoiceProfile(voice_id="test-voice"), api_key="test-key", opener=opener, runner=_decode)
    result = provider.synthesize(TTSRequest(text="[curious] Gút?", language="vi"), tmp_path / "line.wav")
    request, timeout = captured[0]
    assert request.full_url.endswith("/v1/text-to-speech/test-voice?output_format=mp3_44100_128")
    assert request.get_header("Xi-api-key") == "test-key"
    assert json.loads(request.data) == {
        "text": "[curious] Gút?", "model_id": "eleven_v3", "language_code": "vi",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.3, "speed": 1.0},
    }
    assert timeout == 60
    assert result.duration_ms == 100
    with wave.open(str(result.audio_file)) as audio:
        assert audio.getframerate() == 48000


@pytest.mark.parametrize("status", [401, 429, 503])
def test_elevenlabs_key_never_logged(status, caplog, capsys):
    secret = "TOP-SECRET-KEY"

    def opener(request, **kwargs):
        raise urllib.error.HTTPError(request.full_url, status, secret, {}, io.BytesIO(secret.encode()))

    with pytest.raises(ElevenLabsError) as caught:
        api_request("/v1/user/subscription", api_key=secret, opener=opener, retries=0)
    output = capsys.readouterr()
    assert secret not in str(caught.value) + caplog.text + output.out + output.err
    assert caught.value.__suppress_context__


def test_elevenlabs_transient_retry_backoff():
    sleeps, calls = [], []

    def opener(request, **kwargs):
        calls.append(request)
        if len(calls) < 3:
            raise urllib.error.HTTPError(request.full_url, 429, "quota", {}, None)
        return io.BytesIO(b"ok")

    assert api_request("/test", api_key="key", opener=opener, sleep=sleeps.append) == b"ok"
    assert sleeps == [1, 2]


def test_tts_usage_recorded(tmp_path):
    usage = tmp_path / "audio" / "tts-usage.json"
    provider = ElevenLabsTTS(VoiceProfile(voice_id="voice"), api_key="key", opener=lambda *a, **k: io.BytesIO(b"mp3"), runner=_decode)
    normalized = NormalizedTTS(provider)
    normalized.set_usage_path(usage)
    for index in range(2):
        provider.synthesize(TTSRequest(text="Gút", language="vi"), tmp_path / f"{index}.wav")
    data = json.loads(usage.read_text(encoding="utf-8"))
    assert data["characters"] == 6
    assert len(data["requests"]) == 2
    assert data["requests"][0]["model_id"] == "eleven_v3"


def test_provider_identity_changes_with_settings():
    first = ElevenLabsTTS(VoiceProfile(voice_id="voice"), api_key="key")
    second = ElevenLabsTTS(VoiceProfile(voice_id="voice", settings={"style": 0.7}), api_key="key")
    assert provider_identity(first) != provider_identity(second)
    assert provider_identity(first)["model_id"] == "eleven_v3"


def test_provider_falls_back_to_vieneu_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    selected = []
    sentinel = object()
    monkeypatch.setattr(factory_deps, "_build_vieneu_tts", lambda **kwargs: sentinel)
    monkeypatch.setattr(factory_deps, "produce_project", lambda project, provider, *a, **k: selected.append(provider))
    with pytest.warns(RuntimeWarning, match="using VieNeu"):
        producer = factory_deps.build_default_producer(tts="auto")
    producer(tmp_path)
    assert selected == [sentinel]


def test_provider_auto_selects_elevenlabs(monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "key")
    selected = []
    monkeypatch.setattr(factory_deps, "produce_project", lambda project, provider, *a, **k: selected.append(provider))
    factory_deps.build_default_producer()(tmp_path)
    assert selected[0].cache_identity()["model_id"] == "eleven_v3"


def test_shared_provider_builder_defaults_to_auto(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "key")
    provider = factory_deps.build_tts_provider()
    assert provider_identity(provider)["model_id"] == "eleven_v3"
    assert provider_identity(factory_deps.build_tts_provider(tts="silent"))["provider"] == "silent"


def test_doctor_reports_subscription_remaining(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "key")
    monkeypatch.setattr("healthvideo.tts.elevenlabs.subscription", lambda **kwargs: {"character_count": 123, "character_limit": 1000})
    check = _elevenlabs_check()
    assert check.ok and check.required == "recommended"
    assert check.detected == "877 characters remaining"
