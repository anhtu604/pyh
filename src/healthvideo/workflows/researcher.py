"""Topic discovery, Google Sheet synchronization (THANG_DIEM 100-pt rubric) and dossier inbox."""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import yaml

from healthvideo.agents import invoke_with_failover
from healthvideo.company import load_company, role_skill_block
from healthvideo.domain.queue import QueueEntry
from healthvideo.domain.topic import RubricScore100, TopicCard, TopicDossier
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.queue import add_to_queue, load_queue

DEFAULT_SHEET_ID = "1e-WrbZP062LSlNTF8rmpYuHYECgXI10n6HUtiOBfOXg"
TOPIC_SHEET_TABS: tuple[tuple[str, int], ...] = (
    ("TRANH_CAI_MXH", 728612942),
    ("Y_HOC_MOI", 50745631),
    ("Trang tính1", 0),
)
INBOX_DIR = Path("topics/inbox")
INBOX_INDEX = INBOX_DIR / "index.yaml"

_DIACRITIC_TRANS = str.maketrans("đĐ", "dD")


def slugify_vi(text: str, *, max_len: int = 60) -> str:
    """Convert Vietnamese text into a clean ASCII kebab-case slug (<= max_len)."""
    replaced = text.translate(_DIACRITIC_TRANS)
    decomposed = unicodedata.normalize("NFKD", replaced)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("-")
    if len(cleaned) < 3:
        return "chu-de-y-hoc"
    return cleaned


def _parse_ratio_5(value: str | None, default: float = 3.0) -> float:
    if not value:
        return default
    raw = str(value).strip()
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*/\s*5", raw)
    if match:
        return max(0.0, min(5.0, float(match.group(1).replace(",", "."))))
    num = re.search(r"(\d+(?:[.,]\d+)?)", raw)
    if num:
        val = float(num.group(1).replace(",", "."))
        return max(0.0, min(5.0, val if val <= 5.0 else val / 2.0))
    return default


def _extract_labeled_scores(raw: str) -> dict[str, float]:
    """Parse ``Phòng bệnh: 5/5 | Bằng chứng: 5/5 | ...`` cells in Trang tính1."""
    found: dict[str, float] = {}
    if not raw:
        return found
    for chunk in str(raw).split("|"):
        if ":" not in chunk:
            continue
        label, val = chunk.split(":", 1)
        found[label.strip().lower()] = _parse_ratio_5(val, default=3.0)
    return found


