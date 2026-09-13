"""Offline benchmark records measurements, never voice-quality judgments."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from healthvideo.storage.files import canonical_json_hash, read_yaml
from healthvideo.tts.audio_checks import AudioReport, inspect_wav
from healthvideo.tts.base import TTSProvider, TTSRequest, provider_identity


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    text: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.case_id) or not self.text.strip():
            raise ValueError("Benchmark case needs a safe ID and nonblank text")


def load_benchmark_cases(path: Path) -> list[BenchmarkCase]:
    raw = read_yaml(path).get("cases")
    if not isinstance(raw, list) or not raw:
        raise ValueError("Benchmark cases file needs a nonempty `cases` list")
    cases = [BenchmarkCase(case_id=str(item["id"]), text=str(item["text"])) for item in raw]
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Benchmark cases contain duplicate ids")
    return cases


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


@dataclass(frozen=True)
class BenchmarkThresholds:
    """Objective gates only; pronunciation and naturalness need ASR and a doctor."""

    max_realtime_factor: float = 1.0
    min_words_per_second: float = 1.5
    max_words_per_second: float = 5.0


@dataclass(frozen=True)
class CaseVerdict:
    case_id: str
    provider_identity: dict[str, str]
    passed: bool
    failures: tuple[str, ...]
    realtime_factor: float | None
    words_per_second: float | None


def evaluate_benchmark(
    records: Sequence[BenchmarkRecord],
    cases: Sequence[BenchmarkCase],
    thresholds: BenchmarkThresholds | None = None,
) -> tuple[CaseVerdict, ...]:
    thresholds = thresholds or BenchmarkThresholds()
    word_counts = {case.case_id: len(case.text.split()) for case in cases}
    verdicts: list[CaseVerdict] = []
    for record in records:
        failures: list[str] = []
        rtf = wps = None
        if not record.ok or record.audio is None:
            failures.append(f"synthesis_failed:{record.error_type or 'unknown'}")
        else:
            rtf = round(record.elapsed_ms / record.audio.duration_ms, 3)
            wps = round(word_counts[record.case_id] * 1000 / record.audio.duration_ms, 3)
            if not record.audio.has_signal:
                failures.append("no_signal")
            if rtf > thresholds.max_realtime_factor:
                failures.append("realtime_factor")
            if wps < thresholds.min_words_per_second:
                failures.append("speech_rate_low")
            if wps > thresholds.max_words_per_second:
                failures.append("speech_rate_high")
        verdicts.append(
            CaseVerdict(
                record.case_id, dict(record.provider_identity), not failures,
                tuple(failures), rtf, wps,
            )
        )
    return tuple(verdicts)
