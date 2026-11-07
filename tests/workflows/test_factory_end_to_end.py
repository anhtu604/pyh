"""End-to-end offline verification of factory-first staged acceptance."""

from __future__ import annotations

import json
import threading
from datetime import date
from http.client import HTTPConnection
from pathlib import Path

import pytest

from healthvideo.approver_pin import set_pin
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.queue import add_to_queue
from healthvideo.tts.elevenlabs import ElevenLabsTTS
from healthvideo.tts.vibi import VibiTTS
from healthvideo.workflows import (
    dashboard,
    dashboard_operations,
    factory,
    factory_standards,
    standards,
)
from tests.helpers import create_v2_project_fixture, write_passing_script_review


def _http_call(
    server: dashboard.DashboardServer,
    method: str,
    path: str,
    payload: dict | None = None,
    *,
    token: str = "e2e-token",
) -> tuple[int, dict | bytes]:
    port = server.server_address[1]
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": f"127.0.0.1:{port}", "X-Dashboard-Token": token}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    raw = response.read()
    content_type = response.getheader("Content-Type", "")
    conn.close()
    if content_type.startswith("application/json"):
        return response.status, json.loads(raw.decode("utf-8"))
    return response.status, raw


def test_factory_stage1_acceptance_end_to_end_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # (c) Paid providers and background production worker must never be invoked.
    def _forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Forbidden paid provider or production worker called during offline trial")

    monkeypatch.setattr(factory, "start_background", _forbidden)
    monkeypatch.setattr(VibiTTS, "synthesize", _forbidden)
    monkeypatch.setattr(ElevenLabsTTS, "synthesize", _forbidden)
    from healthvideo.agents import AgentResult
    from healthvideo.storage.files import write_yaml_atomic
    from healthvideo.workflows import factory_trials

    def _fake_invoke(agents: object, prompt: str, *, cwd: Path, log_dir: Path) -> AgentResult:
        del agents, cwd
        rev = log_dir.parent / "project" / "revisions" / "001"
        write_passing_script_review(rev)
        write_yaml_atomic(rev / "script/script.yaml", {"lines": [{"id": "L01", "text": "Synthetic trial script.", "claim_id": "C01"}]})
        write_yaml_atomic(rev / "evidence/ledger.yaml", {"claims": [{"id": "C01", "text_public": "Synthetic claim.", "sources": ["R01"], "support": [{"source_id": "R01", "locator": "p.1", "quote": "Quote."}]}], "records": [{"id": "R01", "title": "Source"}]})
        log_path = log_dir / "fake.log"
        log_path.write_text("ok", encoding="utf-8")
        return AgentResult(agent="fake", ok=True, quota_exhausted=False, log_path=log_path)

    monkeypatch.setattr(factory, "running_pid", lambda _: None)
    monkeypatch.setattr(factory_trials, "invoke_with_failover", _fake_invoke)

    pin_file = tmp_path / "config" / "approver-pin.json"
    set_pin("918273", path=pin_file)
    monkeypatch.setattr(dashboard, "pin_path", lambda: pin_file)
    monkeypatch.setattr(dashboard, "reviewer_name", lambda: "")

    # Set up legacy production project (missing workflow/standards.yaml snapshot) + queue fixture.
    add_to_queue(
        tmp_path,
        QueueEntry(
            slug="muoi-va-huyet-ap-v2",
            title="Vì sao ăn mặn làm tăng huyết áp?",
            question="Muối giữ nước và tăng sức cản mạch máu thế nào?",
            doctor_note="Giữ nguyên chờ nghiệm thu đủ 4 chuẩn.",
            added=date(2026, 10, 25),
        ),
    )
    legacy_project = create_v2_project_fixture(
        tmp_path / "projects",
        state="awaiting_medical_review",
    )
    assert not (legacy_project / "revisions" / "001" / "workflow" / "standards.yaml").exists()

    def _snapshot_production_bytes() -> dict[Path, bytes]:
        return {
            path: path.read_bytes()
            for folder in ("projects", "topics")
            for path in sorted((tmp_path / folder).rglob("*"))
            if path.is_file()
        }

    before_bytes = _snapshot_production_bytes()

    # Run stage 1 trial and accept v1 with PIN via the dashboard server.
    server1 = dashboard.DashboardServer(tmp_path, 0, token="e2e-token", agents=list)
    thread1 = threading.Thread(target=server1.serve_forever, daemon=True)
    thread1.start()
    try:
        status, created = _http_call(
            server1,
            "POST",
            "/api/trials/create",
            {"stage": 1, "topic": "TEST — Hình tròn chuyển động"},
        )
        assert status == 200, created
        trial_id = created["message"]["id"]

        status, ran = _http_call(
            server1,
            "POST",
            "/api/trials/run",
            {"trial_id": trial_id, "real_service": False},
        )
        assert status == 200, ran
        assert ran["message"]["status"] == "running"
        assert factory_trials.wait_trial(tmp_path, trial_id)["status"] == "ready"

        draft_text = "Chuẩn giai đoạn 1: mọi khẳng định phải gắn claim và câu trích nguyên văn."
        status, saved = _http_call(
            server1,
            "POST",
            "/api/trials/standard-draft",
            {"trial_id": trial_id, "stage": 1, "text": draft_text},
        )
        assert status == 200, saved

        status, bundle = _http_call(server1, "GET", f"/api/trials/{trial_id}/bundle")
        assert status == 200, bundle
        assert bundle["draft"]["text"] == draft_text

        status, accepted = _http_call(
            server1,
            "POST",
            "/api/trials/accept",
            {
                "trial_id": trial_id,
                "stage": 1,
                "text": draft_text,
                "expected_input_hash": bundle["input_hash"],
                "expected_version": 0,
                "expected_standards_hash": bundle["standards_hash"],
                "reviewer": "Bác sĩ nghiệm thu",
                "pin": "918273",
            },
        )
        assert status == 200, accepted
        assert accepted["message"]["version"] == 1
        assert accepted["message"]["stage"] == 1
    finally:
        server1.shutdown()
        server1.server_close()

    # Restart a fresh DashboardServer instance and verify persistence + constraints (a)–(d).
    server2 = dashboard.DashboardServer(tmp_path, 0, token="e2e-token", agents=list)
    thread2 = threading.Thread(target=server2.serve_forever, daemon=True)
    thread2.start()
    try:
        status, std_info = _http_call(server2, "GET", "/api/standards/accepted")
        assert status == 200
        assert set(std_info["accepted"]) == {"1"}
        assert std_info["accepted"]["1"]["version"] == 1

        # (d) Legacy project without workflow/standards.yaml snapshot remains readable without mutation.
        status, proj_bundle = _http_call(
            server2, "GET", f"/api/project/{legacy_project.name}/bundle"
        )
        assert status == 200
        assert proj_bundle["slug"] == legacy_project.name
        assert len(proj_bundle["lines"]) > 0

        status, proj_ops = _http_call(
            server2, "GET", f"/api/project/{legacy_project.name}/operations"
        )
        assert status == 200
        assert proj_ops["slug"] == legacy_project.name
        assert proj_ops["gate"] == "medical"
        assert dashboard_operations.project_operations(tmp_path, legacy_project.name)["revision"] == "001"

        block = standards.prompt_block(tmp_path, slug=legacy_project.name)
        assert "Giai đoạn 1 · v1" in block
        assert not (legacy_project / "revisions" / "001" / "workflow" / "standards.yaml").exists()
        assert set(factory_standards.accepted_standards(tmp_path)) == {1}

        # (b) Production project and queue fixture bytes are completely unchanged.
        assert _snapshot_production_bytes() == before_bytes
    finally:
        server2.shutdown()
        server2.server_close()
