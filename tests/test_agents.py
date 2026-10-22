"""Tests for external coding agent invocation and quota failover."""

import subprocess
from pathlib import Path
from typing import Any

import pytest

from healthvideo.agents import (
     DEFAULT_AGENTS,
    AgentCli,
    AllAgentsExhausted,
    invoke,
    invoke_with_failover,
)


def _completed(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_quota_switches_to_next_agent(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        if argv[0] == "codex":
            return _completed(returncode=1, stderr="Error: Usage limit reached for today")
        return _completed(returncode=0, stdout="Done by agy")

    result = invoke_with_failover(
        DEFAULT_AGENTS,
        "Run research step",
        cwd=tmp_path,
        log_dir=tmp_path / "logs",
        runner=fake_runner,
    )

    assert result.ok is True
    assert result.agent == "agy"
    assert result.quota_exhausted is False
    assert [call[0] for call in calls] == ["codex", "agy"]


def test_non_quota_failure_does_not_switch(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        return _completed(returncode=1, stderr="SyntaxError: invalid input")

    result = invoke_with_failover(
        DEFAULT_AGENTS,
        "Run research step",
        cwd=tmp_path,
        log_dir=tmp_path / "logs",
        runner=fake_runner,
    )

    assert result.ok is False
    assert result.agent == "codex"
    assert result.quota_exhausted is False
    assert len(calls) == 1


def test_all_exhausted_raises(tmp_path: Path) -> None:
    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if argv[0] == "codex":
            return _completed(returncode=1, stderr="HTTP 429 Too Many Requests")
        return _completed(returncode=1, stdout="RESOURCE_EXHAUSTED: quota exceeded")

    with pytest.raises(AllAgentsExhausted) as exc_info:
        invoke_with_failover(
            DEFAULT_AGENTS,
            "Run draft step",
            cwd=tmp_path,
            log_dir=tmp_path / "logs",
            runner=fake_runner,
        )

    message = str(exc_info.value)
    assert "codex" in message
    assert "agy" in message


def test_prompt_sent_via_stdin_for_codex(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return _completed(returncode=0, stdout="ok")

    codex = DEFAULT_AGENTS[0]
    prompt = "Tóm tắt bằng chứng y khoa"
    invoke(codex, prompt, cwd=tmp_path, log_dir=tmp_path / "logs", runner=fake_runner)

    assert captured["argv"] == list(codex.argv)
    assert captured["kwargs"]["input"] == prompt
    assert captured["kwargs"]["encoding"] == "utf-8"
    assert captured["kwargs"]["text"] is True


def test_prompt_substituted_for_agy(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return _completed(returncode=0, stdout="ok")

    agy = DEFAULT_AGENTS[1]
    prompt = "Viết kịch bản giai đoạn 2"
    invoke(agy, prompt, cwd=tmp_path, log_dir=tmp_path / "logs", runner=fake_runner)

    assert "{prompt}" not in captured["argv"]
    assert prompt in captured["argv"]
    assert captured["argv"][captured["argv"].index("-p") + 1] == prompt
    assert captured["kwargs"]["input"] is None


def test_env_has_no_pin_material(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEALTHVIDEO_APPROVER_PIN", "x")
    monkeypatch.setenv("lower_pin_var", "secret")
    captured_env: dict[str, str] = {}

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured_env.update(kwargs["env"])
        return _completed(returncode=0)

    invoke(
        DEFAULT_AGENTS[0],
        "prompt",
        cwd=tmp_path,
        log_dir=tmp_path / "logs",
        runner=fake_runner,
    )

    assert not any("pin" in key.lower() for key in captured_env)


def test_success_returns_first_agent_result(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv[0])
        return _completed(returncode=0, stdout="completed on first try")

    result = invoke_with_failover(
        DEFAULT_AGENTS,
        "prompt",
        cwd=tmp_path,
        log_dir=tmp_path / "logs",
        runner=fake_runner,
    )

    assert result.ok is True
    assert result.agent == "codex"
    assert result.quota_exhausted is False
    assert calls == ["codex"]


def test_missing_executable_is_not_quota(tmp_path: Path) -> None:
    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(2, "No such file or directory", argv[0])

    agent = AgentCli("missing-cli", ("missing-cli", "{prompt}"), False)
    result = invoke(
        agent,
        "prompt",
        cwd=tmp_path,
        log_dir=tmp_path / "logs",
        runner=fake_runner,
    )

    assert result.ok is False
    assert result.quota_exhausted is False
    assert result.log_path.is_file()
    assert "missing-cli" in result.log_path.read_text(encoding="utf-8")


def test_log_written_utf8(tmp_path: Path) -> None:
    vietnamese_stdout = "Đã kiểm tra huyết áp tâm thu và đường huyết lúc đói.\n"
    vietnamese_stderr = "Cảnh báo: cần đối chiếu thêm nguồn PubMed.\n"

    def fake_runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _completed(
            returncode=0,
            stdout=vietnamese_stdout,
            stderr=vietnamese_stderr,
        )

    result = invoke(
        DEFAULT_AGENTS[0],
        "prompt",
        cwd=tmp_path,
        log_dir=tmp_path / "logs",
        runner=fake_runner,
    )

    assert result.log_path.is_file()
    assert result.log_path.name.endswith("-codex.log")
    content = result.log_path.read_text(encoding="utf-8")
    assert content == vietnamese_stdout + vietnamese_stderr
