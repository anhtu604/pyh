"""Tests for CLI token usage extraction, Python/GPU station spans, and telemetry summary."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.telemetry import (
    STATION_TELEMETRY_FILE,
    extract_cli_usage,
    extract_cli_usage_from_log,
    record_wait_event,
    station_span,
    summarize_telemetry,
)
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.produce import produce_project
from tests.helpers import create_v2_project_fixture


def test_extract_cli_usage_from_footer_ignores_quoted_middle_text() -> None:
    log_text = (
        "codex\n"
        "Example snippet in prompt:\n"
        "tokens used\n"
        "999\n"
        "More text without real footer.\n"
    )
    missing = extract_cli_usage(log_text)
    assert missing.usage_available is False
    assert missing.cli_total_tokens is None

    with_footer = log_text + "hook: Stop Completed\ntokens used\n155,368\n"
    found = extract_cli_usage(with_footer)
    assert found.usage_available is True
    assert found.cli_total_tokens == 155368
    assert found.usage_source == "footer"


def test_extract_cli_usage_from_json_without_double_counting_subsets() -> None:
    payload = json.dumps({
        "type": "response.completed",
        "usage": {
            "input_tokens": 1200,
            "output_tokens": 350,
            "cached_tokens": 800,
            "reasoning_tokens": 120,
        },
    })
    usage = extract_cli_usage(payload)
    assert usage.usage_available is True
    assert usage.input_tokens == 1200
    assert usage.output_tokens == 350
    assert usage.cached_tokens == 800
    assert usage.reasoning_tokens == 120
    # cached_tokens and reasoning_tokens are subsets of input/output tokens.
    assert usage.cli_total_tokens == 1550
    assert usage.usage_source == "json"


def test_extract_cli_usage_sums_jsonl_turns_and_handles_missing_log(tmp_path: Path) -> None:
    jsonl = "\n".join([
        json.dumps({"type": "thread.started"}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 500, "output_tokens": 100, "cached_tokens": 200}}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 300, "output_tokens": 80, "reasoning_tokens": 20}}),
    ])
    log_path = tmp_path / "run.log"
    log_path.write_text(jsonl, encoding="utf-8")
    usage = extract_cli_usage_from_log(log_path)
    assert usage.usage_available is True
    assert usage.input_tokens == 800
    assert usage.output_tokens == 180
    assert usage.cached_tokens == 200
    assert usage.reasoning_tokens == 20
    assert usage.cli_total_tokens == 980

    empty = extract_cli_usage_from_log(tmp_path / "missing.log")
    assert empty.usage_available is False
    assert empty.cli_total_tokens is None


def test_station_span_records_nested_stations_failures_and_summary(tmp_path: Path) -> None:
    with station_span(tmp_path, "gan-nhiem-mo", "produce", revision="001", gpu=False) as outer:
        outer.add_wait(0.02)
        with station_span(tmp_path, "gan-nhiem-mo", "flux", revision="001", gpu=True):
            time.sleep(0.01)
        with station_span(tmp_path, "gan-nhiem-mo", "tts", revision="001", gpu=False):
            time.sleep(0.01)
        with station_span(tmp_path, "gan-nhiem-mo", "render", revision="001", gpu=True):
            time.sleep(0.01)
        with station_span(tmp_path, "gan-nhiem-mo", "qa", revision="001", gpu=True):
            time.sleep(0.01)

    with station_span(tmp_path, "gan-nhiem-mo", "package", revision="001", gpu=False):
        pass

    record_wait_event(tmp_path, "gan-nhiem-mo", "doctor_gate", 1.5, revision="001")

    with pytest.raises(RuntimeError, match="boom"), station_span(
        tmp_path, "other-slug", "render", revision="001", gpu=True
    ):
        raise RuntimeError("boom")

    rows = [
        json.loads(line)
        for line in (tmp_path / STATION_TELEMETRY_FILE).read_text(encoding="utf-8").splitlines()
    ]
    assert any(r["event"] == "end" and r["station"] == "render" and r["ok"] is False for r in rows)

    summary = summarize_telemetry(tmp_path, slug="gan-nhiem-mo")
    assert summary["slug"] == "gan-nhiem-mo"
    assert summary["usage_available"] is False
    assert summary["cli_total_tokens"] is None
    assert summary["wait_s"] >= 1.5
    assert summary["python_gpu_s"] > 0
    assert summary["gpu_s"] > 0
    by_station = summary["stations"]["by_station"]
    assert set(by_station) == {"produce", "flux", "tts", "render", "qa", "package"}
    assert by_station["flux"]["gpu_runs"] == 1
    assert by_station["package"]["ok_runs"] == 1

    # No double counting of nested spans against outer produce.
    assert summary["python_gpu_s"] < (
        by_station["produce"]["active_s"] + by_station["flux"]["active_s"] + 0.05
    )

    overall = summarize_telemetry(tmp_path)
    assert set(overall["projects"]) == {"gan-nhiem-mo", "other-slug"}
    assert overall["projects"]["other-slug"]["stations"]["by_station"]["render"]["failed_runs"] == 1


def test_summarize_telemetry_combines_agents_stations_and_partial_tokens(tmp_path: Path) -> None:
    activity_path = tmp_path / "topics/logs/activity.jsonl"
    activity_path.parent.mkdir(parents=True, exist_ok=True)
    activity_rows = [
        {"at": "2026-11-19T10:00:00+07:00", "role": "writer", "cli": "omniroute",
         "model": "codex/gpt-6.1-sol", "slug": "demo", "step": "draft", "event": "start",
         "ok": None, "job_id": "j1"},
        {"at": "2026-11-19T10:00:30+07:00", "role": "writer", "cli": "omniroute",
         "model": "codex/gpt-6.1-sol", "slug": "demo", "step": "draft", "event": "end",
         "ok": True, "job_id": "j1", "duration_s": 30.0, "usage_available": True,
         "cli_total_tokens": 12000, "failure_kind": None},
        {"at": "2026-11-19T10:01:00+07:00", "role": "script_critic", "cli": "omniroute",
         "model": "codex/gpt-6.1-terra", "slug": "demo", "step": "script_review", "event": "start",
         "ok": None, "job_id": "j2"},
        {"at": "2026-11-19T10:01:10+07:00", "role": "script_critic", "cli": "omniroute",
         "model": "codex/gpt-6.1-terra", "slug": "demo", "step": "script_review", "event": "end",
         "ok": False, "job_id": "j2", "duration_s": 10.0, "usage_available": False,
         "cli_total_tokens": None, "failure_kind": "transient"},
    ]
    activity_path.write_text("\n".join(json.dumps(r) for r in activity_rows) + "\n", encoding="utf-8")
    with station_span(tmp_path, "demo", "tts", gpu=False):
        pass

    summary = summarize_telemetry(tmp_path, slug="demo")
    assert summary["active_agent_s"] == 40.0
    assert summary["cli_total_tokens"] == 12000
    assert summary["usage_available"] is True
    assert summary["partial_usage"] is True
    assert summary["usage_coverage"] == {"reported_runs": 1, "missing_runs": 1, "total_runs": 2}
    assert summary["agents"]["failure_kinds"] == {"transient": 1}


def test_produce_project_emits_station_telemetry_and_skips_dry_run(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "projects", state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=datetime(2026, 9, 12, 8, 0, tzinfo=UTC))

    def runner(argv: list[str]) -> int:
        out_path = Path(argv[argv.index("--output") + 1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"mp4")
        return 0

    produce_project(project, SilentTTS(), runner, dry_run=True)
    assert not (tmp_path / STATION_TELEMETRY_FILE).exists()

    produce_project(project, SilentTTS(), runner, dry_run=False)
    summary = summarize_telemetry(tmp_path, slug="muoi-va-huyet-ap")
    stations = set(summary["stations"]["by_station"])
    assert {"produce", "tts", "qa", "render"}.issubset(stations)


def test_produce_project_records_flux_span_for_illustrations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import wave

    import healthvideo.workflows.produce as produce_workflow
    from healthvideo.tts.base import TTSRequest, TTSResult
    from tests.helpers import align_fixture_script

    monkeypatch.setattr(produce_workflow, "prepare_contact_sheet", lambda *a, **kw: None)
    project = create_v2_project_fixture(tmp_path / "projects", state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision = project / "revisions/001"
    manifest_path = revision / "assets/asset-manifest.yaml"
    manifest_data = read_yaml(manifest_path)
    manifest_data["assets"].append({
        "path": "assets/illustrations/scene1.png",
        "kind": "illustration",
        "semantic": False,
        "classification_reason": "Decorative backdrop",
        "sha256": None,
        "source": "generated:flux2-klein-4b",
        "license": "Apache-2.0",
        "creator": "PYH",
        "revision": "001",
        "prompt": "Warm flat medical illustration",
        "seed": 42,
        "storyboard_role": "whiteboard",
    })
    write_yaml_atomic(manifest_path, manifest_data)
    board_path = revision / "storyboard/storyboard.yaml"
    board_data = read_yaml(board_path)
    highlight = dict(board_data["scenes"][0])
    highlight["id"] = "S02"
    highlight["script_line_id"] = "L02"
    highlight["duration_frames"] = 250
    board_data["visual_budget_profile"] = "m6_5_v1"
    board_data["scenes"] = [
        {
            "id": "S01",
            "start_frame": 0,
            "duration_frames": 750,
            "narration": "Minh họa tổng quan cơ chế ăn mặn và huyết áp trong cơ thể.",
            "script_line_id": "L01",
            "claim_id": "C01",
            "source_marker": "[1]",
            "visual": "whiteboard",
            "on_screen_text": "Overview.",
            "visual_assets": [{"path": "assets/illustrations/scene1.png", "role": "whiteboard"}],
        },
        highlight,
    ]
    align_fixture_script(revision, board_data)
    write_yaml_atomic(board_path, board_data)
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=datetime(2026, 9, 12, 8, 0, tzinfo=UTC))

    saved_script = read_yaml(revision / "script/script.yaml")
    saved_board = read_yaml(board_path)
    line_frames = {
        line["text"]: sum(
            s["duration_frames"] for s in saved_board["scenes"] if s.get("script_line_id") == line["id"]
        ) - 9
        for line in saved_script["lines"]
    }

    class ExactDurationSilent(SilentTTS):
        def synthesize(self, request: TTSRequest, output_path: Path) -> TTSResult:
            frames = line_frames[request.text]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(output_path), "wb") as output:
                output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                output.writeframes(b"\0\0" * (frames * 800))
            return TTSResult(
                provider=self.provider_name,
                audio_file=output_path,
                duration_ms=round(frames * 1000 / 30),
            )

    def runner(argv: list[str]) -> int:
        out_path = Path(argv[argv.index("--output") + 1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"mp4")
        return 0

    produce_project(project, ExactDurationSilent(), runner, dry_run=False)
    summary = summarize_telemetry(tmp_path, slug="muoi-va-huyet-ap")
    assert "flux" in summary["stations"]["by_station"]
    assert summary["stations"]["by_station"]["flux"]["gpu_runs"] == 1
