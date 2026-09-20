"""Resumable orientation research: retryable working files, append-only history.

Orientation informs the doctor before an author brief exists. It never confirms a
brief, approves a gate, or publishes. Its working files under
``revisions/<active>/orientation/`` are rewritable; only a completed record named
by a successful stage manifest is authoritative.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from healthvideo import __version__
from healthvideo.domain.evidence import CandidateSource
from healthvideo.domain.orientation import (
    CompletedOrientation,
    OrientationScope,
    ProviderOutcome,
)
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.stage import StageManifest, StageStatus
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    write_yaml_atomic,
)
from healthvideo.storage.immutable import write_yaml_once
from healthvideo.storage.stages import append_stage_manifest

SEARCH_STAGE = "orientation_search"
STAGE = "orientation"
_SCOPE_ARTIFACT = "orientation/scope.yaml"
_COMPLETED_ARTIFACT = "orientation/completed/<run_id>.yaml"


@dataclass(frozen=True)
class OrientationRunResult:
    """One orientation search attempt: what each provider did, and what it yielded."""

    manifest: ProjectManifestV2
    provider_outcomes: tuple[ProviderOutcome, ...]
    candidates: tuple[CandidateSource, ...]


def _read_manifest(project_dir: Path) -> ProjectManifestV2:
    return ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))


def _write_manifest(project_dir: Path, manifest: ProjectManifestV2) -> None:
    write_yaml_atomic(project_dir / "project.yaml", manifest.model_dump(mode="json"))


def _revision_root(project_dir: Path, manifest: ProjectManifestV2) -> Path:
    return project_dir / "revisions" / manifest.active_revision


def _orientation_dir(project_dir: Path, manifest: ProjectManifestV2) -> Path:
    return _revision_root(project_dir, manifest) / "orientation"


def _topic_input_hash(
    project_dir: Path, manifest: ProjectManifestV2, scope: OrientationScope
) -> str:
    """Bind the run to the selected topic card and the requested scope together."""
    card_path = _revision_root(project_dir, manifest) / "topic" / "card.yaml"
    if not card_path.is_file():
        raise ValueError("orientation requires a selected topic card")
    return canonical_json_hash(
        {"topic": read_yaml(card_path), "scope": scope.model_dump(mode="json")}
    )


def _stage_manifest(
    *,
    stage: str,
    status: StageStatus,
    input_hash: str,
    output_hash: str | None,
    now: datetime,
) -> StageManifest:
    return StageManifest(
        stage=stage,
        status=status,
        input_hash=input_hash,
        output_hash=output_hash,
        tool_version=__version__,
        agent="healthvideo",
        model="not_applicable",
        started_at=now,
        completed_at=now if status is not StageStatus.RUNNING else None,
        estimated_input_tokens=0,
        estimated_output_tokens=0,
    )


def begin_orientation(
    project_dir: Path, scope: OrientationScope
) -> ProjectManifestV2:
    """Record the requested scope and enter resumable orientation research.

    Idempotent for unchanged input: re-running while already researching keeps the
    recorded scope and its input hash byte-identical.
    """
    manifest = _read_manifest(project_dir)
    if manifest.state not in {
        WorkflowState.TOPIC_SELECTED,
        WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS,
    }:
        raise ValueError(
            "orientation research starts from topic_selected or resumes from "
            f"orientation_research_in_progress, not {manifest.state.value}"
        )

    input_hash = _topic_input_hash(project_dir, manifest, scope)
    scope_path = _orientation_dir(project_dir, manifest) / "scope.yaml"
    payload = {**scope.model_dump(mode="json"), "topic_input_hash": input_hash}
    if not scope_path.is_file() or read_yaml(scope_path) != payload:
        write_yaml_atomic(scope_path, payload)

    if manifest.state is WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS:
        return manifest

    context = TransitionContext(
        active_revision=manifest.active_revision,
        current_input_hash=input_hash,
        validated_artifacts=frozenset({_SCOPE_ARTIFACT}),
    )
    advanced = transition_v2(
        manifest, WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS, context
    )
    _write_manifest(project_dir, advanced)
    return advanced


def _provider_name(client: Any, index: int) -> str:
    name = str(getattr(client, "name", "") or type(client).__name__).strip()
    return name or f"provider-{index}"


def _search_one(client: Any, query: str) -> list[CandidateSource]:
    if hasattr(client, "fetch_summaries"):
        return list(client.fetch_summaries(client.search(query, limit=10)))
    return list(client.search(query, limit=10))


def run_orientation_search(
    project_dir: Path,
    clients: Sequence[Any],
    *,
    now: datetime,
) -> OrientationRunResult:
    """Search each provider once, keeping failures distinct from empty results."""
    manifest = _read_manifest(project_dir)
    if manifest.state is not WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS:
        raise ValueError(
            "orientation search requires orientation_research_in_progress, "
            f"not {manifest.state.value}"
        )

    orientation_dir = _orientation_dir(project_dir, manifest)
    scope = read_yaml(orientation_dir / "scope.yaml")
    query = scope["topic_question"]

    outcomes: list[ProviderOutcome] = []
    candidates: list[CandidateSource] = []
    for index, client in enumerate(clients):
        provider = _provider_name(client, index)
        query_id = f"{provider}-{index}"
        try:
            found = _search_one(client, query)
        except (TypeError, ValueError, OSError) as error:
            outcomes.append(
                ProviderOutcome(
                    provider=provider,
                    query_id=query_id,
                    status="failed",
                    failure_class=type(error).__name__,
                    error_summary=str(error) or type(error).__name__,
                )
            )
            continue
        candidates.extend(found)
        outcomes.append(
            ProviderOutcome(
                provider=provider,
                query_id=query_id,
                status="completed" if found else "zero_results",
                result_count=len(found),
            )
        )

    write_yaml_atomic(
        orientation_dir / "search-log.yaml",
        {
            "schema_version": "1.0",
            "query": query,
            "searched_at": now.isoformat(),
            "provider_outcomes": [
                outcome.model_dump(mode="json") for outcome in outcomes
            ],
        },
    )
    candidates_path = orientation_dir / "candidates.jsonl"
    candidates_path.write_text(
        "".join(
            json.dumps(candidate.model_dump(mode="json"), ensure_ascii=False) + "\n"
            for candidate in candidates
        ),
        encoding="utf-8",
    )
    append_stage_manifest(
        _revision_root(project_dir, manifest),
        _stage_manifest(
            stage=SEARCH_STAGE,
            status=StageStatus.RUNNING,
            input_hash=scope["topic_input_hash"],
            output_hash=None,
            now=now,
        ),
    )
    return OrientationRunResult(
        manifest=manifest,
        provider_outcomes=tuple(outcomes),
        candidates=tuple(candidates),
    )


def _recorded_candidates(orientation_dir: Path) -> list[CandidateSource]:
    path = orientation_dir / "candidates.jsonl"
    if not path.is_file():
        return []
    return [
        CandidateSource.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def complete_orientation(
    project_dir: Path,
    completed: CompletedOrientation,
    *,
    now: datetime,
) -> ProjectManifestV2:
    """Publish a validated completed record and open the editorial boundary."""
    manifest = _read_manifest(project_dir)
    if manifest.state is not WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS:
        raise ValueError(
            "completing orientation requires orientation_research_in_progress, "
            f"not {manifest.state.value}"
        )
    if completed.revision != manifest.active_revision:
        raise ValueError(
            "completed orientation does not match the active revision: "
            f"{completed.revision} != {manifest.active_revision}"
        )

    orientation_dir = _orientation_dir(project_dir, manifest)
    scope = read_yaml(orientation_dir / "scope.yaml")
    if completed.topic_input_hash != scope["topic_input_hash"]:
        raise ValueError("completed orientation has a stale topic/scope input hash")
    completed.validate_candidate_binding(_recorded_candidates(orientation_dir))

    payload = completed.model_dump(mode="json")
    output_hash = canonical_json_hash(payload)
    write_yaml_once(orientation_dir / "completed" / f"{completed.run_id}.yaml", payload)
    append_stage_manifest(
        _revision_root(project_dir, manifest),
        _stage_manifest(
            stage=STAGE,
            status=StageStatus.COMPLETE,
            input_hash=completed.topic_input_hash,
            output_hash=output_hash,
            now=now,
        ),
    )

    context = TransitionContext(
        active_revision=manifest.active_revision,
        current_input_hash=output_hash,
        validated_artifacts=frozenset({_COMPLETED_ARTIFACT}),
    )
    advanced = transition_v2(
        manifest, WorkflowState.AWAITING_EDITORIAL_DIRECTION, context
    )
    _write_manifest(project_dir, advanced)
    return advanced


def read_authoritative_orientation(project_dir: Path) -> CompletedOrientation:
    """Return the completed record named by the latest successful stage manifest."""
    manifest = _read_manifest(project_dir)
    revision_root = _revision_root(project_dir, manifest)
    stage_dir = revision_root / "workflow" / "stages" / STAGE
    complete_stages: list[StageManifest] = []
    if stage_dir.is_dir():
        for path in sorted(stage_dir.glob("*.yaml")):
            record = StageManifest.model_validate(read_yaml(path))
            if record.status is StageStatus.COMPLETE:
                complete_stages.append(record)
    if not complete_stages:
        raise ValueError(f"no completed orientation stage record in {stage_dir}")

    latest = complete_stages[-1]
    completed_dir = revision_root / "orientation" / "completed"
    for path in sorted(completed_dir.glob("*.yaml")):
        payload = read_yaml(path)
        if canonical_json_hash(payload) != latest.output_hash:
            continue
        record = CompletedOrientation.model_validate(payload)
        if record.revision != manifest.active_revision:
            raise ValueError("authoritative orientation belongs to another revision")
        return record
    raise ValueError("no completed orientation matches the latest stage output hash")
