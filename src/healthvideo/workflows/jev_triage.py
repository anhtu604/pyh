from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.jev_decision import (
    ClaimTriageInput,
    JevAdvisoryRecord,
    SecondModelRoutingInput,
    TopicTriageInput,
)
from healthvideo.domain.topic import TopicCard
from healthvideo.jev.client import JevClient
from healthvideo.jev.config import resolve_jev_config
from healthvideo.storage.files import read_yaml
from healthvideo.storage.immutable import write_yaml_once
from healthvideo.storage.project_layout import resolve_project_layout


def triage_topic_advisory(
    card: TopicCard,
    *,
    client: JevClient | None = None,
    now: datetime | None = None,
) -> JevAdvisoryRecord:
    active_client = client or JevClient(config=resolve_jev_config())
    inp = TopicTriageInput(
        slug=card.slug,
        title=card.title,
        question=card.question,
        target_audience=card.target_audience,
        preventive_value=card.scores.preventive_value,
        evidence_readiness=card.scores.evidence_readiness,
        clarity=card.scores.clarity,
        harm_risk=card.scores.harm_risk,
        production_cost=card.scores.production_cost,
    )
    return active_client.evaluate_topic(inp, now=now)


def triage_claims_advisory(
    project_dir: Path,
    *,
    client: JevClient | None = None,
    now: datetime | None = None,
    write_artifact: bool = False,
) -> tuple[JevAdvisoryRecord, ...]:
    layout = resolve_project_layout(project_dir)
    ev_dir = layout.artifact_root / "evidence"
    ledger_path = ev_dir / "ledger.yaml"
    claims_path = ev_dir / "claims.yaml"
    sources_path = ev_dir / "records.yaml"

    claims: list[EvidenceClaim] = []
    sources_map: dict[str, SourceRecord] = {}

    if ledger_path.is_file():
        data = read_yaml(ledger_path)
        claims = [EvidenceClaim.model_validate(c) for c in data.get("claims", [])]
        for r in data.get("records", []):
            rec = SourceRecord.model_validate(r)
            sources_map[rec.id] = rec
    elif claims_path.is_file() and sources_path.is_file():
        c_data = read_yaml(claims_path)
        s_data = read_yaml(sources_path)
        raw_claims = c_data.get("claims", c_data) if isinstance(c_data, dict) else c_data
        raw_sources = s_data.get("records", s_data) if isinstance(s_data, dict) else s_data
        claims = [EvidenceClaim.model_validate(c) for c in raw_claims]
        for r in raw_sources:
            rec = SourceRecord.model_validate(r)
            sources_map[rec.id] = rec

    active_client = client or JevClient(config=resolve_jev_config())
    results: list[JevAdvisoryRecord] = []

    for claim in claims:
        source_types = [
            sources_map[s_id].study_design
            for s_id in claim.sources
            if s_id in sources_map and sources_map[s_id].study_design
        ]
        inp = ClaimTriageInput(
            claim_id=claim.id,
            text_public=claim.text_public,
            text_technical=claim.text_technical,
            claim_type=claim.type,
            certainty=claim.certainty,
            source_count=len(claim.sources),
            source_types=source_types,
        )
        record = active_client.evaluate_claim(inp, now=now)
        results.append(record)

    if write_artifact and results:
        target_file = ev_dir / "jev-claim-advisory.yaml"
        payload = {
            "schema_version": "1.0",
            "evaluated_at": (now or datetime.now(UTC)).isoformat(),
            "advisories": [r.model_dump(mode="json") for r in results],
        }
        write_yaml_once(target_file, payload)

    return tuple(results)


def recommend_second_model_review(
    project_dir: Path,
    *,
    client: JevClient | None = None,
    now: datetime | None = None,
    write_artifact: bool = False,
) -> JevAdvisoryRecord:
    layout = resolve_project_layout(project_dir)
    ev_dir = layout.artifact_root / "evidence"
    ledger_path = ev_dir / "ledger.yaml"

    claim_count = 0
    unrated_count = 0
    low_count = 0
    has_notes = False

    if ledger_path.is_file():
        data = read_yaml(ledger_path)
        for c in data.get("claims", []):
            claim = EvidenceClaim.model_validate(c)
            claim_count += 1
            if claim.certainty in ("unrated", ""):
                unrated_count += 1
            elif claim.certainty in ("low", "very_low"):
                low_count += 1
            if claim.doctor_notes.strip():
                has_notes = True

    inp = SecondModelRoutingInput(
        project_slug=layout.manifest.slug,
        revision=getattr(layout.manifest, "active_revision", "001"),
        source_state=str(getattr(layout.manifest, "state", "unknown")),
        claim_count=claim_count,
        unrated_certainty_count=unrated_count,
        low_certainty_count=low_count,
        has_doctor_notes=has_notes,
    )

    active_client = client or JevClient(config=resolve_jev_config())
    record = active_client.evaluate_second_model(inp, now=now)

    if write_artifact:
        handoffs_dir = layout.artifact_root / "handoffs"
        target_file = handoffs_dir / "jev-review-advisory.yaml"
        payload = {
            "schema_version": "1.0",
            "evaluated_at": (now or datetime.now(UTC)).isoformat(),
            "recommendation": record.model_dump(mode="json"),
        }
        write_yaml_once(target_file, payload)

    return record
