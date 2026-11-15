"""Offline tests for channel performance tracking and Researcher analytics."""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from healthvideo.agents import AgentResult
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import channel_analytics, researcher

NOW = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)


def test_import_csv_upsert_and_channel_overview_payload(tmp_path: Path):
    csv_text = (
        "slug,nền_tảng,tiêu_đề_đăng,lượt_xem,ctr_pct,giữ_chân_30s_pct,xem_trung_bình_pct,lưu_chia_sẻ\n"
        "muoi-va-huyet-ap,youtube,Ăn mặn và huyết áp,12500,6.5,58.0,45.2,320\n"
        "shorts-nuoc-chanh,tiktok,Nước chanh sáng có thải độc?,24000,8.2,64.0,71.0,510\n"
    )
    imp = channel_analytics.import_channel_csv(tmp_path, csv_text, platform="youtube")
    assert imp == {"imported_count": 2, "total_videos": 2}

    ups = channel_analytics.upsert_video_metric(
        tmp_path,
        {
            "title": "Tăng uric máu âm thầm",
            "platform": "youtube",
            "views": 6000,
            "ctr_pct": 5.3,
            "retention_30s_pct": 52.0,
            "top_comments": "Khán giả hỏi nên ăn rau gì?",
        },
    )
    assert ups["total_videos"] == 3

    overview = channel_analytics.channel_overview_payload(tmp_path)
    assert overview["connected"] is False
    assert overview["analysis_ready"] is True
    assert overview["sources"] == ["csv", "manual"]
    assert overview["videos_count"] == 3
    assert overview["total_views"] == 42500
    assert overview["avg_ctr_pct"] == 6.67
    assert overview["avg_retention_30s_pct"] == 58.0
    assert len(overview["videos"]) == 3


def test_sync_channel_sheet_reports_missing_tab_gracefully(tmp_path: Path):
    def fake_runner(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps([
                {"sheetId": 728612942, "title": "TRANH_CAI_MXH"},
                {"sheetId": 50745631, "title": "Y_HOC_MOI"},
            ]),
            stderr="",
        )

    missing = channel_analytics.sync_channel_sheet(
        tmp_path,
        gsheets_runner=fake_runner,
    )
    assert missing["ok"] is False
    assert "KET_QUA_KENH" in missing["message"]

    def found_runner(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps([{"sheetId": 12345, "title": "KET_QUA_KENH"}]),
            stderr="",
        )

    def fake_fetcher(url: str) -> str:
        assert "gid=12345" in url
        return (
            "slug,nền_tảng,tiêu_đề_đăng,lượt_xem,ctr_pct,giữ_chân_30s_pct\n"
            "tap-the-duc,youtube,Đi bộ 4000 bước,9800,7.1,61.5\n"
        )

    synced = channel_analytics.sync_channel_sheet(
        tmp_path,
        gsheets_runner=found_runner,
        fetcher=fake_fetcher,
    )
    assert synced["ok"] is True
    assert synced["imported_count"] == 1
    assert synced["total_videos"] == 1