def score_sheet_row(tab: str, row: dict[str, str]) -> RubricScore100:
    """Compute a deterministic 100-point rubric score matching sheet THANG_DIEM."""
    if tab == "TRANH_CAI_MXH":
        tranh_cai = _parse_ratio_5(row.get("điểm_tranh_cãi"), 3.0)
        giao_duc = _parse_ratio_5(row.get("điểm_giáo_dục"), 3.0)
        chac_chan = _parse_ratio_5(row.get("độ_chắc_chắn"), 3.0)
        video = _parse_ratio_5(row.get("khả_năng_video"), 3.0)
        has_pmid = bool((row.get("PMID_DOI") or row.get("nguồn_bằng_chứng") or "").strip())
        has_hook = bool((row.get("hook_trung_lập") or "").strip())
        viral = round((tranh_cai * 4.5 + video * 3.5) * (1.0 if has_hook else 0.92))
        urgency = round(giao_duc * 5.0)
        evidence = round(chac_chan * (4.0 if has_pmid else 3.2))
        short = round(video * 3.0)
    elif tab == "Y_HOC_MOI":
        do_moi = _parse_ratio_5(row.get("điểm_độ_mới"), 3.0)
        tin_cay = _parse_ratio_5(row.get("điểm_tin_cậy"), 3.0)
        thuc_hanh = _parse_ratio_5(row.get("điểm_thực_hành"), 3.0)
        video = _parse_ratio_5(row.get("khả_năng_video"), 3.0)
        has_ref = bool((row.get("DOI") or row.get("PMID") or row.get("url_gốc") or "").strip())
        viral = round(do_moi * 4.0 + video * 4.0)
        urgency = round(thuc_hanh * 5.0)
        evidence = round(tin_cay * (4.0 if has_ref else 3.2))
        short = round(video * 3.0)
    else:  # Trang tính1 or generic tab
        labeled = _extract_labeled_scores(row.get("Điểm đánh giá (1-5)", ""))
        phong_benh = labeled.get("phòng bệnh", 3.5)
        bang_chung = labeled.get("bằng chứng", 3.5)
        ro_khi_ke = labeled.get("rõ khi kể", 3.5)
        nguy_co = labeled.get("nguy cơ thông tin sai", 3.5)
        chi_phi = labeled.get("chi phí", 2.0)  # 1/5 = thấp (tốt) -> 5/5 = cao (tốn)
        uu_tien = (row.get("Ưu tiên") or "").lower()
        boost = 2.0 if "ưu tiên số 1" in uu_tien else (1.0 if "tiềm năng" in uu_tien else 0.0)
        viral = round(ro_khi_ke * 4.5 + phong_benh * 3.2 + boost)
        urgency = round(nguy_co * 3.0 + phong_benh * 2.0)
        evidence = round(bang_chung * 4.0)
        low_cost_bonus = max(0.0, 5.0 - chi_phi)
        short = round(ro_khi_ke * 2.1 + low_cost_bonus * 1.1)

    return RubricScore100(
        viral_engagement=max(0, min(40, int(viral))),
        urgency_prevention=max(0, min(25, int(urgency))),
        evidence_readiness=max(0, min(20, int(evidence))),
        short_feasibility=max(0, min(15, int(short))),
    )


