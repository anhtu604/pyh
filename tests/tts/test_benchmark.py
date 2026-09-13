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