def test_analyze_channel_performance_saves_insights_and_seeds_inbox(tmp_path: Path):
    channel_analytics.upsert_video_metric(
        tmp_path,
        {
            "title": "Hiểu lầm nước chanh thải độc",
            "platform": "youtube",
            "views": 18000,
            "ctr_pct": 7.4,
            "retention_30s_pct": 63.0,
            "top_comments": "Hỏi về uống giấm táo giảm cân",
        },
    )

    def fake_invoke(slots, prompt, **kwargs):
        marker = "ghi kết quả duy nhất vào `"
        report_path = Path(prompt.split(marker, 1)[1].split("`", 1)[0])
        write_yaml_atomic(
            report_path,
            {
                "summary": "Video giải ngộ nhận 3 giây đầu giữ chân tốt hơn video lý thuyết.",
                "winning_patterns": ["Mở đầu bằng câu hỏi phản biện đạt retention 30s > 60%"],
                "dropoff_risks": ["Đoạn đọc số liệu dài làm tụt giữ chân"],
                "audience_questions": ["Giấm táo buổi sáng có hại dạ dày không?"],
                "packaging_tips": ["Giữ tiêu đề ngắn dưới 55 ký tự"],
                "recommended_topics": [
                    {
                        "title": "Giấm táo buổi sáng có giảm đường huyết thật không?",
                        "question": "Bằng chứng lâm sàng về giấm táo với đường huyết sau ăn?",
                        "recommended_format": "both",
                        "rubric": {
                            "viral_engagement": 34,
                            "urgency_prevention": 20,
                            "evidence_readiness": 17,
                            "short_feasibility": 13,
                        },
                    }
                ],
            },
        )
        return AgentResult("fake", True, False, kwargs["log_dir"] / "insights.log")

    out = channel_analytics.analyze_channel_performance(
        tmp_path,
        focus="Phân tích hook và bình luận",
        invoke=fake_invoke,
        now=lambda: NOW,
    )
    assert out["added_topics"] == 1
    assert (tmp_path / channel_analytics.INSIGHTS_FILE).is_file()
    stored = read_yaml(tmp_path / channel_analytics.INSIGHTS_FILE)
    assert "giải ngộ nhận" in stored["summary"]

    inbox_items = researcher.load_inbox(tmp_path)
    assert len(inbox_items) == 1
    assert inbox_items[0]["origin"] == "channel_analytics"
    assert inbox_items[0]["tier"] == "A"


@pytest.mark.parametrize("payload", [{}, {"title": "Metadata only"}])
def test_no_observations_never_invokes_agent(tmp_path, payload):
    if payload:
        channel_analytics.upsert_video_metric(tmp_path, payload)
    def forbidden(*args, **kwargs):
        pytest.fail("no data must not invoke researcher")
    with pytest.raises(ValueError, match="Chưa có số liệu"):
        channel_analytics.analyze_channel_performance(tmp_path, invoke=forbidden)


def test_explicit_zero_and_unknown_survive_roundtrip(tmp_path):
    channel_analytics.import_channel_csv(tmp_path, "title,views,ctr\nUnknown,,\nMeasured,0,0\n")
    records = {r.title_used: r for r in channel_analytics.load_metrics(tmp_path)}
    assert records["Unknown"].views is None
    assert records["Unknown"].metrics_observed == []
    assert records["Measured"].views == 0
    assert set(records["Measured"].metrics_observed) == {"views", "ctr_pct"}
    channel_analytics.save_metrics(tmp_path, list(records.values()))
    assert [r.metrics_observed for r in channel_analytics.load_metrics(tmp_path)] == [r.metrics_observed for r in records.values()]


@pytest.mark.parametrize("report", [None, "broken: [", {}, {"summary": " "},
    {"summary": "Findings", "recommended_topics": [{"title": "Next", "question": "Why?"}]},
    {"summary": "Findings", "recommended_topics": [{"title": "Next", "question": "Why?", "rubric": {"viral_engagement": 20}}]}])
def test_invalid_report_preserves_previous_insights(tmp_path, report):
    channel_analytics.upsert_video_metric(tmp_path, {"title": "Measured", "views": 0})
    previous = {"summary": "Previous evidence"}
    write_yaml_atomic(tmp_path / channel_analytics.INSIGHTS_FILE, previous)
    def invoke(slots, prompt, **kwargs):
        report_path = Path(prompt.split("ghi kết quả duy nhất vào `", 1)[1].split("`", 1)[0])
        assert '"views": 1' in prompt
        assert 'Missing metrics are unknown' in prompt
        if isinstance(report, str):
            report_path.write_text(report, encoding="utf-8")
        elif report is not None:
            write_yaml_atomic(report_path, report)
        return AgentResult("fake", True, False, kwargs["log_dir"] / "test.log")
    with pytest.raises((ValueError, yaml.YAMLError)):
        channel_analytics.analyze_channel_performance(tmp_path, invoke=invoke, now=lambda: NOW)
    assert read_yaml(tmp_path / channel_analytics.INSIGHTS_FILE) == previous
    assert researcher.load_inbox(tmp_path) == []


