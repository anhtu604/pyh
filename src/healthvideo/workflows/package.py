"""Assemble the four publishable files for a video-approved project.

Packaging is the last step before a human uploads the video by hand: it copies
the approved MP4 next to the caption, the full source list and an audit
manifest. It never calls a publishing API and never moves the project state.
"""

import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from tempfile import mkdtemp
from typing import Any, TypeVar

from pydantic import BaseModel

from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.project import ProjectManifest, ProjectState
from healthvideo.domain.review import ReviewKind, ReviewRecord
from healthvideo.domain.script import Script
from healthvideo.render.run import (
    OUTPUT_NAME,
    PRODUCTION_ARTIFACT,
    RENDER_INPUT_NAME,
    production_run_dir,
)
from healthvideo.storage.files import (
    read_yaml,
    replace_directory_atomic,
    sha256_file,
    write_text_atomic,
)
from healthvideo.workflows.review import ensure_approval_current, latest_approval

LedgerEntry = TypeVar("LedgerEntry", bound=BaseModel)

PUBLISH_DIRECTORY = "publish"
CAPTION_NAME = "caption.txt"
SOURCES_NAME = "sources.md"
PACKAGE_MANIFEST_NAME = "manifest.json"
PROJECT_MANIFEST_NAME = "project.yaml"
DISCLAIMER = (
    "Nội dung chỉ mang tính thông tin chung, không thay thế khám, chẩn đoán "
    "hoặc điều trị y khoa. Hãy trao đổi với bác sĩ của bạn trước khi thay đổi "
    "chế độ ăn hoặc thuốc."
)


