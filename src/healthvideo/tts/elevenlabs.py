"""ElevenLabs v3 REST adapter. Credentials never enter public identities or errors."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.storage.files import read_yaml
from healthvideo.tts.audio_checks import inspect_wav
from healthvideo.tts.base import TTSRequest, TTSResult

API_ROOT = "https://api.elevenlabs.io"
VOICE_PROFILE_PATH = Path(__file__).resolve().parents[3] / "profiles" / "voice.yaml"


class VoiceSettings(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    stability: float = Field(default=0.5, ge=0, le=1)
    similarity_boost: float = Field(default=0.75, ge=0, le=1)
    style: float = Field(default=0.3, ge=0, le=1)
    speed: float = Field(default=1.0, ge=0.7, le=1.2)


class MiniMaxSettings(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    pitch: int = Field(default=0, ge=-12, le=12)
    vol: float = Field(default=1.0, ge=0.01, le=10)


class VoiceProfile(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["elevenlabs", "vibi_minimax"] = "elevenlabs"
    model_id: str | None = None
    voice_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    settings: VoiceSettings | MiniMaxSettings = Field(default_factory=VoiceSettings)
    allowed_tags: tuple[str, ...] = (
        "sarcastic", "curious", "excited", "chuckles", "sighs", "whispers", "pause",
    )

    @model_validator(mode="before")
    @classmethod
    def _settings_for_provider(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("settings"), dict):
            model = MiniMaxSettings if data.get("provider") == "vibi_minimax" else VoiceSettings
            data = {**data, "settings": model.model_validate(data["settings"])}
        return data


def load_voice_profile(path: Path = VOICE_PROFILE_PATH) -> VoiceProfile:
    return VoiceProfile.model_validate(read_yaml(path))


class ElevenLabsError(RuntimeError):
    """A deliberately sanitized provider error."""


def api_request(
    path: str, *, api_key: str, payload: dict[str, Any] | None = None,
    opener=None, timeout: float = 60, retries: int = 3, sleep=time.sleep,
) -> bytes:
    """Retry only transient HTTP responses; never echo transport exception contents."""
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(
        API_ROOT + path,
        data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
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
            raise ElevenLabsError(f"ElevenLabs HTTP {status}; check quota, voice and API permissions.") from None
        except (OSError, ValueError):
            raise ElevenLabsError("ElevenLabs connection failed; check network and API configuration.") from None
    raise AssertionError("unreachable")


def subscription(*, api_key: str, opener=None) -> dict[str, Any]:
    try:
        return json.loads(api_request("/v1/user/subscription", api_key=api_key, opener=opener))
    except (ValueError, TypeError):
        raise ElevenLabsError("ElevenLabs returned invalid subscription information.") from None


class ElevenLabsTTS:
    provider_name = "elevenlabs"
    model_id = "eleven_v3"
    require_signal = True

    def __init__(
        self, profile: VoiceProfile, *, api_key: str | None = None, opener=None,
        runner=subprocess.run, timeout: float = 60, retries: int = 3,
        sleep=time.sleep, usage_path: Path | None = None,
    ) -> None:
        self.profile = profile
        self._api_key = api_key if api_key is not None else os.environ.get("ELEVENLABS_API_KEY", "")
        if not self._api_key.strip():
            raise ElevenLabsError("Set ELEVENLABS_API_KEY in the local .env file.")
        self.opener, self.runner = opener, runner
        self.timeout, self.retries, self.sleep = timeout, retries, sleep
        self.usage_path = usage_path

    def cache_identity(self) -> dict[str, str]:
        settings = json.dumps(self.profile.settings.model_dump(), sort_keys=True)
        return {"provider": self.provider_name, "model_id": self.model_id,
                "voice_id": self.profile.voice_id,
                "runtime_id": "rest-" + hashlib.sha256(settings.encode()).hexdigest()[:24]}

    def set_usage_path(self, path: Path) -> None:
        self.usage_path = path

    def _record_usage(self, text: str, output: Path) -> None:
        parent = output.parent
        if parent.name.startswith(".loudnorm-"):
            parent = parent.parent
        path = self.usage_path or parent / "tts-usage.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
            "provider": self.provider_name, "characters": 0, "requests": [],
            "count_basis": "submitted Unicode characters; consult subscription for billed credits",
        }
        data["characters"] += len(text)
        data["requests"].append({"characters": len(text), **self.cache_identity(),
                                 "text_sha256": hashlib.sha256(text.encode()).hexdigest()})
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
        settings = self.profile.settings.model_dump()
        settings["speed"] = settings["speed"] * request.speed
        if not 0.7 <= settings["speed"] <= 1.2:
            raise ValueError("ElevenLabs combined speed must be between 0.7 and 1.2")
        tags = re.findall(r"\[([^\[\]]+)\]", request.text)
        if any(tag not in self.profile.allowed_tags for tag in tags):
            raise ValueError("Delivery contains an unsupported ElevenLabs audio tag")
        audio = api_request(
            f"/v1/text-to-speech/{self.profile.voice_id}?output_format=mp3_44100_128",
            api_key=self._api_key,
            payload={"text": request.text, "model_id": self.model_id,
                     "language_code": "vi", "voice_settings": settings},
            opener=self.opener, timeout=self.timeout, retries=self.retries, sleep=self.sleep,
        )
        self._record_usage(request.text, output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".elevenlabs-", dir=output.parent) as temporary:
            source = Path(temporary) / "speech.mp3"
            source.write_bytes(audio)
            try:
                result = self.runner(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                     "-i", str(source), "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(output)],
                    capture_output=True, check=False,
                )
            except OSError:
                raise ElevenLabsError("ffmpeg is required to decode ElevenLabs audio.") from None
            if result.returncode:
                raise ElevenLabsError("ffmpeg could not decode ElevenLabs audio.")
        report = inspect_wav(output, require_signal=self.require_signal)
        return TTSResult(provider=self.provider_name, audio_file=output, duration_ms=report.duration_ms)
