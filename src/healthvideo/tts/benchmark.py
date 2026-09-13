"""Offline benchmark records measurements, never voice-quality judgments."""

import re
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from healthvideo.storage.files import canonical_json_hash
from healthvideo.tts.audio_checks import AudioReport, inspect_wav
from healthvideo.tts.base import TTSProvider, TTSRequest, provider_identity


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    text: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.case_id) or not self.text.strip():
            raise ValueError("Benchmark case needs a safe ID and nonblank text")


@dataclass(frozen=True)
class BenchmarkRecord:
    case_id: str
    provider_identity: dict[str, str]
    ok: bool
    elapsed_ms: int
    audio: AudioReport | None
    error_type: str | None


def run_benchmark(
    cases: list[BenchmarkCase], providers: list[TTSProvider], output_dir: Path
) -> tuple[BenchmarkRecord, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[BenchmarkRecord] = []
    for case in cases:
        for provider in providers:
            started = perf_counter()
            identity = {"provider": "unavailable"}
            try:
                identity = provider_identity(provider)
                identity_hash = canonical_json_hash(identity)[:12]
                output = output_dir / f"{case.case_id}-{identity_hash}.wav"
                provider.synthesize(TTSRequest(text=case.text, language="vi"), output)
                audio = inspect_wav(
                    output, require_signal=getattr(provider, "require_signal", False)
                )
            except Exception as error:  # noqa: BLE001 - isolate each local provider
                records.append(
                    BenchmarkRecord(
                        case.case_id, identity, False,
                        round((perf_counter() - started) * 1000),
                        None, type(error).__name__,
                    )
                )
            else:
                records.append(
                    BenchmarkRecord(
                        case.case_id, identity, True,
                        round((perf_counter() - started) * 1000), audio, None,
                    )
                )
    return tuple(records)