def package_project(project_dir: Path) -> Path:
    """Publish `publish/` for a project whose video approval is still current.

    Returns the published directory. Refuses a project that has not passed the
    video gate, and refuses an approval that is missing or stale, so no package
    leaves the machine without an auditable doctor approval behind it.
    """
    project = ProjectManifest.model_validate(
        read_yaml(project_dir / PROJECT_MANIFEST_NAME)
    )
    if project.state is not ProjectState.APPROVED_TO_PUBLISH:
        raise ValueError(
            "Packaging requires project state "
            f"{ProjectState.APPROVED_TO_PUBLISH.value}, not {project.state.value}"
        )
    approval = latest_approval(project_dir, ReviewKind.VIDEO)
    if approval is None:
        raise FileNotFoundError(
            "Packaging requires a video approval record; "
            "run 'healthvideo review video'"
        )
    ensure_approval_current(project_dir, project, ReviewKind.VIDEO)

    run_dir = _active_run_dir(project_dir, project)
    video = run_dir / OUTPUT_NAME
    if not video.is_file():
        raise FileNotFoundError(f"Approved video is missing: {video}")

    script = Script.model_validate(read_yaml(project_dir / "script" / "script.yaml"))
    citations = _citations(script, read_yaml(project_dir / "evidence" / "ledger.yaml"))

    publish_dir = project_dir / PUBLISH_DIRECTORY
    staging_dir = Path(mkdtemp(prefix=f".{project.slug}.package-", dir=project_dir))
    try:
        shutil.copy2(video, staging_dir / OUTPUT_NAME)
        write_text_atomic(staging_dir / CAPTION_NAME, _caption(script, citations))
        write_text_atomic(staging_dir / SOURCES_NAME, _sources(script, citations))
        write_text_atomic(
            staging_dir / PACKAGE_MANIFEST_NAME,
            _manifest_json(
                project=project,
                script=script,
                approval=approval,
                staging_dir=staging_dir,
                render_input=run_dir / RENDER_INPUT_NAME,
                citations=citations,
            ),
        )
        replace_directory_atomic(staging_dir, publish_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    return publish_dir


def _active_run_dir(project_dir: Path, project: ProjectManifest) -> Path:
    input_hash = project.artifact_hashes.get(PRODUCTION_ARTIFACT)
    if input_hash is None:
        raise FileNotFoundError(
            "Packaging needs an active production run in "
            f"project.yaml.artifact_hashes.{PRODUCTION_ARTIFACT}"
        )
    return production_run_dir(project_dir, input_hash)


def _citations(
    script: Script, ledger: Mapping[str, Any]
) -> dict[str, list[SourceRecord]]:
    """Resolve each on-screen marker to the evidence records standing behind it.

    Markers appear in the video as bare `[n]`, so every one of them must name at
    least one record here; a marker no record backs is refused rather than
    published as evidence.
    """
    records = {
        record.id: record
        for record in _validated(SourceRecord, ledger.get("records", []))
    }
    claims = {
        claim.id: claim for claim in _validated(EvidenceClaim, ledger.get("claims", []))
    }
    citations: dict[str, list[SourceRecord]] = {}
    for line in script.lines:
        marker = line.source_marker
        if marker is None or marker in citations:
            continue
        claim = claims.get(line.claim_id or "")
        if claim is None:
            raise ValueError(
                f"Script line {line.id} cites {marker} through claim "
                f"{line.claim_id!r}, which the evidence ledger does not define"
            )
        cited = [_record(records, record_id, line.id) for record_id in claim.sources]
        if not cited:
            raise ValueError(
                f"Script line {line.id} shows {marker} but claim {claim.id} "
                f"({claim.type}) lists no source"
            )
        citations[marker] = cited
    return citations


def _validated(model: type[LedgerEntry], items: Any) -> list[LedgerEntry]:
    if not isinstance(items, list):
        raise TypeError(f"Evidence ledger {model.__name__} section must be a list")
    return [model.model_validate(item) for item in items]


def _record(
    records: Mapping[str, SourceRecord], record_id: str, line_id: str
) -> SourceRecord:
    record = records.get(record_id)
    if record is None:
        raise ValueError(
            f"Script line {line_id} cites source {record_id}, "
            "which the evidence ledger does not define"
        )
    return record


def _caption(script: Script, citations: Mapping[str, list[SourceRecord]]) -> str:
    """Write the upload caption: a short hook, the disclaimer and the sources."""
    hook = script.lines[0].text if script.lines else script.title
    blocks = [script.title, hook, DISCLAIMER]
    if citations:
        sources = "\n".join(
            f"{marker} " + "; ".join(_short_citation(record) for record in records)
            for marker, records in citations.items()
        )
        blocks.append(f"Nguồn:\n{sources}")
    return "\n\n".join(blocks) + "\n"


def _short_citation(record: SourceRecord) -> str:
    parts = [record.title]
    if record.authors:
        parts.append(", ".join(record.authors))
    if record.year is not None:
        parts.append(str(record.year))
    if record.doi is not None:
        parts.append(f"DOI: {record.doi}")
    elif record.pmid is not None:
        parts.append(f"PMID: {record.pmid}")
    elif record.url is not None:
        parts.append(record.url)
    return ". ".join(parts)


def _sources(script: Script, citations: Mapping[str, list[SourceRecord]]) -> str:
    """Write the full source list the video only hints at with `[n]`."""
    lines = [f"# Nguồn tham khảo — {script.title}", ""]
    if not citations:
        lines.append("Video này không hiển thị dấu trích dẫn nào.")
        return "\n".join(lines) + "\n"
    for marker, records in citations.items():
        lines.append(f"## {marker}")
        lines.append("")
        for record in records:
            lines.append(f"### {record.id} — {record.title}")
            lines.append("")
            lines.extend(_source_fields(record))
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _source_fields(record: SourceRecord) -> list[str]:
    fields: list[tuple[str, Any]] = [
        ("Tác giả", ", ".join(record.authors) if record.authors else None),
        ("Năm", record.year),
        ("Thiết kế nghiên cứu", record.study_design or None),
        ("Cỡ mẫu", record.sample_size),
        ("DOI", record.doi),
        ("PMID", record.pmid),
        ("URL", record.url),
    ]
    return [f"- {label}: {value}" for label, value in fields if value is not None]


def _manifest_json(
    *,
    project: ProjectManifest,
    script: Script,
    approval: ReviewRecord,
    staging_dir: Path,
    render_input: Path,
    citations: Mapping[str, list[SourceRecord]],
) -> str:
    """Describe the package: what was approved, by whom, and the file hashes."""
    manifest = {
        "schema_version": "1.0",
        "slug": project.slug,
        "language": project.language,
        "title": script.title,
        "production_input_hash": project.artifact_hashes[PRODUCTION_ARTIFACT],
        "approval_stale": False,
        "video_approval": {
            "id": str(approval.id),
            "decision": approval.decision,
            "reviewer": approval.reviewer,
            "reviewed_at": approval.reviewed_at.isoformat(),
            "note": approval.note,
        },
        "artifact_sha256": {
            CAPTION_NAME: sha256_file(staging_dir / CAPTION_NAME),
            OUTPUT_NAME: sha256_file(staging_dir / OUTPUT_NAME),
            SOURCES_NAME: sha256_file(staging_dir / SOURCES_NAME),
            RENDER_INPUT_NAME: sha256_file(render_input),
        },
        "source_markers": {
            marker: [record.id for record in records]
            for marker, records in citations.items()
        },
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
