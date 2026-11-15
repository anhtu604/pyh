"""Channel actions use the same guarded adapters for every coordinator entrypoint."""

import sys
from types import SimpleNamespace

import pytest

from healthvideo.workflows import channel_analytics, chat


def test_channel_summary_keeps_readiness_distinct_from_connection(tmp_path, monkeypatch):
    data = {"connected": False, "analysis_ready": True, "data_available": True,
            "sources": ["manual"], "connections": {"youtube": {"connected": False}},
            "accounts": [], "excluded_account_records": 0, "analysis_reason": "Imported observations", "videos_count": 1, "total_views": 0}
    monkeypatch.setattr(channel_analytics, "channel_overview_payload", lambda root: data)
    assert chat._company_summary(tmp_path)["channel"] == data


@pytest.mark.parametrize("entrypoint", ["operation", "execute", "dispatch"])
def test_analysis_without_data_cannot_dispatch_researcher(tmp_path, monkeypatch, entrypoint):
    def forbidden(*args, **kwargs):
        pytest.fail("researcher must not run without measured data")
    # The analytics guard precedes the invocation irrespective of coordinator route.
    monkeypatch.setattr(channel_analytics, "invoke_with_failover", forbidden)
    message = {"action": "analyze_channel", "context": {}}
    with pytest.raises(ValueError, match="Chưa có số liệu"):
        if entrypoint == "operation":
            chat._execute_leader_operation(tmp_path, None, message, {})
        elif entrypoint == "execute":
            chat._execute(tmp_path, None, message)
        else:
            chat._execute_dispatch_reply(tmp_path, None, {"assignments": [message]})


def test_sync_validates_provider_records_before_save(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "healthvideo.workflows.channel_connections", SimpleNamespace(
        sync_connected_channel=lambda root, platform: {
            "platform": platform, "account_id": "account-a", "records": [{"slug": "measured", "platform": platform, "source_account_id": "account-a", "views": 0, "source": "youtube_api"}]}))
    result = chat._execute_leader_operation(tmp_path, None, {"action": "sync_channel", "platform": "youtube"}, {})
    assert result["result"]["imported_count"] == 1
    assert channel_analytics.load_metrics(tmp_path)[0].metrics_observed == ["views"]


def test_sync_invalid_response_preserves_metrics(tmp_path):
    channel_analytics.upsert_video_metric(tmp_path, {"title": "Existing", "views": 12})
    before = (tmp_path / channel_analytics.METRICS_FILE).read_bytes()
    with pytest.raises(ValueError):
        channel_analytics.save_synced_metrics(tmp_path, {"platform": "youtube", "records": [
            {"slug": "valid", "views": 1}, {"slug": "bad", "views": -1}]})
    assert (tmp_path / channel_analytics.METRICS_FILE).read_bytes() == before


def test_publish_only_prepares_preview_and_requires_app_confirmation(tmp_path, monkeypatch):
    called = []
    def publish(root, slug, **kwargs):
        called.append((root, slug, kwargs))
        return {"ok": True}
    monkeypatch.setitem(sys.modules, "healthvideo.workflows.channel_publishing", SimpleNamespace(publication_preview=publish, publish_approved=lambda *a, **k: pytest.fail("chat cannot upload")))
    reply = chat.CoordinatorReply.model_validate({"reply": "Đăng video đã duyệt", "action": "dispatch", "assignments": [{
        "role": "publisher", "step": "publish_video", "task": "Upload", "slug": "approved",
        "platform": "youtube", "clip_id": "CL01", "privacy": "private", "title_index": 1}]})
    item = reply.assignments[0].model_dump()
    assert item["action"] == "publish_video"
    result = chat._execute_leader_operation(tmp_path, None, item, {})
    assert result["needs_publication_confirmation"] is True
    assert result["requested_privacy"] == "private"
    assert "app" in result["message"]
    assert called == [(tmp_path, "approved", {"platform": "youtube", "clip_id": "CL01", "title_index": 1})]
    with pytest.raises(ValueError, match="privacy"):
        chat._execute_leader_operation(tmp_path, "approved", {"action": "publish_video", "platform": "youtube"}, {})
    assert len(called) == 1


def test_coordinator_explains_no_data_instead_of_assigning_researcher(tmp_path, monkeypatch):
    monkeypatch.setattr(channel_analytics, "channel_overview_payload", lambda root: {
        "analysis_ready": False, "analysis_reason": "Chưa có số liệu đo; nhập CSV hoặc kết nối tài khoản."})
    reply = chat.CoordinatorReply(reply="Đang giao researcher", action="dispatch", assignments=[
        chat.TaskAssignment(role="researcher", step="analyze_channel", task="Analyze")])
    guarded = chat._guard_channel_readiness(tmp_path, reply)
    assert guarded.action == "status"
    assert guarded.assignments == []
    assert "Chưa có số liệu" in guarded.reply
