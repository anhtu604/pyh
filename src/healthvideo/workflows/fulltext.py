"""Fulltext acquisition/indexing without changing project workflow state."""

import xml.etree.ElementTree as ET
from pathlib import Path

from healthvideo.domain.evidence import SourceRecord
from healthvideo.domain.project_v2 import ProjectManifestV2
from healthvideo.evidence import fulltext as ft
from healthvideo.storage.files import read_yaml, write_yaml_atomic


def project_sources(project: Path) -> tuple[Path, list[SourceRecord]]:
    manifest = ProjectManifestV2.model_validate(read_yaml(project / "project.yaml"))
    revision = project / "revisions" / manifest.active_revision
    path = revision / "evidence/ledger.yaml"
    if not path.is_file():
        path = revision / "evidence/records.yaml"
    data = read_yaml(path)
    rows = data.get("records", []) if isinstance(data, dict) else data
    return revision, [SourceRecord.model_validate(row) for row in rows]


def acquire_fulltext(project: Path) -> list[dict]:
    revision, records = project_sources(project)
    rows = []
    for record in records:
        # Reuse matching OA cache; prefer a newly available OA copy over user PDF.
        cached = ft.load_fulltext(record.id, record)
        value = (
            cached if cached is not None and cached.origin == "open_access" else None
        )
        error = None
        if value is None:
            try:
                value = ft.fetch_open_access(record)
            except (OSError, ValueError, ET.ParseError) as exc:
                error = f"{type(exc).__name__}: OA retrieval failed"
        if value is None:
            value = ft.extract_user_pdf(record, ft.CACHE_DIR / "inbox") or cached
        row = {
            "source_id": record.id,
            "origin": value.origin if value else "missing",
            "license": value.license if value else None,
            "sha256": value.sha256 if value else None,
            "cache_path": str(ft.cache_path(record.id).resolve()) if value else None,
            "sections": len(value.sections) if value else 0,
            "pages": len({s.page for s in value.sections if s.page}) if value else 0,
        }
        if value is None:
            row["doi_url"] = f"https://doi.org/{record.doi}" if record.doi else None
            row["inbox_filenames"] = ft.pdf_names(record)
        if error:
            row["warning"] = error
        rows.append(row)
    write_yaml_atomic(revision / "research/fulltext-index.yaml", {"sources": rows})
    return rows
