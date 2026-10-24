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
from healthvideo.domain.outline import Outline
from healthvideo.domain.posts import PostSet
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.domain.visual_budget import calculate_visual_budget
from healthvideo.render.timing import restore_timed_storyboard
from healthvideo.storage.explainer import read_explainer
from healthvideo.storage.files import canonical_json_hash, read_yaml
from healthvideo.workflows.long_form import OUTLINE_ARTIFACT, load_clip_scenes
from healthvideo.workflows.review_frames import mechanism_sheets

_NOT_YET_MODELED = (
    "chưa có trong hệ thống: population, certainty, applicability, "
    "quan điểm bác sĩ theo từng claim."
)


def _render_support(claim: EvidenceClaim) -> str:
    from healthvideo.evidence.fulltext import load_fulltext

    rows = []
    for support in claim.support:
        fulltext = load_fulltext(support.source_id)
        origin = fulltext.origin if fulltext else "abstract"
        license_text = (fulltext.license if fulltext else None) or "unknown"
        rows.append(
            f"<li>{escape(support.source_id)} — {escape(support.locator)}: "
            f"<q>{escape(support.quote)}</q> "
            f"({escape(origin)}; {escape(license_text)})</li>"
        )
    return "<ul>" + "".join(rows) + "</ul>" if rows else ""


def _render_visual_budget_section(storyboard: Storyboard, assets: AssetManifest) -> str:
    report = calculate_visual_budget(storyboard, assets)
    rows = []
    for category in report.effective_bounds:
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
        + f"<p>Mascot: {report.mascot_frames} frames "
        f"({report.mascot_basis_points / 100:.2f}%)</p>"
        + "".join(f'<p role="status">Warning: {escape(w)}</p>' for w in report.warnings)
        + rationale
        + '<table border="1"><thead><tr><th>Nhóm</th><th>Frame</th>'
        "<th>Tỷ lệ</th><th>Giới hạn hiệu lực</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        f"<p>Kết quả: {'đạt' if report.passed else 'không đạt'}</p></section>"
    )


def _render_mechanism_section(
    revision_root: Path, claims: list[EvidenceClaim], sources: dict[str, SourceRecord],
) -> str:
    if not claims:
        return ""
    explainer = (
        read_explainer(revision_root)
        if (revision_root / "explainer" / "explainer.yaml").is_file()
        else None
    )
    rows = []
    for claim in claims:
        source_text = "; ".join(
            escape(source_id) + (
                f": {escape(sources[source_id].title)}" if source_id in sources else ""
            )
            for source_id in claim.sources
        )
        visuals = "".join(
            f"<li>{escape(layer.layer)}: {escape(layer.concept)}; "
            f"{escape(layer.visual.motion)}</li>"
            for layer in (explainer.layers if explainer is not None else ())
            if claim.id in layer.claim_ids
        )
        rows.append(
            f"<tr><td>{escape(claim.id)}</td><td>{escape(claim.text_public)}</td>"
            f"<td>{source_text}{_render_support(claim)}</td>"
            f"<td>{'<ul>' + visuals + '</ul>' if visuals else ''}</td></tr>"
        )
    return (
        '<section><h2>Cơ chế — cần kiểm độ đúng giải phẫu</h2>'
        '<table border="1"><thead><tr><th>Claim</th><th>Câu công chúng</th>'
        '<th>Nguồn</th><th>Lớp / Khái niệm / visual.motion</th></tr></thead><tbody>'
        + "".join(rows) + "</tbody></table></section>"
    )


