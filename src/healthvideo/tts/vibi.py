"""vibi.pro MiniMax adapter for the doctor's cloned voice. Credentials never enter identities or errors."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from healthvideo.tts.audio_checks import inspect_wav
from healthvideo.tts.base import TTSRequest, TTSResult
from healthvideo.tts.elevenlabs import ElevenLabsTTS, VoiceProfile

API_ROOT = "https://api.vibi.pro"
# Cloudflare rejects requests without a User-Agent (error 1010).
USER_AGENT = "healthvideo/1.0"


class VibiError(RuntimeError):
    """A deliberately sanitized provider error."""


def vibi_request(
    url: str, *, api_key: str, payload: dict[str, Any] | None = None,
    opener=None, timeout: float = 60, retries: int = 3, sleep=time.sleep,
) -> bytes:
    """Retry only transient HTTP responses; never echo transport exception contents."""
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(
        url if url.startswith("http") else API_ROOT + url,
        data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
        headers={"xi-api-key": api_key, "User-Agent": USER_AGENT, "Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    for attempt in range(retries + 1):
        try:
            with opener(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
            if (status == 429 or 500 <= status < 600) and attempt < retries:
                sleep(min(2**attempt, 8))
                continue
            raise VibiError(f"vibi HTTP {status}; check credit, voice and API key.") from None
        except (OSError, ValueError):
            raise VibiError("vibi connection failed; check network and API configuration.") from None
    raise AssertionError("unreachable")


def account(*, api_key: str, opener=None) -> dict[str, Any]:
    try:
        return json.loads(vibi_request("/v1/auth/me", api_key=api_key, opener=opener))
    except (ValueError, TypeError):
        raise VibiError("vibi returned invalid account information.") from None


class VibiTTS(ElevenLabsTTS):
    """Async task: submit, poll history until completed, download the mp3."""

    provider_name = "vibi_minimax"

    def __init__(
        self, profile: VoiceProfile, *, api_key: str | None = None, opener=None,
        runner=subprocess.run, timeout: float = 60, retries: int = 3,
        sleep=time.sleep, usage_path: Path | None = None, poll_seconds: float = 2,
        max_wait_seconds: float = 180,
    ) -> None:
        self.profile = profile
        self.model_id = profile.model_id or "speech-2.8-hd"
        self._api_key = api_key if api_key is not None else os.environ.get("VIBI_API_KEY", "")
        if not self._api_key.strip():
            raise VibiError("Set VIBI_API_KEY in the local .env file.")
        self.opener, self.runner = opener, runner
        self.timeout, self.retries, self.sleep = timeout, retries, sleep
        self.usage_path = usage_path
        self.poll_seconds, self.max_wait_seconds = poll_seconds, max_wait_seconds

    def _call(self, url: str, payload: dict[str, Any] | None = None) -> bytes:
        return vibi_request(url, api_key=self._api_key, payload=payload, opener=self.opener,
                            timeout=self.timeout, retries=self.retries, sleep=self.sleep)

    def _json(self, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return json.loads(self._call(url, payload))
        except (ValueError, TypeError):
            raise VibiError("vibi returned an invalid response.") from None

    def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
        settings = self.profile.settings.model_dump()
        settings["speed"] = settings["speed"] * request.speed
        if not 0.5 <= settings["speed"] <= 2.0:
            raise ValueError("MiniMax combined speed must be between 0.5 and 2.0")
        tags = re.findall(r"\[([^\[\]]+)\]", request.text)
        if any(tag not in self.profile.allowed_tags for tag in tags):
            raise ValueError("Delivery contains an unsupported audio tag")
        # MiniMax would read ElevenLabs-style tags aloud, so delivery tags are dropped.
        text = re.sub(r"\s+", " ", re.sub(r"\[[^\[\]]+\]", " ", request.text)).strip()
        task = self._json(f"/v1/text-to-speech/{self.profile.voice_id}", {
            "text": text, "model_id": self.model_id, "provider": "minimax",
            "language_code": "Vietnamese", "voice_settings": settings})
        waited = 0.0
        while True:
            info = self._json(f"/v1/history/{task.get('id')}")
            if info.get("status") == "completed":
                break
            if info.get("status") == "failed":
                raise VibiError("vibi synthesis failed; check the voice and text.")
            if waited >= self.max_wait_seconds:
                raise VibiError("vibi synthesis timed out.")
            self.sleep(self.poll_seconds)
            waited += self.poll_seconds
        audio_url = (info.get("result") or {}).get("audio_url")
        # The API key is sent with the download, so only vibi's own host is accepted.
        if not isinstance(audio_url, str) or not audio_url.startswith(API_ROOT + "/"):
            raise VibiError("vibi returned an unexpected audio location.")
        audio = self._call(audio_url)
        self._record_usage(text, output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".vibi-", dir=output.parent) as temporary:
            source = Path(temporary) / "speech.mp3"
            source.write_bytes(audio)
            try:
                result = self.runner(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                     "-i", str(source), "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(output)],
                    capture_output=True, check=False,
                )
            except OSError:
                raise VibiError("ffmpeg is required to decode vibi audio.") from None
            if result.returncode:
                raise VibiError("ffmpeg could not decode vibi audio.")
        report = inspect_wav(output, require_signal=self.require_signal)
        return TTSResult(provider=self.provider_name, audio_file=output, duration_ms=report.duration_ms)
