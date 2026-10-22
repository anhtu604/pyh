"""Tests for the `healthvideo run` CLI command."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.workflows.runner import RunDeps, RunReport

runner = CliRunner()


def test_run_prints_gate_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_queue(
        root: Path,
        deps: RunDeps,
        *,
        once: bool = False,
        **kwargs: Any,
    ) -> RunReport:
        del deps, once, kwargs
        return RunReport(
            advanced=["tang-huyet-ap"],
            at_gate=["tang-huyet-ap"],
            blocked=["gan-nhiem-mo"],
            code_changes=[Path("video/src/anatomy/ArteryWall.tsx")],
            exhausted=False,
        )

    monkeypatch.setattr("healthvideo.cli.run_queue", fake_run_queue)

    result = runner.invoke(app, ["run", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "tang-huyet-ap" in result.output
    assert "healthvideo review open" in result.output
    assert "--gate medical" in result.output
    assert "topics/logs/gan-nhiem-mo/blocked.txt" in result.output
    assert "topics/code-review.yaml" in result.output


def test_run_exhausted_exit_code_3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_queue(
        root: Path,
        deps: RunDeps,
        *,
        once: bool = False,
        **kwargs: Any,
    ) -> RunReport:
        del root, deps, once, kwargs
        return RunReport(exhausted=True)

    monkeypatch.setattr("healthvideo.cli.run_queue", fake_run_queue)

    result = runner.invoke(app, ["run", "--root", str(tmp_path)])

    assert result.exit_code == 3
    assert "Cả Codex và agy đều hết quota — chạy lại sau." in result.output


def test_run_once_flag_passed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run_queue(
        root: Path,
        deps: RunDeps,
        *,
        once: bool = False,
        **kwargs: Any,
    ) -> RunReport:
        captured["root"] = root
        captured["deps"] = deps
        captured["once"] = once
        return RunReport(advanced=["chu-de-1"])

    monkeypatch.setattr("healthvideo.cli.run_queue", fake_run_queue)

    result = runner.invoke(app, ["run", "--root", str(tmp_path), "--once"])

    assert result.exit_code == 0, result.output
    assert captured["root"] == tmp_path
    assert isinstance(captured["deps"], RunDeps)
    assert captured["once"] is True
