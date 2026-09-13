from pathlib import Path

from healthvideo.tts.benchmark import BenchmarkCase, run_benchmark
from healthvideo.tts.silent import SilentTTS


def test_benchmark_records_independent_provider_results_without_ranking(tmp_path: Path) -> None:
    class FailingTTS:
        provider_name = "failing"

        def synthesize(self, request, output):
            raise RuntimeError("private runtime details")

    records = run_benchmark(
        [BenchmarkCase(case_id="case-1", text="Xin chào")],
        [FailingTTS(), SilentTTS()],
        tmp_path,
    )
    assert len(records) == 2
    assert records[0].ok is False
    assert records[1].ok is True
    assert records[1].audio is not None
    assert "private runtime details" not in str(records)
    assert "rank" not in str(records)


def test_invalid_provider_identity_does_not_abort_next_provider(tmp_path: Path) -> None:
    class InvalidIdentity:
        provider_name = "bad"

        def cache_identity(self):
            raise ValueError("private config")

        def synthesize(self, request, output):
            raise AssertionError("must not synthesize")

    records = run_benchmark(
        [BenchmarkCase(case_id="case-1", text="Xin chào")],
        [InvalidIdentity(), SilentTTS()], tmp_path,
    )
    assert len(records) == 2
    assert not records[0].ok
    assert records[1].ok
    assert "private config" not in str(records)


def test_evaluate_benchmark_applies_only_objective_thresholds(tmp_path: Path) -> None:
    from healthvideo.tts.audio_checks import AudioReport
    from healthvideo.tts.benchmark import (
        BenchmarkRecord,
        BenchmarkThresholds,
        evaluate_benchmark,
    )

    cases = [BenchmarkCase(case_id="ten-words", text="một hai ba bốn năm sáu bảy tám chín mười")]
    identity = {"provider": "command", "model_id": "m", "voice_id": "v", "runtime_id": "r"}
    good = AudioReport(4000, 48_000, 1, 2, True)  # 2.5 words/s
    slow_rtf = BenchmarkRecord("ten-words", identity, True, 9000, good, None)
    too_fast = BenchmarkRecord(
        "ten-words", identity, True, 1000, AudioReport(1000, 48_000, 1, 2, True), None
    )
    failed = BenchmarkRecord("ten-words", identity, False, 10, None, "RuntimeError")
    ok = BenchmarkRecord("ten-words", identity, True, 2000, good, None)

    verdicts = evaluate_benchmark(
        [slow_rtf, too_fast, failed, ok], cases, BenchmarkThresholds(max_realtime_factor=1.0)
    )
    assert [v.passed for v in verdicts] == [False, False, False, True]
    assert verdicts[0].failures == ("realtime_factor",)
    assert verdicts[0].realtime_factor == 2.25
    assert verdicts[1].failures == ("speech_rate_high",)
    assert verdicts[2].failures == ("synthesis_failed:RuntimeError",)
    assert verdicts[3].words_per_second == 2.5
    assert "quality" not in str(verdicts) and "rank" not in str(verdicts)


def test_load_benchmark_cases_rejects_duplicates(tmp_path: Path) -> None:
    from healthvideo.tts.benchmark import load_benchmark_cases

    path = tmp_path / "cases.yaml"
    path.write_text(
        "cases:\n  - id: a\n    text: Xin chào\n  - id: a\n    text: Lại chào\n",
        encoding="utf-8",
    )
    import pytest

    with pytest.raises(ValueError, match="duplicate"):
        load_benchmark_cases(path)
    path.write_text("cases:\n  - id: a\n    text: Xin chào\n", encoding="utf-8")
    assert load_benchmark_cases(path) == [BenchmarkCase("a", "Xin chào")]


def test_benchmark_records_asr_transcript_and_wer_gate(tmp_path: Path) -> None:
    from healthvideo.tts.benchmark import BenchmarkThresholds, evaluate_benchmark

    class EchoASR:
        def identity(self):
            return {"provider": "command", "model_id": "fake-asr"}

        def transcribe(self, wav):
            return "xin chào các bạn"

    cases = [
        BenchmarkCase(case_id="ok", text="Xin chào các bạn"),
        BenchmarkCase(case_id="bad", text="Một câu hoàn toàn khác hẳn"),
    ]
    records = run_benchmark(cases, [SilentTTS()], tmp_path, asr=EchoASR())
    assert records[0].transcript == "xin chào các bạn"
    assert records[0].wer == 0.0
    assert records[1].wer == 1.0
    assert records[0].asr_identity == {"provider": "command", "model_id": "fake-asr"}
    verdicts = evaluate_benchmark(records, cases, BenchmarkThresholds(max_wer=0.2))
    assert "asr_wer" in verdicts[1].failures and "asr_wer" not in verdicts[0].failures


def test_benchmark_asr_failure_is_recorded_not_raised(tmp_path: Path) -> None:
    from healthvideo.tts.benchmark import evaluate_benchmark

    class BrokenASR:
        def identity(self):
            return {"provider": "command", "model_id": "fake-asr"}

        def transcribe(self, wav):
            raise RuntimeError("private path C:/x")

    case = BenchmarkCase(case_id="a", text="Xin chào")
    records = run_benchmark([case], [SilentTTS()], tmp_path, asr=BrokenASR())
    assert records[0].ok is True and records[0].wer is None
    assert records[0].asr_error_type == "RuntimeError"
    assert "private" not in str(records)
    assert "asr_failed:RuntimeError" in evaluate_benchmark(records, [case])[0].failures