@pytest.mark.parametrize("platform,account_id,row", [
    ("youtube", "a", {"platform": "tiktok", "source_account_id": "a", "source": "youtube_api"}),
    ("youtube", "a", {"platform": "youtube", "source_account_id": "b", "source": "youtube_api"}),
    ("youtube", "", {"platform": "youtube", "source_account_id": "", "source": "youtube_api"}),
    ("youtube", "a", {"platform": "youtube", "source": "youtube_api"}),
    ("youtube", "a", {"platform": "youtube", "source_account_id": "a", "source": "manual"}),
])
def test_sync_account_and_platform_mismatch_preserves_store(tmp_path, platform, account_id, row):
    channel_analytics.upsert_video_metric(tmp_path, {"title": "Imported", "views": 7})
    before = (tmp_path / channel_analytics.METRICS_FILE).read_bytes()
    with pytest.raises(ValueError):
        channel_analytics.save_synced_metrics(tmp_path, {"platform": platform, "account_id": account_id,
            "records": [{"slug": "api-video", "views": 0, **row}]})
    assert (tmp_path / channel_analytics.METRICS_FILE).read_bytes() == before


def test_account_switch_retains_history_but_analyzes_current_account_and_imports(tmp_path, monkeypatch):
    from healthvideo.workflows import channel_connections
    monkeypatch.setattr(channel_connections, "connection_status", lambda root: {
        "youtube": {"connected": True, "account_id": "new"}, "tiktok": {"connected": False}})
    for account_id, views in (("old", 100), ("new", 0)):
        result = channel_analytics.save_synced_metrics(tmp_path, {"platform": "youtube", "account_id": account_id,
            "records": [{"slug": "same-video", "platform": "youtube", "views": views,
                         "source": "youtube_api", "source_account_id": account_id}]})
        assert result["account_id"] == account_id
    channel_analytics.upsert_video_metric(tmp_path, {"title": "Imported", "views": 4})
    assert len(channel_analytics.load_metrics(tmp_path)) == 3
    overview = channel_analytics.channel_overview_payload(tmp_path)
    assert overview["connected"] is True
    assert overview["analysis_ready"] is True
    assert overview["total_views"] == 4
    assert overview["excluded_account_records"] == 1
    assert overview["sources"] == ["manual", "youtube_api"]
    assert {item["account_id"] for item in overview["accounts"]} == {"", "new"}
    def invoke(slots, prompt, **kwargs):
        payload = json.loads(prompt.split("Dữ liệu video JSON:\n", 1)[1].split("\n\n", 1)[0])
        assert {record["source_account_id"] for record in payload["videos"]} == {"", "new"}
        assert payload["excluded_account_records"] == 1
        path = Path(prompt.split("ghi kết quả duy nhất vào `", 1)[1].split("`", 1)[0])
        write_yaml_atomic(path, {"summary": "Imported and current authorized account observations only"})
        return AgentResult("fake", True, False, kwargs["log_dir"] / "test.log")
    channel_analytics.analyze_channel_performance(tmp_path, invoke=invoke, now=lambda: NOW)


def test_disconnected_api_history_cannot_make_analysis_ready(tmp_path, monkeypatch):
    from healthvideo.workflows import channel_connections
    monkeypatch.setattr(channel_connections, "connection_status", lambda root: {"youtube": {"connected": False, "account_id": "old"}})
    channel_analytics.save_synced_metrics(tmp_path, {"platform": "youtube", "account_id": "old", "records": [
        {"slug": "old-video", "views": 10, "platform": "youtube", "source": "youtube_api", "source_account_id": "old"}]})
    overview = channel_analytics.channel_overview_payload(tmp_path)
    assert overview["analysis_ready"] is False
    assert overview["excluded_account_records"] == 1
    with pytest.raises(ValueError, match="Chưa có số liệu"):
        channel_analytics.analyze_channel_performance(tmp_path, invoke=lambda *a, **k: pytest.fail("must not invoke"))


