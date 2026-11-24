"""Local Voice Studio adapter, exclusively for draft listening and timing."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from healthvideo.tts.audio_checks import inspect_wav
from healthvideo.tts.base import TTSRequest, TTSResult


class VoiceStudioSettings(BaseModel, frozen=True):
    model_config = ConfigDict(extra='forbid')
    url: str = 'http://127.0.0.1:3900'
    role: Literal['draft'] = 'draft'
    language: Literal['vi'] = 'vi'
    ref_audio: Path
    ref_text: str = Field(min_length=1)
    speed: float = Field(default=1.15, gt=0)
    effect_preset: str = 'warm'
    num_step: int = Field(default=32, gt=0)
    guidance_scale: float = 2.5
    pronounce: Literal[False] = False
    seed: int = 42

    @field_validator('url')
    @classmethod
    def local_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {'', '/'}):
            raise ValueError('Voice Studio cần URL HTTP trên máy local.')
        return value.rstrip('/')


class VoiceStudioError(RuntimeError):
    """An actionable local-provider error in Vietnamese."""


class VoiceStudioTTS:
    provider_name = 'voicestudio'
    require_signal = True

    def __init__(self, profile: VoiceStudioSettings, *, root: Path | None = None,
                 opener=None, runner=subprocess.run, timeout: float = 180,
                 retries: int = 1, sleep=time.sleep, usage_path: Path | None = None):
        self.profile = profile
        self.root = root or Path(__file__).resolve().parents[3]
        self.ref_audio = self.root / profile.ref_audio
        self.opener = opener or urllib.request.urlopen
        self.runner, self.timeout = runner, timeout
        self.retries, self.sleep, self.usage_path = retries, sleep, usage_path

    def cache_identity(self) -> dict[str, str]:
        settings = self.profile.model_dump(mode='json')
        try:
            settings['ref_sha256'] = hashlib.sha256(self.ref_audio.read_bytes()).hexdigest()
        except OSError:
            raise VoiceStudioError('Thiếu file WAV mẫu Voice Studio: ' + str(self.ref_audio)) from None
        digest = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
        return {'provider': self.provider_name, 'runtime_id': 'local-' + digest[:32]}

    def set_usage_path(self, path: Path) -> None:
        # Never share the paid provider's usage counter, even when wrapped.
        self.usage_path = path.with_name('voicestudio-usage.json')

    def _call(self, request: urllib.request.Request, timeout: float) -> bytes:
        for attempt in range(self.retries + 1):
            try:
                with self.opener(request, timeout=timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                status = error.code
                error.close()
                raise VoiceStudioError(f'Voice Studio trả lỗi HTTP {status}; kiểm tra server trên máy.') from None
            except (OSError, TimeoutError, urllib.error.URLError):
                if attempt < self.retries:
                    self.sleep(0.25)
                    continue
                raise VoiceStudioError(
                    'Voice Studio không thể kết nối hoặc đã quá thời gian chờ; '
                    'hãy bật server trên máy tại ' + self.profile.url + '.'
                ) from None
        raise AssertionError('unreachable')

    def health(self) -> None:
        self._call(urllib.request.Request(self.profile.url + '/health'), 2)

    def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
        if request.language != 'vi':
            raise VoiceStudioError('Voice Studio chỉ hỗ trợ bản nháp tiếng Việt trong cấu hình này.')
        self.health()
        try:
            reference = self.ref_audio.read_bytes()
        except OSError:
            raise VoiceStudioError('Thiếu file WAV mẫu Voice Studio: ' + str(self.ref_audio)) from None
        fields = self.profile.model_dump(exclude={'url', 'role', 'ref_audio'})
        fields['text'] = request.text
        fields['speed'] *= request.speed
        boundary = 'pyh-' + uuid.uuid4().hex
        body = bytearray()
        for key, value in fields.items():
            value = str(value).lower() if isinstance(value, bool) else str(value)
            body.extend((f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"'
                         f'\r\n\r\n{value}\r\n').encode())
        body.extend((f'--{boundary}\r\nContent-Disposition: form-data; name="ref_audio"; '
                     f'filename="reference.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode())
        body.extend(reference)
        body.extend(f'\r\n--{boundary}--\r\n'.encode())
        audio = self._call(urllib.request.Request(
            self.profile.url + '/generate', data=bytes(body), method='POST',
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
        ), self.timeout)
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='.voicestudio-', dir=output.parent) as temporary:
            source, target = Path(temporary) / 'raw.wav', Path(temporary) / 'normalized.wav'
            source.write_bytes(audio)
            try:
                inspect_wav(source, require_signal=True)
                result = self.runner(
                    ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                     '-i', str(source), '-ar', '48000', '-ac', '1', '-c:a', 'pcm_s16le', str(target)],
                    capture_output=True, check=False, timeout=120,
                )
                if result.returncode:
                    raise ValueError('ffmpeg không chuyển được WAV')
                report = inspect_wav(target, require_signal=True)
                if report.sample_rate != 48000 or report.channels != 1:
                    raise ValueError('WAV phải là 48 kHz mono')
            except (ValueError, OSError, subprocess.TimeoutExpired):
                raise VoiceStudioError('Voice Studio trả âm thanh lỗi hoặc ffmpeg không chuyển được WAV.') from None
            os.replace(target, output)
        self._record_usage(request.text, output)
        return TTSResult(provider=self.provider_name, audio_file=output, duration_ms=report.duration_ms)

    def _record_usage(self, text: str, output: Path) -> None:
        path = (self.usage_path or output.parent / 'voicestudio-usage.json').with_name('voicestudio-usage.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
            'provider': self.provider_name, 'characters': 0, 'requests': [],
        }
        data['characters'] += len(text)
        data['requests'].append({'characters': len(text), **self.cache_identity(),
                                 'text_sha256': hashlib.sha256(text.encode()).hexdigest()})
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, path)
