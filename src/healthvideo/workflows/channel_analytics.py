"""Published video performance tracking and Researcher-driven channel analytics."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.agents import invoke_with_failover
from healthvideo.company import load_company, role_skill_block
from healthvideo.domain.topic import RubricScore100, TopicDossier
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.workflows.researcher import (
    DEFAULT_SHEET_ID,
    _write_inbox_index,
    default_csv_fetcher,
    load_inbox,
    parse_csv_rows,
    save_dossier,
    slugify_vi,
)

METRICS_FILE = Path("topics/channel-metrics.yaml")
INSIGHTS_FILE = Path("topics/channel-insights.yaml")
CHANNEL_CONFIG_FILE = Path("topics/channel-config.yaml")
CHANNEL_TAB_TITLE = "KET_QUA_KENH"
CHANNEL_SHEET_HEADERS = [
    "ngày_ghi",
    "slug",
    "nền_tảng",
    "url_video",
    "tiêu_đề_đăng",
    "ngày_đăng",
    "lượt_xem",
    "ctr_pct",
    "giữ_chân_30s_pct",
    "xem_trung_bình_pct",
    "lưu_chia_sẻ",
    "bình_luận_câu_hỏi_nổi_bật",
]


class VideoPerformanceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1)
    platform: Literal["youtube", "youtube_shorts", "tiktok", "facebook", "other"] = "youtube"
    url: str = ""
    title_used: str = ""
    published_at: str = ""
    views: int | None = Field(default=None, ge=0)
    ctr_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    retention_30s_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    avg_view_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    shares_saves: int | None = Field(default=None, ge=0)
    top_comments: str = ""
    recorded_at: str = ""
    source: str = "manual"
    source_account_id: str = ""
    metrics_observed: list[str] | None = None

    @model_validator(mode="after")
    def observed_fields(self):
        fields = ("views", "ctr_pct", "retention_30s_pct", "avg_view_pct", "shares_saves")
        if self.metrics_observed is None:
            self.metrics_observed = [key for key in fields if key in self.model_fields_set and getattr(self, key) is not None]
        elif any(key not in fields or getattr(self, key) is None for key in self.metrics_observed):
            raise ValueError("Invalid observed metric marker")
        return self


class ChannelInsights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    generated_at: str = ""
    summary: str = ""
    data_sources: list[str] = Field(default_factory=list)
    source_accounts: list[dict[str, str]] = Field(default_factory=list)
    dataset_fingerprint: str = ""
    winning_patterns: list[str] = Field(default_factory=list)
    dropoff_risks: list[str] = Field(default_factory=list)
    audience_questions: list[str] = Field(default_factory=list)
    packaging_tips: list[str] = Field(default_factory=list)
    recommended_topics: list[dict[str, Any]] = Field(default_factory=list)


class ChannelMetricsProvider(Protocol):
    """Adapter boundary for future direct YouTube/TikTok OAuth API sync."""

    def fetch_metrics(self) -> list[VideoPerformanceRecord]: ...


def parse_sheet_reference(id_or_url: str | None) -> tuple[str, int | None]:
    raw = (id_or_url or "").strip()
    if not raw:
        return DEFAULT_SHEET_ID, None
    id_match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", raw)
    spreadsheet_id = id_match.group(1) if id_match else raw
    gid_match = re.search(r"(?:[?#&]gid=)(\d+)", raw)
    gid = int(gid_match.group(1)) if gid_match else None
    return spreadsheet_id, gid


def load_channel_config(root: Path) -> dict[str, Any]:
    path = root / CHANNEL_CONFIG_FILE
    if path.is_file():
        data = read_yaml(path)
        if isinstance(data, dict):
            return {
                "spreadsheet_id": str(data.get("spreadsheet_id") or DEFAULT_SHEET_ID),
                "sheet_title": str(data.get("sheet_title") or CHANNEL_TAB_TITLE),
                "gid": data.get("gid"),
            }
    return {"spreadsheet_id": DEFAULT_SHEET_ID, "sheet_title": CHANNEL_TAB_TITLE, "gid": None}


def save_channel_config(
    root: Path, *, spreadsheet_id: str, sheet_title: str = CHANNEL_TAB_TITLE, gid: int | None = None
) -> dict[str, Any]:
    cfg = {"spreadsheet_id": spreadsheet_id, "sheet_title": sheet_title, "gid": gid}
    write_yaml_atomic(root / CHANNEL_CONFIG_FILE, cfg)
    return cfg


def load_metrics(root: Path) -> list[VideoPerformanceRecord]:
    path = root / METRICS_FILE
    if not path.is_file():
        return []
    data = read_yaml(path)
    entries = data.get("videos", []) if isinstance(data, dict) else []
    records: list[VideoPerformanceRecord] = []
    for item in entries:
        if isinstance(item, dict):
            records.append(VideoPerformanceRecord.model_validate(item))
    return records


def save_metrics(root: Path, records: list[VideoPerformanceRecord]) -> Path:
    dedup: dict[tuple[str, str, str], VideoPerformanceRecord] = {}
    for rec in records:
        key = (rec.slug, rec.platform, rec.source_account_id)
        prior = dedup.get(key)
        if prior is None or (rec.views or 0) >= (prior.views or 0) or rec.recorded_at >= prior.recorded_at:
            dedup[key] = rec
    ordered = sorted(dedup.values(), key=lambda r: (-(r.views or 0), r.slug))
    path = root / METRICS_FILE
    write_yaml_atomic(
        path,
        {
            "version": 1,
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "videos": [r.model_dump(mode="json") for r in ordered],
        },
    )
    return path


def load_insights(root: Path) -> dict[str, Any] | None:
    path = root / INSIGHTS_FILE
    if not path.is_file():
        return None
    data = read_yaml(path)
    return dict(data) if isinstance(data, dict) else None


def _to_int(val: Any, default: int | None = None) -> int | None:
    if val is None or val == "":
        return default
    cleaned = re.sub(r"[^\d-]", "", str(val).split(".")[0])
    try:
        return max(0, int(cleaned)) if cleaned else default
    except ValueError:
        return default


def _to_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    cleaned = str(val).replace("%", "").replace(",", ".").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    num = float(match.group(0))
    return max(0.0, min(100.0, round(num, 2)))


def _normalize_platform(raw: str | None, default: str = "youtube") -> str:
    val = (raw or default).strip().lower()
    if "short" in val:
        return "youtube_shorts"
    if "tiktok" in val:
        return "tiktok"
    if "fb" in val or "facebook" in val or "reel" in val:
        return "facebook"
    if "youtube" in val or "yt" in val:
        return "youtube"
    return "other"


def _row_to_metric(row: dict[str, str], *, default_platform: str = "youtube", source: str = "csv") -> VideoPerformanceRecord | None:
    norm = {k.strip().lower(): v.strip() for k, v in row.items() if k and v is not None}
    title = (
        norm.get("tiêu_đề_đăng")
        or norm.get("video title")
        or norm.get("tiêu đề video")
        or norm.get("title")
        or ""
    )
    url = (
        norm.get("url_video")
        or norm.get("video url")
        or norm.get("video link")
        or norm.get("link")
        or ""
    )
    raw_slug = norm.get("slug") or norm.get("content") or ""
    slug = slugify_vi(raw_slug or title or url) if (raw_slug or title or url) else ""
    if not slug:
        return None
    views = _to_int(norm.get("lượt_xem") or norm.get("views") or norm.get("total views"))
    ctr = _to_float(
        norm.get("ctr_pct")
        or norm.get("impressions click-through rate (%)")
        or norm.get("ctr (%)")
        or norm.get("ctr")
    )
    ret_30 = _to_float(norm.get("giữ_chân_30s_pct") or norm.get("retention_30s_pct"))
    avg_pct = _to_float(
        norm.get("xem_trung_bình_pct")
        or norm.get("average percentage viewed (%)")
        or norm.get("avg_view_pct")
    )
    shares = _to_int(norm.get("lưu_chia_sẻ") or norm.get("shares") or norm.get("saves"))
    comments = norm.get("bình_luận_câu_hỏi_nổi_bật") or norm.get("comments") or ""
    pub = norm.get("ngày_đăng") or norm.get("video publish time") or norm.get("published_at") or ""
    rec = norm.get("ngày_ghi") or datetime.now().astimezone().date().isoformat()
    platform = _normalize_platform(norm.get("nền_tảng") or norm.get("platform"), default_platform)
    return VideoPerformanceRecord(
        slug=slug,
        platform=platform,  # type: ignore[arg-type]
        url=url,
        title_used=title or slug,
        published_at=pub,
        views=views,
        ctr_pct=ctr,
        retention_30s_pct=ret_30,
        avg_view_pct=avg_pct,
        shares_saves=shares,
        top_comments=comments,
        recorded_at=rec,
        source=source,
    )


def import_channel_csv(root: Path, csv_text: str, *, platform: str = "youtube", source: str = "csv") -> dict[str, Any]:
    rows = parse_csv_rows(csv_text)
    existing = load_metrics(root)
    added: list[VideoPerformanceRecord] = []
    for row in rows:
        rec = _row_to_metric(row, default_platform=platform, source=source)
        if rec is not None:
            added.append(rec)
    merged = [*existing, *added]
    save_metrics(root, merged)
    return {"imported_count": len(added), "total_videos": len(load_metrics(root))}


def upsert_video_metric(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title_used") or payload.get("title") or "").strip()
    url = str(payload.get("url") or "").strip()
    raw_slug = str(payload.get("slug") or "").strip()
    slug = slugify_vi(raw_slug or title or url)
    if not raw_slug and not title and not url:
        raise ValueError("Cần nhập slug, tiêu đề hoặc link video.")
    record = VideoPerformanceRecord(
        slug=slug,
        platform=_normalize_platform(payload.get("platform"), "youtube"),  # type: ignore[arg-type]
        url=url,
        title_used=title or slug,
        published_at=str(payload.get("published_at") or "").strip(),
        views=_to_int(payload.get("views")),
        ctr_pct=_to_float(payload.get("ctr_pct")),
        retention_30s_pct=_to_float(payload.get("retention_30s_pct")),
        avg_view_pct=_to_float(payload.get("avg_view_pct")),
        shares_saves=_to_int(payload.get("shares_saves")),
        top_comments=str(payload.get("top_comments") or "").strip(),
        recorded_at=datetime.now().astimezone().date().isoformat(),
        source="manual",
    )
    save_metrics(root, [*load_metrics(root), record])
    return {"video": record.model_dump(mode="json"), "total_videos": len(load_metrics(root))}


def sync_channel_sheet(
    root: Path,
    *,
    spreadsheet_id_or_url: str | None = None,
    sheet_title: str = CHANNEL_TAB_TITLE,
    gid: int | None = None,
    fetcher: Callable[[str], str] = default_csv_fetcher,
    gsheets_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Sync channel performance metrics from a Google Sheet tab (KET_QUA_KENH or gid)."""
    cfg = load_channel_config(root)
    target_id, parsed_gid = parse_sheet_reference(spreadsheet_id_or_url or cfg["spreadsheet_id"])
    effective_gid = gid if gid is not None else (parsed_gid if parsed_gid is not None else cfg.get("gid"))
    save_channel_config(root, spreadsheet_id=target_id, sheet_title=sheet_title, gid=effective_gid)

    # First check sheet tab names via gsheets CLI if available and no explicit gid passed.
    if effective_gid is None:
        try:
            proc = gsheets_runner(
                ["gsheets", "readonly", "list-sheets", target_id, "--json"],
                capture_output=True, text=True, check=False, timeout=15, shell=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                sheets = json.loads(proc.stdout)
                if isinstance(sheets, list):
                    matched = next(
                        (s for s in sheets if str(s.get("title", "")).casefold() == sheet_title.casefold()),
                        None,
                    )
                    if matched is not None:
                        effective_gid = int(matched.get("sheetId", 0))
                        save_channel_config(root, spreadsheet_id=target_id, sheet_title=sheet_title, gid=effective_gid)
                    else:
                        titles = [str(s.get("title", "")) for s in sheets]
                        return {
                            "ok": False,
                            "imported_count": 0,
                            "total_videos": len(load_metrics(root)),
                            "message": (
                                f"Bảng tính {target_id} hiện chỉ có các tab {titles}, chưa có tab {sheet_title}. "
                                "Bác sĩ có thể tạo tab KET_QUA_KENH, dán link Sheet khác có quyền chỉnh sửa, "
                                "hoặc nhập CSV YouTube/TikTok trực tiếp trên App."
                            ),
                        }
        except (OSError, ValueError, subprocess.SubprocessError):
            pass

    if effective_gid is not None:
        url = f"https://docs.google.com/spreadsheets/d/{target_id}/export?format=csv&gid={effective_gid}"
    else:
        url = f"https://docs.google.com/spreadsheets/d/{target_id}/gviz/tq?tqx=out:csv&sheet={quote(sheet_title)}"
    csv_text = fetcher(url)
    res = import_channel_csv(root, csv_text, source="google_sheet")
    return {"ok": True, "spreadsheet_id": target_id, "sheet_title": sheet_title, **res}


def create_channel_sheet(
    root: Path,
    *,
    title: str = "PYH · Kết quả Kênh",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Create a fresh writable Google Sheet with KET_QUA_KENH headers via gsheets CLI (explicit button)."""
    created = runner(
        ["gsheets", "mutate", "create", "--title", title, "--json"],
        capture_output=True, text=True, check=False, timeout=20, shell=False,
    )
    if created.returncode != 0:
        raise RuntimeError(created.stderr.strip() or created.stdout.strip() or "Không tạo được Google Sheet mới.")
    info = json.loads(created.stdout)
    new_id = str(info["spreadsheetId"])
    runner(
        ["gsheets", "mutate", "add-sheet", new_id, "--title", CHANNEL_TAB_TITLE],
        capture_output=True, text=True, check=False, timeout=15, shell=False,
    )
    header_row = "|".join([",".join(CHANNEL_SHEET_HEADERS)])
    runner(
        ["gsheets", "mutate", "write", new_id, f"{CHANNEL_TAB_TITLE}!A1:L1", header_row],
        capture_output=True, text=True, check=False, timeout=15, shell=False,
    )
    save_channel_config(root, spreadsheet_id=new_id, sheet_title=CHANNEL_TAB_TITLE, gid=None)
    return {
        "spreadsheet_id": new_id,
        "url": info.get("spreadsheetUrl") or f"https://docs.google.com/spreadsheets/d/{new_id}/edit",
    }


def _project_context_for_metrics(root: Path, metrics: list[VideoPerformanceRecord]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for rec in metrics[:20]:
        ctx: dict[str, Any] = rec.model_dump(mode="json")
        project_dir = root / "projects" / rec.slug
        if (project_dir / "project.yaml").is_file():
            try:
                layout = resolve_project_layout(project_dir)
                rev = layout.artifact_root
                script_file = rev / "script/script.yaml"
                if script_file.is_file():
                    lines = read_yaml(script_file).get("lines", [])
                    if lines and isinstance(lines[0], dict):
                        ctx["opening_line"] = str(lines[0].get("text") or "")[:240]
                posts_file = rev / "posts/posts.yaml"
                if posts_file.is_file():
                    posts = read_yaml(posts_file)
                    if isinstance(posts, dict):
                        ctx["packaged_titles"] = posts.get("youtube_titles", [])[:3]
            except (OSError, ValueError):
                pass
        contexts.append(ctx)
    return contexts


def _analysis_records(root: Path) -> tuple[list[VideoPerformanceRecord], dict, int]:
    """Retain historical accounts on disk, select only the current authorized account."""
    from healthvideo.workflows.channel_connections import connection_status

    connections = connection_status(root)
    selected = []
    excluded = 0
    for record in load_metrics(root):
        if record.source.endswith('_api') or record.source_account_id:
            platform = 'youtube' if record.platform == 'youtube_shorts' else record.platform
            account = connections.get(platform, {})
            if not (account.get('connected') and record.source_account_id
                    and account.get('account_id') == record.source_account_id):
                excluded += 1
                continue
        selected.append(record)
    return selected, connections, excluded


def _account_coverage(records: list[VideoPerformanceRecord]) -> list[dict[str, str]]:
    return [{"platform": platform, "account_id": account_id, "source": source}
            for platform, account_id, source in sorted({
                (record.platform, record.source_account_id, record.source) for record in records})]


def _dataset_provenance(records: list[VideoPerformanceRecord]) -> dict[str, Any]:
    """Bind insights to deterministic observations; agent text cannot set provenance."""
    observations = [record.model_dump(mode='json') for record in records if record.metrics_observed]
    canonical_rows = sorted(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
                            for row in observations)
    fingerprint = hashlib.sha256(json.dumps(canonical_rows, ensure_ascii=False).encode('utf-8')).hexdigest()
    return {'data_sources': sorted({record.source for record in records if record.metrics_observed}),
            'source_accounts': _account_coverage([record for record in records if record.metrics_observed]),
            'dataset_fingerprint': fingerprint}


def analyze_channel_performance(
    root: Path,
    *,
    focus: str = "",
    invoke=invoke_with_failover,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> dict[str, Any]:
    """Invoke `researcher` to correlate published performance against hooks/scripts/packaging."""
    from healthvideo.workflows.runner import HARD_RULES

    selected, _, excluded = _analysis_records(root)
    metrics = [record for record in selected if record.metrics_observed]
    if not metrics:
        raise ValueError("Chưa có số liệu video nào để phân tích; hãy đồng bộ Sheet, nhập CSV hoặc thêm video.")
    current_now = now()
    log_dir = root / "topics/logs/channel"
    log_dir.mkdir(parents=True, exist_ok=True)
    report_path = log_dir / f"insights-{current_now:%Y%m%dT%H%M%S}.yaml"
    report_path.unlink(missing_ok=True)

    company = load_company()
    skills_block = role_skill_block("researcher", company)
    payload = {
        "focus": focus or "Phân tích toàn bộ hiệu quả video đã đăng và đề xuất hướng nội dung tiếp theo.",
        "videos": _project_context_for_metrics(root, metrics),
        "coverage": {key: sum(key in (m.metrics_observed or []) for m in metrics)
                     for key in ("views", "ctr_pct", "retention_30s_pct", "avg_view_pct", "shares_saves")},
        "sources": sorted({m.source for m in metrics}),
        "accounts": _account_coverage(metrics),
        "excluded_account_records": excluded,
        "limitations": "Imported data is not account connection. Missing metrics are unknown; do not infer CTR, retention, causal patterns or channel-wide coverage from missing observations.",
    }
    prompt = (
        "# Nhiệm vụ Researcher: Phân tích Hiệu quả Kênh (`channel_analytics`)\n\n"
        f"Đọc dữ liệu thực tế và ghi kết quả duy nhất vào `{report_path}` dạng YAML khớp schema `ChannelInsights`: "
        "`summary`, `winning_patterns`, `dropoff_risks`, `audience_questions`, `packaging_tips`, "
        "`recommended_topics` (mỗi mục có `title`, `question`, `recommended_format`, `rubric`).\n\n"
        f"Dữ liệu video JSON:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
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
        step="channel_analytics",
    )
    if not result.ok:
        raise RuntimeError("Researcher chưa hoàn thành phân tích kênh.")
    if not report_path.is_file():
        raise ValueError("Researcher không ghi báo cáo phân tích kênh.")
    raw = read_yaml(report_path)
    if not isinstance(raw, dict) or not str(raw.get("summary") or "").strip():
        raise ValueError("Báo cáo phân tích kênh thiếu summary.")
    parsed = ChannelInsights.model_validate(
        {
            "schema_version": "1.0",
            "generated_at": current_now.isoformat(timespec="seconds"),
            **raw,
            **_dataset_provenance(metrics),
        }
    )
    dossiers: list[TopicDossier] = []

    # Also seed recommended follow-up topics into topics/inbox without duplicating existing slugs.
    existing_slugs = {item["slug"] for item in load_inbox(root)}
    added_recs = 0
    for rec_topic in parsed.recommended_topics:
        if not isinstance(rec_topic, dict):
            continue
        t_title = str(rec_topic.get("title") or "").strip()
        t_q = str(rec_topic.get("question") or "").strip()
        if not t_title or not t_q or not rec_topic.get("rubric"):
            raise ValueError("Đề xuất cần title, question và rubric có bằng chứng.")
        slug = slugify_vi(t_title)
        if not isinstance(rec_topic["rubric"], dict) or set(RubricScore100.model_fields) - rec_topic["rubric"].keys():
            raise ValueError("Rubric cần đủ bốn tiêu chí có số liệu chấm thực tế.")
        rubric = RubricScore100.model_validate(
            rec_topic["rubric"]
        )
        dossier = TopicDossier(
            slug=slug,
            title=t_title,
            question=t_q,
            origin="channel_analytics",
            source_tab="KET_QUA_KENH",
            recorded_date=current_now.date().isoformat(),
            neutral_hook=t_title,
            recommended_format=rec_topic.get("recommended_format") or "both",
            rubric=rubric,
            synced_at=current_now,
        )
        if slug not in existing_slugs:
            existing_slugs.add(slug)
            dossiers.append(dossier)
            added_recs += 1
    write_yaml_atomic(root / INSIGHTS_FILE, parsed.model_dump(mode="json"))
    for dossier in dossiers:
        save_dossier(root, dossier)
    if added_recs:
        _write_inbox_index(root, load_inbox(root), now=current_now)

    return {"insights": parsed.model_dump(mode="json"), "added_topics": added_recs}


def channel_overview_payload(root: Path) -> dict[str, Any]:
    """Payload rendered inside overview(root)['channel'] on the Dashboard."""
    metrics, connections, excluded = _analysis_records(root)
    insights = load_insights(root)
    cfg = load_channel_config(root)
    observed = [m for m in metrics if m.metrics_observed]
    fingerprint = _dataset_provenance(observed)['dataset_fingerprint']
    insights_stale = bool(insights is not None and insights.get('dataset_fingerprint') != fingerprint)
    if insights is None:
        insights_status = 'none'
    elif not insights.get('dataset_fingerprint'):
        insights_status = 'historical_unverified'
    else:
        insights_status = 'stale' if insights_stale else 'current'
    ctrs = [m.ctr_pct for m in observed if "ctr_pct" in (m.metrics_observed or [])]
    r30s = [m.retention_30s_pct for m in observed if "retention_30s_pct" in (m.metrics_observed or [])]
    avgs = [m.avg_view_pct for m in observed if "avg_view_pct" in (m.metrics_observed or [])]
    return {
        "connected": any(c.get("connected", False) for c in connections.values()),
        "connections": connections,
        "data_available": bool(observed),
        "analysis_ready": bool(observed),
        "analysis_reason": "Có dữ liệu đo thực tế; phạm vi theo từng chỉ số." if observed else "Chưa có số liệu đo; hãy nhập CSV/Sheet, nhập tay hoặc đồng bộ tài khoản đã kết nối.",
        "sources": sorted({m.source for m in observed}),
        "accounts": _account_coverage(observed),
        "excluded_account_records": excluded,
        "sheet_id": cfg["spreadsheet_id"],
        "sheet_title": cfg["sheet_title"],
        "videos_count": len(metrics),
        "total_views": (sum(m.views or 0 for m in observed if "views" in (m.metrics_observed or []))
                        if any("views" in (m.metrics_observed or []) for m in observed) else None),
        "avg_ctr_pct": round(sum(ctrs) / len(ctrs), 2) if ctrs else None,
        "avg_retention_30s_pct": round(sum(r30s) / len(r30s), 2) if r30s else None,
        "avg_view_pct": round(sum(avgs) / len(avgs), 2) if avgs else None,
        "videos": [m.model_dump(mode="json") for m in metrics[:20]],
        "insights": insights if not insights_stale else None,
        "insights_stale": insights_stale,
        "insights_status": insights_status,
        "historical_insights": insights if insights_stale else None,
    }


def save_synced_metrics(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the entire provider response before changing stored observations."""
    if payload.get("platform") not in {"youtube", "tiktok"} or not isinstance(payload.get("records"), list):
        raise ValueError("Kết quả đồng bộ thiếu platform hoặc danh sách records hợp lệ.")
    account_id = payload.get("account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        raise ValueError("Kết quả đồng bộ thiếu tài khoản nguồn đã xác minh.")
    records = [VideoPerformanceRecord.model_validate(item) for item in payload["records"]]
    if any(record.platform != payload["platform"] or record.source_account_id != account_id
           or record.source != payload["platform"] + "_api" for record in records):
        raise ValueError("Bản ghi đồng bộ không khớp nền tảng hoặc tài khoản nguồn.")
    save_metrics(root, [*load_metrics(root), *records])
    return {"platform": payload["platform"], "account_id": account_id, "imported_count": len(records), "total_videos": len(load_metrics(root))}