def _render_long_form_section(revision_root: Path, storyboard: Storyboard) -> str:
    if storyboard.format_profile != "youtube_long":
        return ""
    outline = Outline.model_validate(read_yaml(revision_root / OUTLINE_ARTIFACT))
    chapter_rows = "".join(
        f"<tr><td>{escape(chapter.id)}</td><td>{escape(chapter.title)}</td>"
        f"<td>{escape(chapter.goal)}</td><td>{escape(', '.join(chapter.claim_ids))}</td>"
        f"<td>{chapter.target_seconds}</td></tr>"
        for chapter in outline.chapters
    )
    clip_rows = "".join(
        f"<tr><td>{escape(clip_id)}</td>"
        f"<td>{escape(', '.join(scene.id for scene in scenes))}</td>"
        f"<td>{escape(' '.join(scene.narration for scene in scenes))}</td>"
        f"<td>{escape(', '.join(sorted({s.claim_id for s in scenes if s.claim_id})))}</td></tr>"
        for clip_id, scenes in load_clip_scenes(revision_root, storyboard).items()
    )
    return (
        '<section><h2>Dàn ý chương</h2><table border="1"><thead><tr>'
        "<th>Chương</th><th>Tiêu đề</th><th>Mục tiêu</th><th>Claim</th><th>Giây dự kiến</th>"
        f"</tr></thead><tbody>{chapter_rows}</tbody></table></section>"
        '<section><h2>Clip dọc 9:16 cắt từ kịch bản</h2><table border="1"><thead><tr>'
        "<th>Clip</th><th>Cảnh</th><th>Lời thoại</th><th>Claim</th>"
        f"</tr></thead><tbody>{clip_rows}</tbody></table></section>"
    )


def render_medical_packet(revision_root: Path) -> str:
    ledger = read_yaml(revision_root / "evidence" / "ledger.yaml")
    sources = {
        record["id"]: SourceRecord.model_validate(record)
        for record in ledger.get("records", [])
    }
    claims = [EvidenceClaim.model_validate(claim) for claim in ledger.get("claims", [])]
    from healthvideo.evidence.fulltext import validate_support_records

    validate_support_records(claims, sources.values())
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
        if claim.type == "mechanism":
            continue
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
            f"<td>{source_titles}{_render_support(claim)}</td>"
            f"<td>{escape(certainty)}</td>"
            f"<td>{escape(population)}</td>"
            f"<td>{script_lines}</td>"
            f"<td>{markers}</td>"
            "</tr>"
        )

    note_paragraph = f"<p>{escape(_NOT_YET_MODELED)}</p>" if has_unmodeled else ""
    mechanism_section = _render_mechanism_section(
        revision_root, [claim for claim in claims if claim.type == "mechanism"], sources,
    )
    asset_manifest = AssetManifest.model_validate(
        read_yaml(revision_root / "assets" / "asset-manifest.yaml")
    )
    visual_budget_section = _render_visual_budget_section(storyboard, asset_manifest)
    hook_outro_section = ""
    if script.format_profile == "hook_outro_v1":
        final = storyboard.scenes[-1]
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
        + mechanism_section
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
        + _render_long_form_section(revision_root, storyboard)
        + "</body></html>"
    )


def _uses_placeholder_mascot(renders: Path, clips: dict[str, str]) -> bool:
    """Inspect saved render inputs, never the mutable brand profile or storyboard.

    mascot_asset records SVG paths for the fixed rig and PNG paths for artwork.
    Only inputs belonging to this packet count; older packets may have no input.
    """
    inputs = [renders / "render-input.json"]
    for relative in clips.values():
        path = (renders / relative).with_suffix(".render-input.json")
        if path.resolve().is_relative_to(renders.resolve()):
            inputs.append(path)
    for path in inputs:
        if not path.is_file():
            continue
        data = read_yaml(path)
        mascot_paths = [
            asset["path"]
            for scene in data.get("scenes", [])
            for asset in scene.get("visual_assets", [])
            if asset.get("role") == "mascot"
        ]
        cta = data.get("youtube_cta")
        if cta and "mascot_path" in cta:
            mascot_paths.append(cta["mascot_path"])
        if any(Path(relative).suffix == ".svg" for relative in mascot_paths):
            return True
    return False


def _render_posts_section(revision_root: Path) -> str:
    posts_path = revision_root / "posts" / "posts.yaml"
    if not posts_path.is_file():
        return ""
    posts = PostSet.model_validate(read_yaml(posts_path))
    titles_html = "".join(f"<li>{escape(title)}</li>" for title in posts.youtube_titles)
    tags_html = ", ".join(escape(tag) for tag in posts.youtube_tags)
    clips_html = "".join(
        f"<li><strong>{escape(clip_id)}</strong>: "
        f"TikTok: {escape(captions.tiktok)} | "
        f"Shorts: {escape(captions.shorts)} | "
        f"Reels: {escape(captions.reels)}</li>"
        for clip_id, captions in sorted(posts.clip_captions.items())
    )
    thumbnail_html = (
        '<h3>Thumbnail YouTube</h3><img src="../posts/thumbnail.png" '
        'alt="Thumbnail YouTube" style="max-width:100%;width:640px">'
        if posts.thumbnail is not None else ""
    )
    return (
        "<section><h2>Bài đăng</h2>"
        f"{thumbnail_html}"
        f"<h3>Tiêu đề YouTube</h3><ul>{titles_html}</ul>"
        f"<h3>Mô tả YouTube</h3><pre>{escape(posts.youtube_description)}</pre>"
        f"<p><strong>Tag:</strong> {tags_html}</p>"
        + (f"<h3>Caption clip</h3><ul>{clips_html}</ul>" if clips_html else "")
        + f"<h3>Facebook</h3><p>{escape(posts.facebook_post)}</p>"
        f"<h3>Community</h3><p>{escape(posts.youtube_community)}</p>"
        "</section>"
    )


