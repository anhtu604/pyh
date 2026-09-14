"""Static, read-only HTML review packets — no JS, no self-signing, no network.

Only renders fields that exist today on `EvidenceClaim`/`SourceRecord`
(`domain/evidence.py`): `text_public`, `text_technical`, `sources`/`title`.
The §14 spec also wants population/certainty/applicability/per-claim doctor
notes; those fields do not exist on the model yet, so the packet says so
explicitly rather than inventing text for them — extending the model is a
later milestone's job, once there is a real extraction pipeline feeding it.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from healthvideo.domain.asset_manifest import AssetManifest
from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.domain.visual_budget import VisualCategory, calculate_visual_budget
from healthvideo.storage.files import read_yaml

_NOT_YET_MODELED = (
    "chưa có trong hệ thống: population, certainty, applicability, "
    "quan điểm bác sĩ theo từng claim."
)


def _render_visual_budget_section(storyboard: Storyboard) -> str:
    if storyboard.visual_budget_profile != "m6_5_v1":
        return ""
    report = calculate_visual_budget(storyboard)
    rows = []
    for category in VisualCategory:
        frames = report.category_frames[category]
        basis_points = report.category_basis_points[category]
        bounds = report.effective_bounds[category]
        percentage = f"{basis_points // 100}.{basis_points % 100:02d}%"
        rows.append(
            "<tr>"
            f"<td>{escape(category.value)}</td><td>{frames}</td>"
            f"<td>{basis_points} bp ({percentage})</td>"
            f"<td>{bounds.min_percent}–{bounds.max_percent}%</td>"
            "</tr>"
        )
    override = storyboard.visual_budget_override
    rationale = (
        f"<p>Lý do override: {escape(override.rationale)}</p>"
        if override is not None
        else ""
    )
    return (
        '<section><h2>Ngân sách visual M6.5</h2>'
        f"<p>Profile: {escape(report.profile)}</p>"
        f"<p>Tổng timeline: {report.total_frames} frame</p>"
        f"<p>Override: {'có' if report.override_active else 'không'}</p>"
        + rationale
        + '<table border="1"><thead><tr><th>Nhóm</th><th>Frame</th>'
        "<th>Tỷ lệ</th><th>Giới hạn hiệu lực</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        f"<p>Kết quả: {'đạt' if report.passed else 'không đạt'}</p></section>"
    )


def render_medical_packet(revision_root: Path) -> str:
    ledger = read_yaml(revision_root / "evidence" / "ledger.yaml")
    sources = {
        record["id"]: SourceRecord.model_validate(record)
        for record in ledger.get("records", [])
    }
    claims = [EvidenceClaim.model_validate(claim) for claim in ledger.get("claims", [])]
    script = Script.model_validate(read_yaml(revision_root / "script" / "script.yaml"))
    storyboard = Storyboard.model_validate(
        read_yaml(revision_root / "storyboard" / "storyboard.yaml")
    )

    lines_by_claim: dict[str, list[str]] = {}
    for line in script.lines:
        if line.claim_id:
            lines_by_claim.setdefault(line.claim_id, []).append(line.text)
    markers_by_claim: dict[str, list[str]] = {}
    for scene in storyboard.scenes:
        if scene.claim_id and scene.source_marker:
            markers_by_claim.setdefault(scene.claim_id, []).append(scene.source_marker)

    rows = []
    highlight_rows = []
    for scene in storyboard.scenes:
        highlight = scene.evidence_highlight
        if (
            scene.visual != "evidence_highlight"
            or highlight is None
            or highlight.source_id is None
        ):
            continue
        source = sources.get(highlight.source_id)
        source_title = (
            source.title if source is not None else "nguồn không có trong ledger"
        )
        coords = f"({highlight.x:g}, {highlight.y:g}, {highlight.width:g}, {highlight.height:g})"
        highlight_rows.append(
            "<tr>"
            f"<td>{escape(scene.id)}</td><td>{escape(scene.source_marker or '')}</td>"
            f"<td>{escape(highlight.source_id)}: {escape(source_title)}</td>"
            f"<td>{highlight.page}</td><td>{escape(highlight.quote)}</td>"
            f"<td>{escape(coords)}</td><td>{escape(highlight.image)}</td>"
            "</tr>"
        )
    has_unmodeled = False
    for claim in claims:
        source_titles = ", ".join(
            escape(sources[source_id].title)
            for source_id in claim.sources
            if source_id in sources
        )
        script_lines = "; ".join(
            escape(text) for text in lines_by_claim.get(claim.id, [])
        )
        markers = ", ".join(
            escape(marker) for marker in markers_by_claim.get(claim.id, [])
        )
        certainty = (
            claim.certainty
            if claim.certainty != "unrated"
            else "chưa có trong hệ thống"
        )
        population = claim.population or "chưa có trong hệ thống"
        if (
            certainty == "chưa có trong hệ thống"
            or population == "chưa có trong hệ thống"
        ):
            has_unmodeled = True
        rows.append(
            "<tr>"
            f"<td>{escape(claim.id)}</td>"
            f"<td>{escape(claim.text_public)}</td>"
            f"<td>{escape(claim.text_technical)}</td>"
            f"<td>{source_titles}</td>"
            f"<td>{escape(certainty)}</td>"
            f"<td>{escape(population)}</td>"
            f"<td>{script_lines}</td>"
            f"<td>{markers}</td>"
            "</tr>"
        )

    note_paragraph = f"<p>{escape(_NOT_YET_MODELED)}</p>" if has_unmodeled else ""
    visual_budget_section = _render_visual_budget_section(storyboard)
    hook_outro_section = ""
    if script.format_profile == "hook_outro_v1":
        final = storyboard.scenes[-1]
        asset_manifest = AssetManifest.model_validate(
            read_yaml(revision_root / "assets" / "asset-manifest.yaml")
        )
        brand_records = {
            asset.path: asset for asset in asset_manifest.assets
            if asset.storyboard_role == "brand"
        }
        brand_details = []
        for ref in final.visual_assets:
            if ref.role != "brand":
                continue
            record = brand_records.get(ref.path)
            if record is None:
                brand_details.append(escape(ref.path) + " (chưa khai báo)")
            else:
                brand_details.append(
                    f"{escape(record.path)}; SHA-256: {escape(record.sha256)}; "
                    f"license: {escape(record.license)}; creator: {escape(record.creator)}"
                )
        brand_paths = ", ".join(brand_details)
        hook_outro_section = (
            '<section><h2>Hook và outro đã khai báo</h2>'
            f"<p>Profile: {escape(script.format_profile)}</p>"
            f"<p>Hook: {escape(script.lines[0].text)}</p>"
            f"<p>Outro: {escape(script.lines[-1].text)}</p>"
            f"<p>Timeline outro: {final.start_frame}–{final.start_frame + final.duration_frames} frame</p>"
            f"<p>Brand asset: {brand_paths or 'chưa khai báo'}</p></section>"
        )
    return (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        "<title>Gói duyệt y khoa</title></head><body>"
        f"<h1>{escape(storyboard.title)}</h1>"
        '<table border="1"><thead><tr>'
        "<th>Claim</th><th>Câu công chúng</th><th>Mệnh đề kỹ thuật</th>"
        "<th>Nguồn</th><th>Độ tin cậy</th><th>Quần thể</th><th>Câu thoại</th><th>Marker</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        + (
            '<h2>Paper highlights</h2><table border="1"><thead><tr><th>Scene</th><th>Marker</th><th>Source</th><th>Page</th><th>Quote</th><th>Source-page rectangle (x,y,w,h)</th><th>Crop asset</th></tr></thead><tbody>'
            + "".join(highlight_rows)
            + "</tbody></table>"
            if highlight_rows
            else ""
        )
        + note_paragraph
        + visual_budget_section
        + hook_outro_section
        + "</body></html>"
    )


def render_video_packet(revision_root: Path) -> str:
    manifest_path = revision_root / "renders" / "render-manifest.json"
    manifest = read_yaml(manifest_path) if manifest_path.is_file() else {}
    qa_path = revision_root / "reviews" / "video-qa.json"
    qa = read_yaml(qa_path) if qa_path.is_file() else {}

    return (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        "<title>Gói duyệt video</title></head><body>"
        '<video controls src="../renders/video.mp4"></video>'
        f"<pre>{escape(str(manifest))}</pre>"
        f"<pre>{escape(str(qa))}</pre>"
        "</body></html>"
    )
