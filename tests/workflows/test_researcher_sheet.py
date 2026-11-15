"""Offline tests for Researcher Google Sheet sync, 100-pt rubric scoring, and inbox promotion."""

from datetime import UTC, datetime
from pathlib import Path

from healthvideo.agents import AgentResult
from healthvideo.domain.topic import RubricScore100
from healthvideo.storage.files import write_yaml_atomic
from healthvideo.storage.queue import load_queue
from healthvideo.workflows import researcher
from healthvideo.workflows.factory_deps import create_project

NOW = datetime(2026, 11, 15, 9, 30, tzinfo=UTC)


def test_rubric_score_tiers():
    tier_a = RubricScore100(viral_engagement=36, urgency_prevention=22, evidence_readiness=18, short_feasibility=14)
    assert tier_a.total == 90 and tier_a.tier == "A"

    tier_b = RubricScore100(viral_engagement=28, urgency_prevention=18, evidence_readiness=14, short_feasibility=10)
    assert tier_b.total == 70 and tier_b.tier == "B"

    tier_c = RubricScore100(viral_engagement=20, urgency_prevention=15, evidence_readiness=12, short_feasibility=8)
    assert tier_c.total == 55 and tier_c.tier == "C"


def test_sync_reference_sheet_scores_tabs_and_preserves_decisions(tmp_path: Path):
    tabs_csv = {
        "gid=728612942": (
            "ngày_chạy,nguồn_tín_hiệu,phát_ngôn,câu_hỏi_kiểm_chứng,tương_tác,điểm_tranh_cãi,"
            "điểm_giáo_dục,độ_chắc_chắn,khả_năng_video,phần_đúng,phần_sai_thiếu,ngoại_lệ,nguy_cơ,"
            "phán_quyết_sơ_bộ,nguồn_bằng_chứng,PMID_DOI,url_gốc,điểm_cần_bác_sĩ_duyệt,hook_trung_lập\n"
            "2026-11-14,TikTok,Uống nước chanh buổi sáng thải độc gan,Nước chanh có thải độc gan không?,"
            "120k,5/5,5/5,5/5,5/5,Bổ sung vitamin C,Không thay thế chức năng gan,Viêm loét dạ dày,,"
            "Sai một phần,PubMed,PMID 12345,https://example.com/1,Kiểm tra liều acid,Uống nước chanh sáng có thật sự thải độc gan?\n"
        ),
        "gid=50745631": (
            "ngày_chạy,tiêu_đề_Việt,câu_hỏi_nghiên_cứu,thiết_kế,quần_thể,kết_quả_chính,chưa_chứng_minh_được,"
            "hạn_chế,ý_nghĩa_thực_tế,điểm_độ_mới,điểm_tin_cậy,điểm_thực_hành,khả_năng_video,DOI,PMID,url_gốc,hook_không_giật_gân\n"
            "2026-11-14,Đi bộ 4000 bước mỗi ngày,Đi bộ bao nhiêu bước giúp giảm tử vong?,Cohort,Người lớn,"
            "Giảm rõ rệt nguy cơ tim mạch,Chưa khẳng định nguyên nhân,Quan sát,Khả thi hàng ngày,4/5,4/5,4/5,4/5,"
            "10.1000/test,PMID 999,https://example.com/2,4000 bước mỗi ngày mang lại lợi ích gì?\n"
        ),
        "gid=0": (
            "Ngày,Chủ đề / Hook 1 câu,Hiểu lầm / Câu hỏi công chúng,Câu hỏi y khoa trung tính,"
            "Tín hiệu công khai (Nguồn, URL, Ngày),Bằng chứng y khoa (Nguồn, URL, PMID/DOI),Phân định bằng chứng,"
            "Điểm cần bác sĩ duyệt,Điểm đánh giá (1-5),Ưu tiên\n"
            "2026-11-14,Ngủ bù cuối tuần có hết mệt?,Ngủ bù bù cho cả tuần thiếu ngủ,Ngủ bù có khôi phục thiếu ngủ mạn?,"
            "https://example.com/3,PMID 555,Thiếu cơ sở,Xem nhóm thiếu ngủ nặng,"
            "Phòng bệnh: 2/5 | Bằng chứng: 3/5 | Rõ khi kể: 3/5 | Nguy cơ thông tin sai: 2/5 | Chi phí: 4/5,Thấp\n"
        ),
    }

    def fake_fetcher(url: str) -> str:
        for marker, content in tabs_csv.items():
            if marker in url:
                return content
        return ""

    res1 = researcher.sync_reference_sheet(tmp_path, fetcher=fake_fetcher, now=lambda: NOW)
    assert res1["synced_count"] == 3
    assert res1["total"] == 3
    assert res1["tier_a"] >= 1

    items = researcher.load_inbox(tmp_path)
    assert items[0]["source_tab"] == "TRANH_CAI_MXH"
    assert items[0]["tier"] == "A"
    assert items[0]["rubric_total"] >= 80
    first_slug = items[0]["slug"]

    # Doctor rejects one topic; re-syncing should preserve status and slug
    researcher.reject_inbox_topic(tmp_path, first_slug, reason="Trùng chủ đề cũ")
    res2 = researcher.sync_reference_sheet(tmp_path, fetcher=fake_fetcher, now=lambda: NOW)
    assert res2["synced_count"] == 3
    reloaded = researcher.get_dossier(tmp_path, first_slug)
    assert reloaded.status == "rejected"
    assert reloaded.rejection_reason == "Trùng chủ đề cũ"


