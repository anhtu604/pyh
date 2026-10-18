import json
import subprocess
from copy import deepcopy

import pytest
from pydantic import ValidationError

from healthvideo.domain.evidence import CandidateSource
from healthvideo.evidence.screening import (
    CommandJudge,
    DualLLMScreener,
    ScreeningCriteria,
    ScreeningDecision,
)


def candidate(**updates):
    return CandidateSource(
        source_id="R-TEST-01",
        database="synthetic",
        title="Ví dụ minh họa",
        abstract="Nội dung giả để kiểm thử cấu trúc.",
        year=2026,
        **updates,
    )


def criteria():
    return ScreeningCriteria(
        question="Câu hỏi minh họa?", include=["Mẫu A"], exclude=["Mẫu B"]
    )


class FakeJudge:
    def __init__(self, decision="include", reason="Lý do minh họa", error=False):
        self.decision = decision
        self.reason = reason
        self.error = error
        self.calls = []

    def judge(self, record, criteria, *, reviews=()):
        self.calls.append((deepcopy(record), deepcopy(criteria), deepcopy(reviews)))
        if self.error:
            raise RuntimeError("SECRET must not be persisted")
        return ScreeningDecision(
            decision=self.decision,
            reason=self.reason,
            probability=0.7,
            reviewer="fake",
        )


@pytest.mark.parametrize("decision", ["include", "exclude"])
def test_agreement_does_not_call_arbiter(decision):
    first, second, arbiter = FakeJudge(decision), FakeJudge(decision), FakeJudge()
    result = DualLLMScreener(first, second, arbiter).screen(candidate(), criteria())
    assert result.final.decision == decision
    assert result.arbiter is None
    assert not arbiter.calls
    assert first.calls == second.calls
    assert first.calls[0][2] == ()


@pytest.mark.parametrize(
    "left,right", [("include", "exclude"), ("unsure", "include"), ("unsure", "unsure")]
)
def test_disagreement_or_unsure_passes_both_reasons_to_arbiter(left, right):
    first, second = FakeJudge(left, "Lý do A"), FakeJudge(right, "Lý do B")
    arbiter = FakeJudge("exclude", "Phân xử minh họa")
    result = DualLLMScreener(first, second, arbiter).screen(candidate(), criteria())
    assert result.final == result.arbiter
    assert result.final.decision == "exclude"
    reviews = arbiter.calls[0][2]
    assert [(r.decision, r.reason) for r in reviews] == [
        (left, "Lý do A"),
        (right, "Lý do B"),
    ]
    assert first.calls == second.calls


def test_judge_exception_becomes_unsure_and_keeps_screening_alive():
    result = DualLLMScreener(
        FakeJudge(error=True), FakeJudge(), FakeJudge(error=True)
    ).screen(
        candidate(),
        criteria(),
    )
    assert result.reviewer_1.decision == "unsure"
    assert result.final.decision == "unsure"
    assert "RuntimeError" in result.final.reason
    assert "SECRET" not in result.final.reason


@pytest.mark.parametrize(
    "updates",
    [
        {"question": " "},
        {"include": "bad"},
        {"exclude": [1]},
        {"include": [""]},
        {"unexpected": "SECRET"},
    ],
)
def test_criteria_rejects_invalid_yaml_shape(updates):
    data = {"question": "Ví dụ?", "include": [], "exclude": []} | updates
    with pytest.raises(ValidationError):
        ScreeningCriteria.model_validate(data)


def test_old_candidate_shape_has_optional_publication_type():
    assert candidate().pub_type == ""


def test_command_prompts_are_identical_and_only_contain_allowed_fields(monkeypatch):
    prompts = []

    def run(argv, **kwargs):
        prompts.append(kwargs["input"])
        assert kwargs["timeout"] == 120
        assert kwargs.get("shell", False) is False
        assert kwargs["encoding"] == "utf-8"
        return subprocess.CompletedProcess(
            argv, 0, '{"decision":"include","reason":"Ví dụ","probability":0.8}', ""
        )

    monkeypatch.setenv("HEALTHVIDEO_SCREEN_CMD", "fake -p")
    monkeypatch.setenv("SCREEN_SECRET", "SECRET")
    monkeypatch.setattr("healthvideo.evidence.screening.subprocess.run", run)
    record = candidate(
        authors=["SECRET"], doi="SECRET", venue="SECRET", pub_type="synthetic review"
    )
    result = DualLLMScreener(
        CommandJudge("one"), CommandJudge("two"), CommandJudge("three")
    ).screen(record, criteria())
    assert result.final.decision == "include"
    assert result.reviewer_1.reviewer == "one"
    assert result.reviewer_2.reviewer == "two"
    assert len(prompts) == 2 and prompts[0] == prompts[1]
    assert "SECRET" not in prompts[0]
    assert "synthetic review" in prompts[0]
    assert "Ví dụ minh họa" in prompts[0]