def render_video_packet(revision_root: Path) -> str:
    manifest_path = revision_root / "renders" / "render-manifest.json"
    manifest = read_yaml(manifest_path) if manifest_path.is_file() else {}
    mascot_warning = (
        f'<p role="status">{escape("mascot đang dùng hình tạm")}</p>'
        if _uses_placeholder_mascot(revision_root / "renders", manifest.get("clips", {}))
        else ""
    )
    qa_path = revision_root / "reviews" / "video-qa.json"
    qa = read_yaml(qa_path) if qa_path.is_file() else {}
    storyboard = Storyboard.model_validate(
        read_yaml(revision_root / "storyboard" / "storyboard.yaml")
    )
    timing_path = revision_root / "renders" / "scene-timing.json"
    if timing_path.is_file():
        storyboard = restore_timed_storyboard(storyboard, read_yaml(timing_path))
    assets = AssetManifest.model_validate(read_yaml(revision_root / "assets/asset-manifest.yaml"))
    budget_section = _render_visual_budget_section(storyboard, assets)
    if budget_section:
        recorded = qa.get("visual_budget")
        expected = calculate_visual_budget(storyboard, assets).model_dump(mode="json")
        if recorded is None:
            status = "thiếu visual_budget"
        elif canonical_json_hash(recorded) == canonical_json_hash(expected):
            status = "khớp report tái tính"
        else:
            status = "không khớp report tái tính"
        budget_section += f"<p>QA production: {status}</p>"

    clip_spans = (
        {
            clip_id: (min(scene.start_frame for scene in scenes),
                      max(scene.start_frame + scene.duration_frames for scene in scenes))
            for clip_id, scenes in load_clip_scenes(revision_root, storyboard).items()
        }
        if storyboard.format_profile == "youtube_long" and manifest.get("clips")
        else {}
    )
    clip_videos = "".join(
        f"<h2>Clip {escape(clip_id)}</h2>"
        + (f"<p>Source timeline: {clip_spans[clip_id][0]}–{clip_spans[clip_id][1]} frame</p>"
           if clip_id in clip_spans else "")
        + f'<video controls src="../renders/{escape(relative)}"></video>'
        for clip_id, relative in sorted(manifest.get("clips", {}).items())
    )
    sheets = mechanism_sheets(revision_root)
    sheet_section = (
        '<section><h2>Mechanism contact sheets (QA)</h2>'
        '<p>QA aids; medical and video approvals are still required.</p>'
        + "".join(
            f'<figure><img style="max-width:100%" alt="{escape(path.parent.parent.name)} '
            f'mechanism frames" src="../{escape(path.relative_to(revision_root).as_posix())}">'
            f'<figcaption>{escape(path.parent.parent.name)} / {escape(path.name)}</figcaption>'
            '</figure>' for path in sheets
        ) + '</section>' if sheets else ""
    )
    posts_section = _render_posts_section(revision_root)
    pronunciation_section = _render_pronunciation_section(revision_root, storyboard)
    sfx_section = '<section><h2>SFX đã dùng</h2><ul>' + ''.join(
        f'<li>{escape(str(event["scene"]))}: {escape(str(event["id"]))}; '
        f'{escape(str(event["time"]))} s (trong cảnh: {escape(str(event["at"]))} s)</li>'
        for event in manifest.get('sfx', [])
    ) + '</ul></section>'
    return (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        "<title>Gói duyệt video</title></head><body>"
        '<video controls src="../renders/video.mp4"></video>'
        + clip_videos
        + sheet_section
        + mascot_warning
        + budget_section
        + posts_section
        + pronunciation_section
        + sfx_section
        + _render_visual_review_section(revision_root)
        + f"<pre>{escape(str(manifest))}</pre>"
        f"<pre>{escape(str(qa))}</pre>"
        "</body></html>"
    )