@pytest.mark.parametrize("platform", ["youtube", "tiktok"])
def test_actual_provider_sync_payload_validates_and_preserves_measured_zero(tmp_path, monkeypatch, platform):
    from healthvideo.workflows import channel_connections
    monkeypatch.setattr(channel_connections, "access_token", lambda *a, **k: "test-token")
    monkeypatch.setattr(channel_connections, "connection_status", lambda root: {
        platform: {"connected": True, "account_id": "verified-account"}})
    def http(method, url, **kwargs):
        if platform == "tiktok":
            return {"data": {"videos": [{"id": "video-id", "view_count": 0, "share_count": 0}], "has_more": False}}
        if "/channels?" in url:
            return {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "uploads-id"}}}]}
        if "/playlistItems?" in url:
            return {"items": [{"contentDetails": {"videoId": "video-id"}}]}
        assert "/videos?" in url
        return {"items": [{"id": "video-id", "snippet": {"title": "Measured zero"}, "statistics": {"viewCount": "0"}}]}
    monkeypatch.setattr(channel_connections, "_http", http)
    payload = channel_connections.sync_connected_channel(tmp_path, platform)
    result = channel_analytics.save_synced_metrics(tmp_path, payload)
    assert result["account_id"] == "verified-account"
    assert result["imported_count"] == 1
    record = channel_analytics.load_metrics(tmp_path)[0]
    assert record.views == 0
    assert record.source_account_id == "verified-account"
    assert record.platform == platform
    assert "views" in record.metrics_observed
    assert record.ctr_pct is None
    assert channel_analytics.channel_overview_payload(tmp_path)["analysis_ready"] is True


@pytest.mark.parametrize("change", ["account", "measurement"])
def test_insights_provenance_invalidates_changed_dataset_without_deleting_report(tmp_path, monkeypatch, change):
    from healthvideo.workflows import channel_connections
    account = {"id": "old"}
    monkeypatch.setattr(channel_connections, "connection_status", lambda root: {
        "youtube": {"connected": True, "account_id": account["id"]}})
    channel_analytics.save_synced_metrics(tmp_path, {"platform": "youtube", "account_id": "old", "records": [
        {"slug": "api-video", "platform": "youtube", "source": "youtube_api", "source_account_id": "old", "views": 3}]})
    def invoke(slots, prompt, **kwargs):
        path = Path(prompt.split("ghi kết quả duy nhất vào `", 1)[1].split("`", 1)[0])
        write_yaml_atomic(path, {"summary": "Measured evidence", "dataset_fingerprint": "agent-spoof",
                                "data_sources": ["invented"], "source_accounts": [{"account_id": "spoof"}]})
        return AgentResult("fake", True, False, kwargs["log_dir"] / "test.log")
    channel_analytics.analyze_channel_performance(tmp_path, invoke=invoke, now=lambda: NOW)
    before = (tmp_path / channel_analytics.INSIGHTS_FILE).read_bytes()
    overview = channel_analytics.channel_overview_payload(tmp_path)
    assert overview["insights_status"] == "current"
    assert overview["insights_stale"] is False
    assert overview["insights"]["data_sources"] == ["youtube_api"]
    assert overview["insights"]["source_accounts"][0]["account_id"] == "old"
    assert overview["insights"]["dataset_fingerprint"] != "agent-spoof"
    if change == "account":
        account["id"] = "new"
    else:
        channel_analytics.save_synced_metrics(tmp_path, {"platform": "youtube", "account_id": "old", "records": [
            {"slug": "api-video", "platform": "youtube", "source": "youtube_api", "source_account_id": "old", "views": 4}]})
    overview = channel_analytics.channel_overview_payload(tmp_path)
    assert overview["insights_stale"] is True
    assert overview["insights_status"] == "stale"
    assert overview["insights"] is None
    assert overview["historical_insights"]["summary"] == "Measured evidence"
    assert (tmp_path / channel_analytics.INSIGHTS_FILE).read_bytes() == before


def test_legacy_insights_are_historical_unverified(tmp_path):
    channel_analytics.upsert_video_metric(tmp_path, {"title": "Measured", "views": 0})
    write_yaml_atomic(tmp_path / channel_analytics.INSIGHTS_FILE, {"summary": "Legacy report"})
    overview = channel_analytics.channel_overview_payload(tmp_path)
    assert overview["insights"] is None
    assert overview["insights_stale"] is True
    assert overview["insights_status"] == "historical_unverified"
    assert overview["historical_insights"]["summary"] == "Legacy report"


def test_dataset_fingerprint_stable_under_record_order():
    records = [channel_analytics.VideoPerformanceRecord(slug="b", views=0),
               channel_analytics.VideoPerformanceRecord(slug="a", ctr_pct=0)]
    assert channel_analytics._dataset_provenance(records) == channel_analytics._dataset_provenance(records[::-1])