def default_csv_fetcher(url: str, *, timeout: float = 20.0) -> str:
    """Fetch UTF-8 CSV from Google Sheets public export URL."""
    request = Request(url, headers={"User-Agent": "ProtectYourHealth-Researcher/2.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except URLError as exc:
        raise RuntimeError(f"Không tải được Google Sheet ({exc.reason}).") from exc
    return raw.decode("utf-8-sig", errors="replace")


def parse_csv_rows(csv_text: str) -> list[dict[str, str]]:
    """Parse CSV text into normalized stripped key/value dicts."""
    reader = csv.DictReader(io.StringIO(csv_text))
    rows: list[dict[str, str]] = []
    for raw_row in reader:
        cleaned = {
            (k or "").strip(): (v or "").strip()
            for k, v in raw_row.items()
            if k and str(k).strip()
        }
        if any(cleaned.values()):
            rows.append(cleaned)
    return rows


def fetch_sheet_csv(
    spreadsheet_id: str,
    gid: int,
    *,
    fetcher: Callable[[str], str] = default_csv_fetcher,
) -> list[dict[str, str]]:
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"
    return parse_csv_rows(fetcher(url))


def _row_to_dossier(
    tab: str,
    row_index: int,
    row: dict[str, str],
    *,
    existing_slugs: set[str],
    now: datetime,
) -> TopicDossier | None:
    if tab == "TRANH_CAI_MXH":
        statement = row.get("phát_ngôn", "")
        hook = row.get("hook_trung_lập", "")
        title = (hook or statement)[:140].strip()
        question = (row.get("câu_hỏi_kiểm_chứng") or statement).strip()
        claim_text = statement
        signal = f"{row.get('nguồn_tín_hiệu', '')} ({row.get('tương_tác', '')})".strip(" ()")
        source_url = row.get("url_gốc", "")
        pmid_doi = row.get("PMID_DOI") or row.get("nguồn_bằng_chứng", "")
        verdict = row.get("phán_quyết_sơ_bộ", "")
        nuance = " | ".join(
            part
            for part in (
                f"Đúng: {row['phần_đúng']}" if row.get("phần_đúng") else "",
                f"Sai/thiếu: {row['phần_sai_thiếu']}" if row.get("phần_sai_thiếu") else "",
                f"Ngoại lệ: {row['ngoại_lệ']}" if row.get("ngoại_lệ") else "",
                f"Nguy cơ: {row['nguy_cơ']}" if row.get("nguy_cơ") else "",
            )
            if part
        )
        doctor_pts = row.get("điểm_cần_bác_sĩ_duyệt", "")
        rec_date = row.get("ngày_chạy", "")
        rec_format = "vertical_clip"
        target_s = 75
    elif tab == "Y_HOC_MOI":
        title = (row.get("tiêu_đề_Việt") or row.get("hook_không_giật_gân", ""))[:140].strip()
        question = (row.get("câu_hỏi_nghiên_cứu") or title).strip()
        hook = row.get("hook_không_giật_gân", "")
        claim_text = row.get("kết_quả_chính", "")
        signal = f"{row.get('thiết_kế', '')} · {row.get('quần_thể', '')}".strip(" ·")
        source_url = row.get("url_gốc", "")
        pmid_doi = " / ".join(p for p in (row.get("PMID", ""), row.get("DOI", "")) if p)
        verdict = row.get("ý_nghĩa_thực_tế", "")
        nuance = " | ".join(
            part
            for part in (
                f"Chưa CM: {row['chưa_chứng_minh_được']}" if row.get("chưa_chứng_minh_được") else "",
                f"Hạn chế: {row['hạn_chế']}" if row.get("hạn_chế") else "",
            )
            if part
        )
        doctor_pts = row.get("cảnh_báo_diễn_giải", "")
        rec_date = row.get("ngày_chạy", "")
        rec_format = "both"
        target_s = 90
    else:
        hook = row.get("Chủ đề / Hook 1 câu", "")
        title = hook[:140].strip()
        question = (row.get("Câu hỏi y khoa trung tính") or row.get("Hiểu lầm / Câu hỏi công chúng") or title).strip()
        claim_text = row.get("Hiểu lầm / Câu hỏi công chúng", "")
        signal = row.get("Tín hiệu công khai (Nguồn, URL, Ngày)", "")
        source_url = ""
        url_match = re.search(r"https?://\S+", signal)
        if url_match:
            source_url = url_match.group(0).rstrip(").,;")
        pmid_doi = row.get("Bằng chứng y khoa (Nguồn, URL, PMID/DOI)", "")
        verdict = row.get("Phân định bằng chứng", "")
        nuance = row.get("Ưu tiên", "")
        doctor_pts = row.get("Điểm cần bác sĩ duyệt", "")
        rec_date = row.get("Ngày", "")
        rec_format = "both"
        target_s = 75

    if not title or not question:
        return None
    base_slug = slugify_vi(title)
    slug = base_slug
    counter = 2
    while slug in existing_slugs:
        suffix = f"-{counter}"
        slug = f"{base_slug[: max(3, 60 - len(suffix))].rstrip('-')}{suffix}"
        counter += 1
    existing_slugs.add(slug)
    rubric = score_sheet_row(tab, row)
    return TopicDossier(
        slug=slug,
        title=title,
        question=question,
        origin="google_sheet",
        source_tab=tab,
        source_row=row_index,
        recorded_date=rec_date,
        claim_or_headline=claim_text,
        source_signal=signal,
        source_url=source_url,
        pmid_doi=pmid_doi,
        preliminary_verdict=verdict,
        nuance_notes=nuance,
        doctor_review_points=doctor_pts,
        neutral_hook=hook or title,
        recommended_format=rec_format,
        target_seconds=target_s,
        rubric=rubric,
        synced_at=now,
    )


def _dossier_path(root: Path, slug: str) -> Path:
    return root / INBOX_DIR / f"{slug}.dossier.yaml"


def load_inbox(root: Path) -> list[dict[str, Any]]:
    """Load all topic dossiers in topics/inbox ordered by rubric score desc."""
    inbox_dir = root / INBOX_DIR
    if not inbox_dir.is_dir():
        return []
    queued = {entry.slug for entry in load_queue(root)}
    existing_projects = {
        path.parent.name for path in (root / "projects").glob("*/project.yaml")
    } if (root / "projects").is_dir() else set()
    items: list[dict[str, Any]] = []
    for path in sorted(inbox_dir.glob("*.dossier.yaml")):
        try:
            dossier = TopicDossier.model_validate(read_yaml(path))
        except (OSError, TypeError, ValueError, yaml.YAMLError):
            continue
        item = dossier.model_dump(mode="json")
        item["queued"] = dossier.slug in queued
        item["in_project"] = dossier.slug in existing_projects
        items.append(item)
    items.sort(key=lambda d: (-int(d.get("rubric_total", 0)), str(d.get("slug", ""))))
    return items


def _write_inbox_index(root: Path, items: list[dict[str, Any]], *, now: datetime) -> None:
    summary = {
        "version": 1,
        "updated_at": now.isoformat(timespec="seconds"),
        "total": len(items),
        "tier_a": sum(1 for it in items if it.get("tier") == "A"),
        "tier_b": sum(1 for it in items if it.get("tier") == "B"),
        "tier_c": sum(1 for it in items if it.get("tier") == "C"),
        "entries": [
            {
                "slug": it["slug"],
                "title": it["title"],
                "tier": it["tier"],
                "rubric_total": it["rubric_total"],
                "source_tab": it.get("source_tab", ""),
                "origin": it.get("origin", "google_sheet"),
                "status": it.get("status", "inbox"),
                "recommended_format": it.get("recommended_format", "both"),
            }
            for it in items
        ],
    }
    write_yaml_atomic(root / INBOX_INDEX, summary)


def inbox_summary(root: Path) -> dict[str, int]:
    items = load_inbox(root)
    return {
        "total": len(items),
        "tier_a": sum(1 for it in items if it.get("tier") == "A" and it.get("status") == "inbox"),
        "tier_b": sum(1 for it in items if it.get("tier") == "B" and it.get("status") == "inbox"),
        "tier_c": sum(1 for it in items if it.get("tier") == "C" and it.get("status") == "inbox"),
    }


def save_dossier(root: Path, dossier: TopicDossier) -> Path:
    path = _dossier_path(root, dossier.slug)
    write_yaml_atomic(path, dossier.model_dump(mode="json"))
    return path


def get_dossier(root: Path, slug: str) -> TopicDossier:
    path = _dossier_path(root, slug)
    if not path.is_file():
        raise LookupError(f"Không tìm thấy hồ sơ đề xuất {slug!r}.")
    return TopicDossier.model_validate(read_yaml(path))


def sync_reference_sheet(
    root: Path,
    *,
    spreadsheet_id: str = DEFAULT_SHEET_ID,
    tabs: tuple[tuple[str, int], ...] = TOPIC_SHEET_TABS,
    fetcher: Callable[[str], str] = default_csv_fetcher,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> dict[str, Any]:
    """Pull topics from the read-only doctor Google Sheet, score via THANG_DIEM, and store inbox dossiers."""
    current_now = now()
    existing_by_source: dict[tuple[str, int], TopicDossier] = {}
    used_slugs: set[str] = set()
    for raw in load_inbox(root):
        try:
            d = TopicDossier.model_validate({
                k: v for k, v in raw.items() if k not in {"queued", "in_project"}
            })
        except ValueError:
            continue
        used_slugs.add(d.slug)
        if d.source_tab and d.source_row is not None:
            existing_by_source[(d.source_tab, d.source_row)] = d

    synced = 0
    errors: list[str] = []
    for tab_name, gid in tabs:
        try:
            rows = fetch_sheet_csv(spreadsheet_id, gid, fetcher=fetcher)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{tab_name}: {exc}")
            continue
        for idx, row in enumerate(rows, start=2):
            prior = existing_by_source.get((tab_name, idx))
            if prior is not None:
                # Recompute rubric & metadata while keeping doctor's inbox decision and slug stable.
                candidate = _row_to_dossier(
                    tab_name, idx, row, existing_slugs=set(), now=current_now,
                )
                if candidate is None:
                    continue
                updated = candidate.model_copy(
                    update={
                        "slug": prior.slug,
                        "status": prior.status,
                        "rejection_reason": prior.rejection_reason,
                    }
                )
                save_dossier(root, updated)
                synced += 1
            else:
                created = _row_to_dossier(
                    tab_name, idx, row, existing_slugs=used_slugs, now=current_now,
                )
                if created is not None:
                    save_dossier(root, created)
                    synced += 1

    items = load_inbox(root)
    _write_inbox_index(root, items, now=current_now)
    return {
        "spreadsheet_id": spreadsheet_id,
        "synced_count": synced,
        "total": len(items),
        "tier_a": sum(1 for it in items if it.get("tier") == "A"),
        "tier_b": sum(1 for it in items if it.get("tier") == "B"),
        "tier_c": sum(1 for it in items if it.get("tier") == "C"),
        "errors": errors,
        "items": items,
    }


def promote_inbox_topic(root: Path, slug: str, *, doctor_note: str | None = None) -> dict[str, Any]:
    """Promote an inbox topic into topics/queue.yaml (doctor/Leader choice A4)."""
    dossier = get_dossier(root, slug)
    note_parts: list[str] = []
    if doctor_note and doctor_note.strip():
        note_parts.append(doctor_note.strip())
    if dossier.doctor_review_points:
        note_parts.append(f"Lưu ý từ nghiên cứu: {dossier.doctor_review_points}")
    if dossier.pmid_doi:
        note_parts.append(f"Tham khảo ban đầu: {dossier.pmid_doi}")
    if dossier.recommended_format == "vertical_clip":
        note_parts.append(f"Đề xuất định dạng: Shorts 9:16 (~{dossier.target_seconds}s)")
    combined_note = " | ".join(note_parts) if note_parts else None
    entry = QueueEntry(
        slug=dossier.slug,
        title=dossier.title,
        question=dossier.question,
        doctor_note=combined_note,
        added=datetime.now().astimezone().date(),
    )
    add_to_queue(root, entry)
    updated = dossier.model_copy(update={"status": "selected", "rejection_reason": None})
    save_dossier(root, updated)
    _write_inbox_index(root, load_inbox(root), now=datetime.now().astimezone())
    return {"entry": entry.model_dump(mode="json"), "dossier": updated.model_dump(mode="json")}


def reject_inbox_topic(root: Path, slug: str, *, reason: str = "") -> dict[str, Any]:
    dossier = get_dossier(root, slug)
    updated = dossier.model_copy(update={"status": "rejected", "rejection_reason": reason or "Bác sĩ bỏ qua"})
    save_dossier(root, updated)
    _write_inbox_index(root, load_inbox(root), now=datetime.now().astimezone())
    return updated.model_dump(mode="json")


def build_topic_card_from_dossier(dossier: TopicDossier) -> TopicCard:
    return TopicCard(
        slug=dossier.slug,
        title=dossier.title,
        question=dossier.question,
        scores=dossier.rubric.to_topic_scores(),
        status=dossier.status,
        rejection_reason=dossier.rejection_reason,
        created_at=dossier.synced_at,
        origin=dossier.origin,
    )


def discover_topics_with_agent(
    root: Path,
    *,
    query: str = "",
    count: int = 5,
    invoke=invoke_with_failover,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> dict[str, Any]:
    """Ask the `researcher` agent to proactively search/propose scored health topics."""
    from healthvideo.workflows.runner import HARD_RULES

    current_now = now()
    log_dir = root / "topics/logs/researcher"
    log_dir.mkdir(parents=True, exist_ok=True)
    report_path = log_dir / f"discover-{current_now:%Y%m%dT%H%M%S}.yaml"
    report_path.unlink(missing_ok=True)

    existing_slugs = {item["slug"] for item in load_inbox(root)}
    existing_slugs.update(entry.slug for entry in load_queue(root))
    insights_file = root / "topics/channel-insights.yaml"
    insights = read_yaml(insights_file) if insights_file.is_file() else {}

    company = load_company()
    skills_block = role_skill_block("researcher", company)
    payload = {
        "query": query or "chủ đề sức khỏe dự phòng phổ biến cho người Việt Nam",
        "requested_count": max(1, min(10, int(count))),
        "existing_slugs": sorted(existing_slugs)[:120],
        "channel_insights_summary": insights.get("summary", ""),
        "channel_winning_patterns": insights.get("winning_patterns", []),
        "channel_audience_questions": insights.get("audience_questions", []),
    }
    prompt = (
        "# Nhiệm vụ Researcher: Tìm & Chấm điểm Chủ đề Mới (`topic_research`)\n\n"
        f"Ghi kết quả duy nhất vào `{report_path}` dạng YAML có khóa `topics: [...]`.\n"
        "Mỗi mục gồm: `title`, `question`, `claim_or_headline`, `source_signal`, `source_url`, "
        "`pmid_doi`, `preliminary_verdict`, `nuance_notes`, `doctor_review_points`, `neutral_hook`, "
        "`recommended_format` (`youtube_long` | `vertical_clip` | `both`), `target_seconds`, "
        "và `rubric` (`viral_engagement` 0..40, `urgency_prevention` 0..25, "
        "`evidence_readiness` 0..20, `short_feasibility` 0..15).\n\n"
        f"Dữ liệu đầu vào JSON:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"{skills_block}\n"
        "## Quy tắc cứng\n" + "\n".join(f"- {rule}" for rule in HARD_RULES) + "\n"
    )
    result = invoke(
        company.chain("researcher"),
        prompt,
        cwd=root,
        log_dir=log_dir,
        role="researcher",
        slug="chung",
        step="topic_research",
    )
    if not result.ok:
        raise RuntimeError("Researcher chưa hoàn thành tìm kiếm đề tài.")
    raw = read_yaml(report_path) if report_path.is_file() else {}
    entries = raw.get("topics", []) if isinstance(raw, dict) else []
    if not isinstance(entries, list):
        raise TypeError("Researcher trả về topics không hợp lệ.")

    created: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        question = str(item.get("question") or "").strip()
        if not title or not question:
            continue
        base_slug = slugify_vi(str(item.get("slug") or title))
        slug = base_slug
        n = 2
        while slug in existing_slugs:
            suffix = f"-{n}"
            slug = f"{base_slug[: max(3, 60 - len(suffix))].rstrip('-')}{suffix}"
            n += 1
        existing_slugs.add(slug)
        rubric = RubricScore100.model_validate(item.get("rubric") or {})
        dossier = TopicDossier(
            slug=slug,
            title=title,
            question=question,
            origin="researcher_agent",
            source_tab="RESEARCHER_AI",
            recorded_date=current_now.date().isoformat(),
            claim_or_headline=str(item.get("claim_or_headline") or ""),
            source_signal=str(item.get("source_signal") or ""),
            source_url=str(item.get("source_url") or ""),
            pmid_doi=str(item.get("pmid_doi") or ""),
            preliminary_verdict=str(item.get("preliminary_verdict") or ""),
            nuance_notes=str(item.get("nuance_notes") or ""),
            doctor_review_points=str(item.get("doctor_review_points") or ""),
            neutral_hook=str(item.get("neutral_hook") or title),
            recommended_format=item.get("recommended_format") or "both",
            target_seconds=int(item.get("target_seconds") or 75),
            rubric=rubric,
            synced_at=current_now,
        )
        save_dossier(root, dossier)
        created.append(dossier.model_dump(mode="json"))

    items = load_inbox(root)
    _write_inbox_index(root, items, now=current_now)
    return {"added_count": len(created), "added": created, "total": len(items)}
