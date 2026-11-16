"""Offline tests for two-way Telegram Leader Bot bridge and fixed chat.py kwargs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from healthvideo.agents import AgentResult
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import write_yaml_atomic
from healthvideo.storage.queue import load_queue
from healthvideo.workflows import (
    channel_analytics,
    chat,
    researcher,
    telegram,
    telegram_bot,
)
from healthvideo.workflows.factory_deps import read_state
from tests.workflows.test_change_request import create_v2_project_fixture


def _setup_env(monkeypatch, chat_id: str = "555001") -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", chat_id)


def _capture_sends():
    sent: list[dict] = []

    def send_fn(text: str, *, reply_markup=None, chat_id=None, transport=None, timeout=10):
        sent.append({"text": text, "reply_markup": reply_markup, "chat_id": chat_id})
        return {"ok": True, "result": {"message_id": len(sent)}}

    return sent, send_fn


def test_unauthorized_chat_ignored(tmp_path: Path, monkeypatch):
    _setup_env(monkeypatch, "555001")
    sent, send_fn = _capture_sends()
    state = telegram_bot.load_state(tmp_path)

    def req(method, payload, **kwargs):
        if method == "getUpdates":
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 10,
                        "message": {"message_id": 1, "chat": {"id": 999999, "type": "private"}, "text": "/status"},
                    }
                ],
            }
        return {"ok": True}

    state, ok = telegram_bot.poll_once(tmp_path, state, req=req, send_fn=send_fn, typing=False)
    assert ok is True
    assert state["offset"] == 11
    assert sent == []
    assert not (tmp_path / "topics" / "chat.jsonl").exists()


@pytest.mark.parametrize(
    "text",
    [
        "Nhập PIN 123456 giúp anh",
        "Duyệt cổng y khoa cho video này đi",
        "approve medical gate please",
        "đổi pin thành 999999",
    ],
)
def test_pin_and_gate_approval_refused_without_writing_chat(tmp_path: Path, monkeypatch, text: str):
    _setup_env(monkeypatch, "555001")
    sent, send_fn = _capture_sends()
    state = telegram_bot.load_state(tmp_path)

    ok = telegram_bot.handle_update(
        tmp_path,
        state,
        {"update_id": 20, "message": {"message_id": 2, "chat": {"id": 555001, "type": "private"}, "text": text}},
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        typing=False,
    )
    assert ok is True
    assert len(sent) == 1
    assert "KHÔNG nhận mã PIN" in sent[0]["text"]
    assert not (tmp_path / "topics" / "chat.jsonl").exists()


def test_leader_dispatch_sync_and_analyze_channel_auto_execute(tmp_path: Path, monkeypatch):
    _setup_env(monkeypatch, "555001")
    channel_analytics.upsert_video_metric(tmp_path, {
        "title": "Measured imported video", "views": 100, "retention_30s_pct": 60.0,
    })
    sent, send_fn = _capture_sends()
    state = telegram_bot.load_state(tmp_path)
    captured: dict = {}

    def fake_sync(root, *, spreadsheet_id="", **kwargs):
        captured["spreadsheet_id"] = spreadsheet_id
        return {"synced_count": 3, "total": 5, "tier_a": 2, "errors": []}

    def fake_analyze(root, *, focus="", **kwargs):
        captured["focus"] = focus
        return {"insights": {"summary": "Hook 10s đầu giữ chân tốt"}, "added_topics": 1}

    monkeypatch.setattr(researcher, "sync_reference_sheet", fake_sync)
    monkeypatch.setattr(channel_analytics, "analyze_channel_performance", fake_analyze)

    def fake_invoke(slots, prompt, **kwargs):
        assert kwargs["role"] == "coordinator"
        rows = chat.load(tmp_path, None)
        report_path = Path(kwargs["log_dir"]) / f"{rows[-1]['id']}.yaml"
        write_yaml_atomic(
            report_path,
            {
                "reply": "Đã điều Researcher đồng bộ Sheet và phân tích kênh cho anh.",
                "action": "dispatch",
                "assignments": [
                    {
                        "role": "researcher",
                        "step": "sync_sheet_topics",
                        "task": "Đồng bộ sheet",
                        "sheet_url": "https://docs.google.com/spreadsheets/d/SHEET_ABC_123/edit#gid=0",
                    },
                    {
                        "role": "researcher",
                        "step": "analyze_channel",
                        "task": "Phân tích retention",
                        "query": "hook 30s đầu",
                    },
                ],
            },
        )
        return AgentResult("fake", True, False, kwargs["log_dir"] / "fake.log")

    ok = telegram_bot.handle_update(
        tmp_path,
        state,
        {
            "update_id": 30,
            "message": {
                "message_id": 3,
                "chat": {"id": 555001, "type": "private"},
                "text": "Đồng bộ sheet chủ đề và phân tích kênh giúp anh",
            },
        },
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        invoke=fake_invoke,
        typing=False,
    )
    assert ok is True
    assert captured["spreadsheet_id"] == "SHEET_ABC_123"
    assert captured["focus"] == "hook 30s đầu"
    rows = chat.load(tmp_path, None)
    assert rows[0]["source"] == "telegram"
    assert rows[-1]["status"] == "done"
    assert "Đồng bộ Sheet chủ đề: +3 mục" in sent[0]["text"]
    assert "Hook 10s đầu giữ chân tốt" in sent[0]["text"]


def test_telegram_analysis_without_data_explains_readiness_without_invoking_analyzer(tmp_path: Path, monkeypatch):
    _setup_env(monkeypatch, "555001")
    sent, send_fn = _capture_sends()
    state = telegram_bot.load_state(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("No measured observations: analyzer must not run")

    monkeypatch.setattr(channel_analytics, "analyze_channel_performance", forbidden)
    # A title/link alone does not provide measured performance observations.
    channel_analytics.upsert_video_metric(tmp_path, {"title": "Metadata only", "url": "https://example.com/video"})

    def fake_invoke(slots, prompt, **kwargs):
        rows = chat.load(tmp_path, None)
        report_path = Path(kwargs["log_dir"]) / f"{rows[-1]['id']}.yaml"
        write_yaml_atomic(report_path, {
            "reply": "Đã giao researcher phân tích kênh.",
            "action": "dispatch",
            "assignments": [{"role": "researcher", "step": "analyze_channel", "task": "Phân tích kênh"}],
        })
        return AgentResult("fake", True, False, kwargs["log_dir"] / "fake.log")

    assert telegram_bot.handle_update(
        tmp_path, state,
        {"update_id": 31, "message": {"message_id": 4, "chat": {"id": 555001, "type": "private"},
                                     "text": "Phân tích kênh giúp anh"}},
        req=lambda *a, **k: {"ok": True}, send_fn=send_fn, invoke=fake_invoke, typing=False,
    ) is True
    result = chat.load(tmp_path, None)[-1]
    assert result["status"] == "done"
    assert result["action"] == "status"
    assert result["assignments"] == []
    assert len(sent) == 1
    assert "Chưa có số liệu đo" in sent[0]["text"]
    assert "CSV/Sheet" in sent[0]["text"]


def test_confirm_and_dismiss_callbacks_work_across_medical_gate(tmp_path: Path, monkeypatch):
    _setup_env(monkeypatch, "555001")
    project = create_v2_project_fixture(tmp_path / "projects", state=WorkflowState.MEDICALLY_APPROVED)
    slug = project.name
    approval = project / "revisions/001/reviews/medical-approval.yaml"
    write_yaml_atomic(approval, {"approved": True})
    sent, send_fn = _capture_sends()
    state = telegram_bot.load_state(tmp_path)

    def fake_invoke(slots, prompt, **kwargs):
        rows = chat.load(tmp_path, slug)
        report_path = Path(kwargs["log_dir"]) / f"{rows[-1]['id']}.yaml"
        write_yaml_atomic(
            report_path,
            {
                "reply": "Đổi số liệu ngưỡng đường huyết sẽ cần mở lại cổng Y khoa.",
                "action": "edit_script",
                "brief": "Đổi 6 mg/dL thành 5 mg/dL",
            },
        )
        return AgentResult("fake", True, False, kwargs["log_dir"] / "fake.log")

    telegram_bot.handle_update(
        tmp_path,
        state,
        {
            "update_id": 40,
            "message": {
                "message_id": 4,
                "chat": {"id": 555001, "type": "private"},
                "text": f"#{slug} Sửa 6 mg/dL thành 5 mg/dL",
            },
        },
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        invoke=fake_invoke,
        typing=False,
    )
    markup = sent[-1]["reply_markup"]
    assert markup is not None
    buttons = [btn for row in markup["inline_keyboard"] for btn in row]
    for btn in buttons:
        assert len(btn["callback_data"].encode("utf-8")) <= 64
    cfm_cb = next(btn["callback_data"] for btn in buttons if btn["callback_data"].startswith("cfm:"))

    telegram_bot.handle_update(
        tmp_path,
        state,
        {
            "update_id": 41,
            "callback_query": {
                "id": "cb-1",
                "data": cfm_cb,
                "message": {"message_id": 10, "chat": {"id": 555001, "type": "private"}},
            },
        },
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        typing=False,
    )
    assert read_state(project) == WorkflowState.NEEDS_MEDICAL_REVISION
    assert not approval.exists()
    assert list((project / "revisions/001/reviews/medical").glob("*-superseded-approval.yaml"))
    assert "Đã xác nhận thực hiện đề xuất" in sent[-1]["text"]

    # Second proposal dismissed instead of confirmed
    pending_msg = chat.load(tmp_path, slug)[-1]
    dis_msg = chat._append(
        tmp_path,
        slug,
        chat._message("coordinator", "Đề xuất phụ", {}, action="factory_feedback", brief="Thử nghiệm", status="pending"),
    )
    assert pending_msg["id"] != dis_msg["id"]
    state["active_slug"] = slug
    telegram_bot.handle_update(
        tmp_path,
        state,
        {
            "update_id": 42,
            "callback_query": {
                "id": "cb-2",
                "data": f"dis:{dis_msg['id']}",
                "message": {"message_id": 11, "chat": {"id": 555001, "type": "private"}},
            },
        },
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        typing=False,
    )
    assert chat.load(tmp_path, slug)[-1]["status"] == "dismissed"

    # Ask options render <=64-byte opt: callbacks and clicking one triggers follow-up turn
    prompts_seen: list[str] = []

    def ask_invoke(slots, prompt, **kwargs):
        rows = chat.load(tmp_path, slug)
        prompts_seen.append(rows[-1]["text"])
        report_path = Path(kwargs["log_dir"]) / f"{rows[-1]['id']}.yaml"
        if len(prompts_seen) == 1:
            write_yaml_atomic(
                report_path,
                {
                    "reply": "Anh muốn giữ nguyên hay đổi cảnh S07?",
                    "action": "ask",
                    "options": [
                        {"label": "Giữ nguyên", "effect": "keep"},
                        {"label": "Đổi cảnh S07", "effect": "change"},
                    ],
                },
            )
        else:
            write_yaml_atomic(report_path, {"reply": "Đã ghi nhận lựa chọn của anh.", "action": "status"})
        return AgentResult("fake", True, False, kwargs["log_dir"] / "fake.log")

    telegram_bot.handle_update(
        tmp_path,
        state,
        {
            "update_id": 43,
            "message": {"message_id": 12, "chat": {"id": 555001, "type": "private"}, "text": "Xem lại cảnh S07"},
        },
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        invoke=ask_invoke,
        typing=False,
    )
    opt_buttons = [btn for row in sent[-1]["reply_markup"]["inline_keyboard"] for btn in row]
    assert all(len(btn["callback_data"].encode("utf-8")) <= 64 for btn in opt_buttons)
    assert any(btn["text"] == "Giữ nguyên" for btn in opt_buttons)
    opt_cb = next(btn["callback_data"] for btn in opt_buttons if btn["callback_data"].startswith("opt:"))

    telegram_bot.handle_update(
        tmp_path,
        state,
        {
            "update_id": 44,
            "callback_query": {
                "id": "cb-3",
                "data": opt_cb,
                "message": {"message_id": 13, "chat": {"id": 555001, "type": "private"}},
            },
        },
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        invoke=ask_invoke,
        typing=False,
    )
    assert prompts_seen[-1] == "Giữ nguyên"
    assert "Đã ghi nhận lựa chọn của anh." in sent[-1]["text"]


def test_slash_commands_status_inbox_promote_project_chung(tmp_path: Path, monkeypatch):
    _setup_env(monkeypatch, "555001")
    project = create_v2_project_fixture(tmp_path / "projects", state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    slug = project.name

    # Seed inbox via real researcher CSV parser
    long_title = "Uống nước chanh ấm buổi sáng sớm có thực sự giúp thải độc gan và thận khỏe mạnh hơn không"
    csv_map = {
        "gid=728612942": (
            "ngày_chạy,nguồn_tín_hiệu,phát_ngôn,câu_hỏi_kiểm_chứng,tương_tác,điểm_tranh_cãi,"
            "điểm_giáo_dục,độ_chắc_chắn,khả_năng_video,phần_đúng,phần_sai_thiếu,ngoại_lệ,nguy_cơ,"
            "phán_quyết_sơ_bộ,nguồn_bằng_chứng,PMID_DOI,url_gốc,điểm_cần_bác_sĩ_duyệt,hook_trung_lập\n"
            f"2026-11-14,TikTok,{long_title},Nước chanh có thải độc gan?,"
            "150k,5/5,5/5,5/5,5/5,Bù nước,Không thải độc gan,Loét dạ dày,,Sai một phần,PubMed,PMID 123,https://e.co,Acid,\n"
        )
    }

    def fake_fetcher(url: str) -> str:
        for key, body in csv_map.items():
            if key in url:
                return body
        return ""

    researcher.sync_reference_sheet(tmp_path, tabs=(("TRANH_CAI_MXH", 728612942),), fetcher=fake_fetcher)
    sent, send_fn = _capture_sends()
    state = telegram_bot.load_state(tmp_path)

    for text in ("/status", "/inbox", f"/project {slug}"):
        telegram_bot.handle_update(
            tmp_path,
            state,
            {"update_id": 50, "message": {"message_id": 5, "chat": {"id": 555001}, "text": text}},
            req=lambda *a, **k: {"ok": True},
            send_fn=send_fn,
            typing=False,
        )

    assert "Trạng thái Xưởng PYH" in sent[0]["text"]
    assert "Hộp chủ đề chờ duyệt" in sent[1]["text"]
    assert state["active_slug"] == slug
    assert f"chuyển ngữ cảnh chat sang project: {slug}" in sent[2]["text"]

    # Click promote callback from /inbox reply
    inbox_buttons = [btn for row in sent[1]["reply_markup"]["inline_keyboard"] for btn in row]
    prm_cb = next(btn["callback_data"] for btn in inbox_buttons if btn["callback_data"].startswith("prm:"))
    assert len(prm_cb.encode("utf-8")) <= 64

    telegram_bot.handle_update(
        tmp_path,
        state,
        {
            "update_id": 51,
            "callback_query": {"id": "cb-prm", "data": prm_cb, "message": {"message_id": 6, "chat": {"id": 555001}}},
        },
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        typing=False,
    )
    assert len(load_queue(tmp_path)) == 1
    assert "hàng đợi sản xuất" in sent[-1]["text"]

    telegram_bot.handle_update(
        tmp_path,
        state,
        {"update_id": 52, "message": {"message_id": 7, "chat": {"id": 555001}, "text": "/chung"}},
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        typing=False,
    )
    assert state["active_slug"] is None


def test_lock_and_offset_priming_and_start_env_isolation(tmp_path: Path, monkeypatch):
    _setup_env(monkeypatch, "555001")
    with (
        telegram_bot.TelegramBotLock(tmp_path),
        pytest.raises(telegram_bot.TelegramBotAlreadyRunning),
        telegram_bot.TelegramBotLock(tmp_path),
    ):
        pass

    state = telegram_bot.load_state(tmp_path)
    state = telegram_bot.prime_offset_if_needed(
        tmp_path,
        state,
        req=lambda m, p, **k: {"ok": True, "result": [{"update_id": 100}, {"update_id": 105}]},
    )
    assert state["offset"] == 106

    # start_background passes TELEGRAM_* into bot process while normal child_env keeps stripping them
    captured_env: dict = {}
    captured_kwargs: dict = {}

    class FakeProc:
        pid = 43210

        def poll(self):
            return None

    calls = 0

    def fake_popen(argv, *, env=None, **kwargs):
        nonlocal calls
        calls += 1
        captured_env.update(env or {})
        captured_kwargs.update(kwargs)
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(telegram_bot, "running_pid", lambda root: None if calls == 0 else 43210)
    assert telegram_bot.start_background(tmp_path) == 43210
    assert captured_env["TELEGRAM_BOT_TOKEN"] == "fake-token-123"
    assert captured_env["TELEGRAM_CHAT_ID"] == "555001"
    if sys.platform == "win32":
        flags = captured_kwargs["creationflags"]
        assert flags & subprocess.CREATE_NO_WINDOW
        assert not (flags & subprocess.DETACHED_PROCESS)


def test_send_text_splits_long_messages_and_keeps_markup_last(monkeypatch):
    _setup_env(monkeypatch, "555001")
    requests_made: list[dict] = []

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"ok": True, "result": {"message_id": len(requests_made)}}).encode("utf-8")

    def fake_transport(req, *, timeout):
        assert timeout == 10
        requests_made.append(json.loads(req.data.decode("utf-8")))
        return FakeResp()

    long_text = "\n".join(f"Dòng nội dung số {i}: kiểm tra chia đoạn dài" for i in range(180))
    markup = {"inline_keyboard": [[{"text": "OK", "callback_data": "act:status"}]]}
    res = telegram.send_text(long_text, reply_markup=markup, transport=fake_transport)
    assert res is not None
    assert len(requests_made) >= 2
    assert all(len(r["text"]) <= 3900 for r in requests_made)
    assert "reply_markup" not in requests_made[0]
    assert requests_made[-1]["reply_markup"] == markup


def test_configured_rejects_placeholder_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "<chat_id>")
    assert telegram.configured() is False

    monkeypatch.setenv("TELEGRAM_CHAT_ID", "555001")
    assert telegram.configured() is True


def test_send_video_clips_and_script_commands(tmp_path: Path, monkeypatch):
    _setup_env(monkeypatch, "555001")
    project = create_v2_project_fixture(tmp_path / "projects", state=WorkflowState.AWAITING_VIDEO_REVIEW)
    slug = project.name
    rev = project / "revisions/001"
    video_path = rev / "renders/video.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"0123456789")
    clip_path = rev / "renders/clips/short-01.mp4"
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"clip-bytes")
    write_yaml_atomic(
        rev / "script/script.yaml",
        {"lines": [{"id": "N01", "text": "Uống đủ nước mỗi ngày rất tốt", "claim_id": "C01"}]},
    )
    write_yaml_atomic(
        rev / "evidence/ledger.yaml",
        {"claims": [{"id": "C01", "text_public": "Nước lọc giúp chuyển hóa"}], "records": [{"id": "R01"}]},
    )
    write_yaml_atomic(rev / "posts/posts.yaml", {"title": "Nước uống buổi sáng"})

    sent, send_fn = _capture_sends()
    videos: list[dict] = []

    def fake_send_video(path, *, caption="", reply_markup=None, chat_id=None, **kw):
        videos.append({"path": Path(path), "caption": caption, "reply_markup": reply_markup, "chat_id": chat_id})
        return {"ok": True, "result": {"message_id": len(videos)}}

    state = telegram_bot.load_state(tmp_path)
    for cmd in (f"/video {slug}", f"/clips {slug}", f"/script {slug}"):
        telegram_bot.handle_update(
            tmp_path,
            state,
            {"update_id": 70, "message": {"message_id": 70, "chat": {"id": 555001}, "text": cmd}},
            req=lambda *a, **k: {"ok": True},
            send_fn=send_fn,
            send_video_fn=fake_send_video,
            typing=False,
        )

    assert len(videos) == 2
    assert videos[0]["path"] == video_path
    assert slug in videos[0]["caption"]
    assert videos[1]["path"] == clip_path
    assert "N01 (C01): Uống đủ nước mỗi ngày rất tốt" in sent[0]["text"]

    # Large video (> _MAX_TELEGRAM_VIDEO_BYTES) invokes ffmpeg preview transcoder
    monkeypatch.setattr(telegram_bot, "_MAX_TELEGRAM_VIDEO_BYTES", 5)
    ffmpeg_calls: list[list[str]] = []

    def fake_runner(argv, **kwargs):
        ffmpeg_calls.append(argv)
        Path(argv[-1]).write_bytes(b"small")

    preview = telegram_bot.prepare_telegram_video(tmp_path, project, video_path, runner=fake_runner)
    assert len(ffmpeg_calls) == 1
    assert preview.exists() and preview != video_path


def test_telegram_duyet_gates_with_pin_auto_delete_and_card_toggle(tmp_path: Path, monkeypatch):
    from healthvideo.approver_pin import set_pin
    from healthvideo.workflows import dashboard

    _setup_env(monkeypatch, "555001")
    pin_file = tmp_path / "approver-pin.json"
    set_pin("123456", path=pin_file)
    monkeypatch.setattr(dashboard, "pin_path", lambda: pin_file)
    monkeypatch.setattr(dashboard, "reviewer_name", lambda: "BS An")
    monkeypatch.setattr(telegram_bot.factory, "start_background", lambda root: 99999)
    monkeypatch.setattr(telegram_bot._PIN_LIMITER, "failures", 0)
    monkeypatch.setattr(telegram_bot._PIN_LIMITER, "locked_until", 0.0)

    deleted_ids: list[int | str] = []

    def fake_delete(msg_id, *, chat_id=None, transport=None):
        deleted_ids.append(msg_id)
        return True

    # 1. Medical gate approve flow
    root1 = tmp_path / "med"
    med_project = create_v2_project_fixture(root1 / "projects", state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    med_slug = med_project.name
    sent, send_fn = _capture_sends()
    state = telegram_bot.load_state(root1)

    telegram_bot.handle_update(
        root1,
        state,
        {"update_id": 80, "message": {"message_id": 80, "chat": {"id": 555001}, "text": f"/duyet {med_slug}"}},
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        delete_fn=fake_delete,
        typing=False,
    )
    buttons = [btn for row in sent[-1]["reply_markup"]["inline_keyboard"] for btn in row]
    approve_cb = next(btn["callback_data"] for btn in buttons if btn["text"].startswith("✅ Duyệt cổng"))
    assert len(approve_cb.encode("utf-8")) <= 64

    telegram_bot.handle_update(
        root1,
        state,
        {
            "update_id": 81,
            "callback_query": {"id": "cb-med", "data": approve_cb, "message": {"message_id": 81, "chat": {"id": 555001}}},
        },
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        delete_fn=fake_delete,
        typing=False,
    )
    assert state["pending_gate_input"]["step"] == "await_pin"

    # Wrong PIN deletes message and keeps pending state active
    telegram_bot.handle_update(
        root1,
        state,
        {"update_id": 82, "message": {"message_id": 201, "chat": {"id": 555001}, "text": "999999"}},
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        delete_fn=fake_delete,
        typing=False,
    )
    assert 201 in deleted_ids
    assert "PIN không đúng" in sent[-1]["text"]
    assert state["pending_gate_input"] is not None

    # Correct PIN deletes message, approves gate, and never logs PIN to chat
    telegram_bot.handle_update(
        root1,
        state,
        {"update_id": 83, "message": {"message_id": 202, "chat": {"id": 555001}, "text": "123456"}},
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        delete_fn=fake_delete,
        typing=False,
    )
    assert 202 in deleted_ids
    assert state["pending_gate_input"] is None
    assert read_state(med_project) == WorkflowState.MEDICALLY_APPROVED
    assert (med_project / "revisions/001/reviews/medical-approval.yaml").is_file()
    assert not (med_project / "chat.jsonl").exists()

    # 2. Video gate decision card toggle + reject flow
    from datetime import UTC, datetime

    from healthvideo.workflows import product_review
    from tests.helpers import advance_v2_project_to_video_review

    root2 = tmp_path / "vid"
    vid_project = create_v2_project_fixture(root2 / "projects", state=WorkflowState.DRAFT_READY)
    advance_v2_project_to_video_review(vid_project, now=datetime(2026, 10, 22, tzinfo=UTC))
    vid_slug = vid_project.name
    state2 = telegram_bot.load_state(root2)
    write_yaml_atomic(
        vid_project / "revisions/001" / product_review.REPORT,
        {
            "scores": dict.fromkeys(product_review.CRITERIA, 8),
            "summary": "Synthetic passing product review with decision card.",
            "issues": [],
            "checked": ["Audio đạt chuẩn"],
            "decisions": [
                {
                    "id": "D1",
                    "where": "S01",
                    "question": "Giữ góc quay hiện tại?",
                    "why_hard": "Chữ nhỏ trên mobile",
                    "options": [
                        {"id": "a", "label": "Giữ nguyên", "effect": "keep", "keep": True, "recommended": True},
                        {"id": "b", "label": "Phóng to chữ", "effect": "Sửa hình S01", "keep": False},
                    ],
                }
            ],
        },
    )
    product_review.record_review(vid_project, product_review.render_hash(vid_project))
    telegram_bot.handle_update(
        root2,
        state2,
        {"update_id": 84, "message": {"message_id": 84, "chat": {"id": 555001}, "text": f"/duyet {vid_slug}"}},
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        delete_fn=fake_delete,
        typing=False,
    )
    vid_buttons = [btn for row in sent[-1]["reply_markup"]["inline_keyboard"] for btn in row]
    opt_b_cb = next(btn["callback_data"] for btn in vid_buttons if "D1·b" in btn["text"])
    telegram_bot.handle_update(
        root2,
        state2,
        {
            "update_id": 85,
            "callback_query": {"id": "cb-d1b", "data": opt_b_cb, "message": {"message_id": 85, "chat": {"id": 555001}}},
        },
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        delete_fn=fake_delete,
        typing=False,
    )
    toggled_buttons = [btn for row in sent[-1]["reply_markup"]["inline_keyboard"] for btn in row]
    assert any("Gửi sửa theo thẻ" in btn["text"] for btn in toggled_buttons)

    reject_cb = next(btn["callback_data"] for btn in toggled_buttons if "Dựng lại video" in btn["text"])
    telegram_bot.handle_update(
        root2,
        state2,
        {
            "update_id": 86,
            "callback_query": {"id": "cb-rej", "data": reject_cb, "message": {"message_id": 86, "chat": {"id": 555001}}},
        },
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        delete_fn=fake_delete,
        typing=False,
    )
    telegram_bot.handle_update(
        root2,
        state2,
        {"update_id": 87, "message": {"message_id": 203, "chat": {"id": 555001}, "text": "Nhạc nền hơi to"}},
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        delete_fn=fake_delete,
        typing=False,
    )
    telegram_bot.handle_update(
        root2,
        state2,
        {"update_id": 88, "message": {"message_id": 204, "chat": {"id": 555001}, "text": "123456"}},
        req=lambda *a, **k: {"ok": True},
        send_fn=send_fn,
        delete_fn=fake_delete,
        typing=False,
    )
    assert 204 in deleted_ids
    assert read_state(vid_project) == WorkflowState.NEEDS_PRODUCTION_REVISION
    assert not (vid_project / "chat.jsonl").exists()