def test_promote_inbox_topic_and_create_project_copies_dossier(tmp_path: Path):
    def fake_fetcher(url: str) -> str:
        if "gid=728612942" in url:
            return (
                "phát_ngôn,câu_hỏi_kiểm_chứng,điểm_tranh_cãi,điểm_giáo_dục,độ_chắc_chắn,khả_năng_video,"
                "PMID_DOI,điểm_cần_bác_sĩ_duyệt,hook_trung_lập\n"
                "Ăn tỏi sống chữa cao huyết áp,Tỏi sống có hạ huyết áp bền vững?,5/5,5/5,4/5,5/5,"
                "PMID 4242,Cần nêu rõ không bỏ thuốc,Tỏi có thay thuốc huyết áp được không?\n"
            )
        return ""

    res = researcher.sync_reference_sheet(tmp_path, fetcher=fake_fetcher, now=lambda: NOW)
    slug = res["items"][0]["slug"]

    promoted = researcher.promote_inbox_topic(tmp_path, slug, doctor_note="Nhấn mạnh tuân thủ thuốc.")
    assert promoted["dossier"]["status"] == "selected"

    entries = load_queue(tmp_path)
    assert [e.slug for e in entries] == [slug]
    assert "Nhấn mạnh tuân thủ thuốc." in (entries[0].doctor_note or "")

    project_dir = create_project(tmp_path, entries[0])
    copied = project_dir / "revisions/001/topic/dossier.yaml"
    assert copied.is_file()
    assert "PMID 4242" in copied.read_text(encoding="utf-8")


def test_discover_topics_with_agent_writes_scored_dossiers(tmp_path: Path):
    def fake_invoke(slots, prompt, **kwargs):
        # Prompt specifies exact report path for topics YAML output.
        marker = "Ghi kết quả duy nhất vào `"
        report_path = Path(prompt.split(marker, 1)[1].split("`", 1)[0])
        write_yaml_atomic(
            report_path,
            {
                "topics": [
                    {
                        "title": "Nhịn ăn gián đoạn 16:8 ở người tiền đái tháo đường",
                        "question": "Nhịn ăn 16:8 có cải thiện HbA1c an toàn không?",
                        "claim_or_headline": "16:8 giúp hạ cân nhưng không phù hợp mọi bệnh nhân",
                        "pmid_doi": "PMID 778899",
                        "recommended_format": "both",
                        "target_seconds": 90,
                        "rubric": {
                            "viral_engagement": 35,
                            "urgency_prevention": 21,
                            "evidence_readiness": 17,
                            "short_feasibility": 13,
                        },
                    }
                ]
            },
        )
        return AgentResult("fake", True, False, kwargs["log_dir"] / "discover.log")

    result = researcher.discover_topics_with_agent(
        tmp_path, query="tiền đái tháo đường", invoke=fake_invoke, now=lambda: NOW
    )
    assert result["added_count"] == 1
    dossier = result["added"][0]
    assert dossier["tier"] == "A"
    assert dossier["rubric_total"] == 86
    assert (tmp_path / "topics/inbox" / f"{dossier['slug']}.dossier.yaml").is_file()