def test_command_arbiter_prompt_contains_both_decisions_and_reasons(monkeypatch):
    prompts = []
    outputs = iter(
        [("include", "Lý do A"), ("exclude", "Lý do B"), ("unsure", "Phân xử")]
    )

    def run(argv, **kwargs):
        prompts.append(kwargs["input"])
        decision, reason = next(outputs)
        return subprocess.CompletedProcess(
            argv,
            0,
            json.dumps({"decision": decision, "reason": reason, "probability": None}),
            "",
        )

    monkeypatch.setenv("HEALTHVIDEO_SCREEN_CMD", "fake")
    monkeypatch.setattr("healthvideo.evidence.screening.subprocess.run", run)
    result = DualLLMScreener(
        CommandJudge("one"), CommandJudge("two"), CommandJudge("three")
    ).screen(candidate(), criteria())
    assert result.final.decision == "unsure"
    assert prompts[0] == prompts[1]
    assert "Lý do A" not in prompts[0] and "Lý do B" not in prompts[1]
    assert all(
        text in prompts[2] for text in ["include", "exclude", "Lý do A", "Lý do B"]
    )


@pytest.mark.parametrize(
    "stdout,want",
    [
        (
            'log {"decision":"exclude","reason":"first"}\nfinal {"decision":"include","reason":"last {example}","probability":null}\nend',
            "include",
        ),
        ('```json\n{"decision":"exclude","reason":"example"}\n```', "exclude"),
        ("not JSON", "unsure"),
        ('{"decision":"wrong","reason":"example"}', "unsure"),
        ('{"decision":"include"}', "unsure"),
        ('{"decision":"include","reason":"example","probability":2}', "unsure"),
    ],
)
def test_command_reads_last_json_object_or_returns_unsure(monkeypatch, stdout, want):
    monkeypatch.setenv("HEALTHVIDEO_SCREEN_CMD", "fake")
    monkeypatch.setattr(
        "healthvideo.evidence.screening.subprocess.run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout, ""),
    )
    result = CommandJudge("test").judge(candidate(), criteria())
    assert result.decision == want
    assert result.reason


@pytest.mark.parametrize(
    "failure", ["timeout", "missing", "exit", "batch", "empty", "bad_quotes"]
)
def test_command_failures_return_unsure_without_exposing_output(monkeypatch, failure):
    monkeypatch.setenv(
        "HEALTHVIDEO_SCREEN_CMD",
        {"empty": "", "bad_quotes": 'fake "'}.get(failure, "fake"),
    )

    def run(argv, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, 120, output="SECRET")
        if failure == "missing":
            raise FileNotFoundError("SECRET")
        return subprocess.CompletedProcess(argv, 1, "SECRET", "SECRET")

    monkeypatch.setattr("healthvideo.evidence.screening.subprocess.run", run)
    if failure == "batch":
        from healthvideo.process import UnsafeBatchLauncherError

        def prepare(argv):
            raise UnsafeBatchLauncherError("SECRET")

        monkeypatch.setattr(
            "healthvideo.evidence.screening.prepare_subprocess_argv", prepare
        )
    result = CommandJudge("test").judge(candidate(), criteria())
    assert result.decision == "unsure" and result.reason
    assert "SECRET" not in result.reason


def test_windows_quoted_command_uses_helper_and_no_shell(monkeypatch):
    captured = []
    monkeypatch.setenv(
        "HEALTHVIDEO_SCREEN_CMD",
        '"C:\\Program Files\\Example\\judge.exe" "argument with spaces" -p',
    )
    monkeypatch.setattr("healthvideo.evidence.screening.sys.platform", "win32")

    def prepare(argv):
        captured.append(argv)
        return argv

    monkeypatch.setattr(
        "healthvideo.evidence.screening.prepare_subprocess_argv", prepare
    )
    monkeypatch.setattr(
        "healthvideo.evidence.screening.subprocess.run",
        lambda argv, **kw: subprocess.CompletedProcess(
            argv, 0, '{"decision":"include","reason":"example"}', ""
        ),
    )
    assert CommandJudge("test").judge(candidate(), criteria()).decision == "include"
    assert captured == [
        ["C:\\Program Files\\Example\\judge.exe", "argument with spaces", "-p"]
    ]