def _render_visual_review_section(root: Path) -> str:
    report_path = root / "reviews/visual-review.yaml"
    index_path = root / "reviews/visual/candidates.yaml"
    if not index_path.is_file():
        return ""
    index = read_yaml(index_path)
    report = read_yaml(report_path) if report_path.is_file() else {}
    rows = []
    for asset in index.get("assets", []):
        selected = asset.get("selected")
        image = (
            f'<img style="max-width:480px" alt="Ứng viên đã chọn" src="../{escape(selected)}">'
            if selected else f'<p>SVG thay thế: {escape(str(asset.get("fallback") or "chờ xem ảnh"))}</p>'
        )
        rows.append(f'<h3>{escape(", ".join(asset["scenes"]))}</h3>{image}')
    sheets = index.get('contact_sheets') or ([index['contact_sheet']] if index.get('contact_sheet') else [])
    final_path = root / 'reviews/visual/final-contact-sheets.yaml'
    final = read_yaml(final_path) if final_path.is_file() else {}
    final_section = ('<h3>Bố cục bản cuối sau chọn ứng viên/SVG</h3>' + ''.join(
        f'<img style="max-width:100%" alt="Contact sheet bản cuối" src="../{escape(s["path"])}">'
        for s in final.get('sheets', [])
    )) if final else ''
    return (
        '<section><h2>Kiểm trực quan — visual_review</h2>'
        '<a href="visual-review.yaml">Báo cáo visual-review.yaml</a>'
        + ''.join(rows)
        + final_section
        + '<h3>Contact sheet ứng viên ban đầu</h3>'
        + ''.join(f'<img style="max-width:100%" alt="Contact sheet toàn video" src="../{escape(s["path"])}">'
                  for s in sheets)
        + f'<pre>{escape(str(report))}</pre></section>'
    )


def _render_pronunciation_section(revision_root: Path, storyboard: Storyboard) -> str:
    path = revision_root / "reviews/pronunciation-qa.json"
    if not path.is_file():
        return '<section><h2>Có thể đọc sai</h2><p>Chưa có căn chữ Whisper; dùng phụ đề ước lượng.</p></section>'
    report = read_yaml(path)
    origins = {}
    for scene in storyboard.scenes:
        origins.setdefault(scene.script_line_id, scene.start_frame / 30)
    rows = []
    for flag in report.get("flags", []):
        line, start, end = flag["line"], float(flag["start"]), float(flag["end"])
        video_start = origins.get(line, 0) + start
        audio_path = f"../renders/audio/lines/{line}.wav#t={max(0, start-.2):.3f},{end+.4:.3f}"
        rows.append(
            f'<tr><td>{escape(line)}</td><td>{escape(flag["script_word"])}</td>'
            f'<td>{escape(flag["heard"] or "(không nghe được)")}</td>'
            f'<td>{start:.2f}–{end:.2f} giây (dòng); '
            f'<a href="../renders/video.mp4#t={video_start:.3f}">{video_start:.2f} giây video</a></td>'
            f'<td>{escape(flag["priority"])}</td><td><audio controls preload="none" '
            f'src="{escape(audio_path, quote=True)}"></audio></td>'
            f'<td>{escape(flag["suggestion"])}</td></tr>'
        )
    ratios = "".join(f'<li>{escape(line["line"])}: {line["match_ratio"]:.1%}</li>'
                     for line in report.get("lines", []))
    return ('<section><h2>Có thể đọc sai</h2>'
            '<p>Gợi ý từ ASR, cần bác sĩ nghe lại; không tự sửa lời thoại.</p>'
            f'<p>Trạng thái: {escape(report.get("status", "unavailable"))}</p><ul>{ratios}</ul>'
            '<table border="1"><tr><th>Dòng</th><th>Kịch bản</th><th>Nghe được</th>'
            '<th>Mốc nghe lại</th><th>Ưu tiên</th><th>Audio</th><th>Gợi ý</th></tr>'
            + "".join(rows) + '</table></section>')
