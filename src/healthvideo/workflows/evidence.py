"""Evidence intake, literature searching, candidate selection, and ledger synthesis workflow (§9)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from healthvideo.domain.evidence import (
    CandidateSource,
    EvidenceClaim,
    EvidenceQuestion,
    SearchLogRecord,
    SourceRecord,
    SourceSelection,
)
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.files import canonical_json_hash, read_yaml, write_yaml_atomic


def record_question(
    project_dir: Path,
    question: EvidenceQuestion,
    now: datetime | None = None,
) -> tuple[Path, ProjectManifestV2]:
    """Record PICO research question and advance state to research_in_progress if at author_brief_ready."""
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    ev_dir = project_dir / "revisions" / manifest.active_revision / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    q_path = ev_dir / "question.yaml"
    write_yaml_atomic(q_path, question.model_dump(mode="json"))

    if manifest.state == WorkflowState.AUTHOR_BRIEF_READY:
        brief_file = project_dir / "revisions" / manifest.active_revision / "author" / "brief.yaml"
        brief_data = read_yaml(brief_file) if brief_file.is_file() else {}
        input_hash = canonical_json_hash(brief_data)
        context = TransitionContext(
            active_revision=manifest.active_revision,
            current_input_hash=input_hash,
            validated_artifacts=frozenset({"author/brief.yaml"}),
        )
        manifest = transition_v2(manifest, WorkflowState.RESEARCH_IN_PROGRESS, context)
        write_yaml_atomic(project_dir / "project.yaml", manifest.model_dump(mode="json"))

    return q_path, manifest


def search_literature(
    project_dir: Path,
    question: EvidenceQuestion,
    clients: Sequence[Any],
    now: datetime | None = None,
) -> SearchLogRecord:
    """Execute search across configured clients, logging queries and candidates to disk."""
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    ev_dir = project_dir / "revisions" / manifest.active_revision / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)

    query = " ".join(question.search_keywords)
    candidates: list[CandidateSource] = []
    for client in clients:
        try:
            if hasattr(client, "fetch_summaries"):
                pmids = client.search(query, limit=10)
                items = client.fetch_summaries(pmids)
                candidates.extend(items)
            elif hasattr(client, "search"):
                items = client.search(query, limit=10)
                candidates.extend(items)
        except (TypeError, ValueError, OSError):
            pass

    candidates_path = ev_dir / "candidates.jsonl"
    with candidates_path.open("a", encoding="utf-8") as f:
        for c in candidates:
            serialized = json.dumps(c.model_dump(mode="json"), ensure_ascii=False)
            f.write(f"{serialized}\n")

    timestamp = now or datetime.now().astimezone()
    log = SearchLogRecord(
        database="multi",
        query=query,
        searched_at=timestamp,
        total_results=len(candidates),
        retrieved_count=len(candidates),
    )
    search_log_path = ev_dir / "search-log.yaml"
    write_yaml_atomic(search_log_path, log.model_dump(mode="json"))
    return log


def record_source_selections(
    project_dir: Path,
    selections: Sequence[SourceSelection],
) -> tuple[Path, Path]:
    """Record included and excluded candidate sources with rationale."""
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    ev_dir = project_dir / "revisions" / manifest.active_revision / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)

    included = [s.model_dump(mode="json") for s in selections if s.decision == "included"]
    excluded = [s.model_dump(mode="json") for s in selections if s.decision == "excluded"]

    inc_path = ev_dir / "included-sources.yaml"
    exc_path = ev_dir / "excluded-sources.yaml"
    write_yaml_atomic(inc_path, {"sources": included})
    write_yaml_atomic(exc_path, {"sources": excluded})
    return inc_path, exc_path


def build_evidence_ledger(
    project_dir: Path,
    claims: Sequence[EvidenceClaim],
    sources: Sequence[SourceRecord],
    now: datetime | None = None,
) -> tuple[Path, ProjectManifestV2]:
    """Build and validate evidence/ledger.yaml, ensuring no retracted sources, and advance state."""
    source_ids = {s.id for s in sources}
    for s in sources:
        if s.retraction_status == "retracted":
            raise ValueError(f"Source {s.id} is retracted and cannot be included in evidence ledger")

    for c in claims:
        for src_id in c.sources:
            if src_id not in source_ids:
                raise ValueError(f"Claim {c.id} references unknown source {src_id}")

    ledger_data = {
        "schema_version": "1.0",
        "records": [s.model_dump(mode="json") for s in sources],
        "claims": [c.model_dump(mode="json") for c in claims],
    }

    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    ev_dir = project_dir / "revisions" / manifest.active_revision / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = ev_dir / "ledger.yaml"
    write_yaml_atomic(ledger_path, ledger_data)

    if manifest.state == WorkflowState.RESEARCH_IN_PROGRESS:
        input_hash = canonical_json_hash(ledger_data)
        context = TransitionContext(
            active_revision=manifest.active_revision,
            current_input_hash=input_hash,
            validated_artifacts=frozenset({"evidence/ledger.yaml"}),
        )
        manifest = transition_v2(manifest, WorkflowState.EVIDENCE_READY, context)
        write_yaml_atomic(project_dir / "project.yaml", manifest.model_dump(mode="json"))

    return ledger_path, manifest


def reject_topic_for_lack_of_evidence(
    project_dir: Path,
    reason: str,
    now: datetime | None = None,
) -> ProjectManifestV2:
    """Transition project state to TOPIC_REJECTED when literature search finds insufficient evidence."""
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    timestamp = now or datetime.now().astimezone()
    input_hash = canonical_json_hash({"reason": reason})
    context = TransitionContext(
        active_revision=manifest.active_revision,
        current_input_hash=input_hash,
        validated_artifacts=frozenset(),
    )
    new_manifest = transition_v2(
        manifest,
        WorkflowState.TOPIC_REJECTED,
        context,
        reason_code=reason,
        entered_at=timestamp,
    )
    write_yaml_atomic(project_dir / "project.yaml", new_manifest.model_dump(mode="json"))
    return new_manifest
