"""End-to-end offline verification of channel standards with legacy projects."""

from __future__ import annotations

import json
import threading
from datetime import date
from http.client import HTTPConnection
from pathlib import Path

import pytest

from healthvideo.approver_pin import set_pin
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import write_yaml_atomic
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
from tests.helpers import create_v2_project_fixture


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


def test_legacy_project_reads_accepted_standards_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Forbidden paid provider or production worker called during offline verification")

    monkeypatch.setattr(factory, "start_background", _forbidden)
    monkeypatch.setattr(VibiTTS, "synthesize", _forbidden)
    monkeypatch.setattr(ElevenLabsTTS, "synthesize", _forbidden)
    monkeypatch.setattr(factory, "running_pid", lambda _: None)

    pin_file = tmp_path / "config" / "approver-pin.json"
    set_pin("918273", path=pin_file)
    monkeypatch.setattr(dashboard, "pin_path", lambda: pin_file)
    monkeypatch.setattr(dashboard, "reviewer_name", lambda: "")

    add_to_queue(
        tmp_path,
        QueueEntry(
            slug="muoi-va-huyet-ap-v2",
            title="Vì sao ăn mặn làm tăng huyết áp?",
            question="Muối giữ nước và tăng sức cản mạch máu thế nào?",
            doctor_note="Nhấn mạnh vai trò giữ nước ở thận.",
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

    write_yaml_atomic(
        tmp_path / factory_standards.STANDARDS_FILE,
        {
            "version": 1,
            "entries": [
                {
                    "id": "std-1-v1",
                    "stage": 1,
                    "version": 1,
                    "text": "Chuẩn giai đoạn 1: mọi khẳng định phải gắn claim và câu trích nguyên văn.",
                    "reviewer": "Bác sĩ",
                    "accepted_at": "2026-10-30T00:00:00+00:00",
                    "scope": "channel",
                }
            ],
            "feedback_scope": "Only chung and matching project slug; history preserved.",
        },
    )

    server = dashboard.DashboardServer(tmp_path, 0, token="e2e-token", agents=list)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, proj_bundle = _http_call(
            server, "GET", f"/api/project/{legacy_project.name}/bundle"
        )
        assert status == 200
        assert proj_bundle["slug"] == legacy_project.name
        assert len(proj_bundle["lines"]) > 0

        status, proj_ops = _http_call(
            server, "GET", f"/api/project/{legacy_project.name}/operations"
        )
        assert status == 200
        assert proj_ops["slug"] == legacy_project.name
        assert proj_ops["gate"] == "medical"
        assert dashboard_operations.project_operations(tmp_path, legacy_project.name)["revision"] == "001"

        block = standards.prompt_block(tmp_path, slug=legacy_project.name)
        assert "Giai đoạn 1 · v1" in block
        assert not (legacy_project / "revisions" / "001" / "workflow" / "standards.yaml").exists()
        assert set(factory_standards.accepted_standards(tmp_path)) == {1}

        assert _snapshot_production_bytes() == before_bytes
    finally:
        server.shutdown()
        server.server_close()
