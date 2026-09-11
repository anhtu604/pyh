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

from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml

_NOT_YET_MODELED = (
    "chưa có trong hệ thống: population, certainty, applicability, "
    "quan điểm bác sĩ theo từng claim."
)


def render_medical_packet(revision_root: Path) -> str:
    ledger = read_yaml(revision_root / "evidence" / "ledger.yaml")
    sources = {
        record["id"]: SourceRecord.model_validate(record) for record in ledger.get("records", [])
    }
    claims = [EvidenceClaim.model_validate(claim) for claim in ledger.get("claims", [])]
    script = Script.model_validate(read_yaml(revision_root / "script" / "script.yaml"))
    storyboard = Storyboard.model_validate(read_yaml(revision_root / "storyboard" / "storyboard.yaml"))

    lines_by_claim: dict[str, list[str]] = {}
    for line in script.lines:
        if line.claim_id:
            lines_by_claim.setdefault(line.claim_id, []).append(line.text)
    markers_by_claim: dict[str, list[str]] = {}
    for scene in storyboard.scenes:
        if scene.claim_id and scene.source_marker:
            markers_by_claim.setdefault(scene.claim_id, []).append(scene.source_marker)

    rows = []
    for claim in claims:
        source_titles = ", ".join(
            escape(sources[source_id].title) for source_id in claim.sources if source_id in sources
        )
        script_lines = "; ".join(escape(text) for text in lines_by_claim.get(claim.id, []))
        markers = ", ".join(escape(marker) for marker in markers_by_claim.get(claim.id, []))
        rows.append(
            "<tr>"
            f"<td>{escape(claim.id)}</td>"
            f"<td>{escape(claim.text_public)}</td>"
            f"<td>{escape(claim.text_technical)}</td>"
            f"<td>{source_titles}</td>"
            f"<td>{script_lines}</td>"
            f"<td>{markers}</td>"
            "</tr>"
        )

    return (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        "<title>Gói duyệt y khoa</title></head><body>"
        f"<h1>{escape(storyboard.title)}</h1>"
        '<table border="1"><thead><tr>'
        "<th>Claim</th><th>Câu công chúng</th><th>Mệnh đề kỹ thuật</th>"
        "<th>Nguồn</th><th>Câu thoại</th><th>Marker</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        f"<p>{escape(_NOT_YET_MODELED)}</p>"
        "</body></html>"
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
