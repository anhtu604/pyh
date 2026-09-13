"""Resolve public source markers to validated ledger records."""

from collections.abc import Mapping, Sequence
from typing import Any

from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Scene


def resolve_citations(
    script: Script,
    ledger: Mapping[str, Any],
    scenes: Sequence[Scene],
    *,
    strict_line_ids: bool = False,
) -> dict[str, list[SourceRecord]]:
    records = {
        record.id: record
        for record in (
            SourceRecord.model_validate(item) for item in ledger.get("records", [])
        )
    }
    claims = {
        claim.id: claim
        for claim in (
            EvidenceClaim.model_validate(item) for item in ledger.get("claims", [])
        )
    }
    lines_by_id = {line.id: line for line in script.lines}
    citations: dict[str, list[SourceRecord]] = {}
    for index, scene in enumerate(scenes):
        if strict_line_ids:
            line = lines_by_id.get(scene.script_line_id or "")
            if index == 0 and line is not None and line.claim_id and not line.source_marker:
                raise ValueError("hook claim requires source marker")
            if line is None or line.claim_id != scene.claim_id or line.source_marker != scene.source_marker:
                raise ValueError(f"Scene {scene.id} claim/source marker mismatches script line")
        else:
            if scene.source_marker is None:
                continue
            line = next(
                (item for item in script.lines if item.source_marker == scene.source_marker and item.claim_id == scene.claim_id),
                None,
            )
            if line is None:
                raise ValueError(f"Render scene {scene.id} shows {scene.source_marker} without a script claim/source mapping")
        if line.claim_id is not None:
            claim = claims.get(line.claim_id)
            if claim is None:
                raise ValueError(f"Script line {line.id} refers to undefined claim {line.claim_id}")
            if strict_line_ids:
                for source_id in claim.sources:
                    if source_id not in records:
                        raise ValueError(f"Script line {line.id} cites undefined source {source_id}")
        if scene.source_marker is None:
            continue
        if line.claim_id is None:
            raise ValueError(f"Scene {scene.id} has source marker without claim")
        claim = claims[line.claim_id]
        cited = []
        for source_id in claim.sources:
            record = records.get(source_id)
            if record is None:
                raise ValueError(f"Script line {line.id} cites undefined source {source_id}")
            cited.append(record)
        if not cited:
            raise ValueError(f"Scene {scene.id} marker has no source")
        existing = citations.get(scene.source_marker)
        if existing is not None and [item.id for item in existing] != [item.id for item in cited]:
            raise ValueError(f"Scene {scene.id} reuses marker for a different source mapping")
        citations[scene.source_marker] = cited
    return citations
