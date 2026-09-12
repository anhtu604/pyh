"""Manual second-model handoff using the existing v2 side-state graph."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import mkdtemp
from xml.etree import ElementTree

from healthvideo.domain.agent_review import AgentReviewRequest, AgentReviewResponse
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)
from healthvideo.storage.immutable import promote_directory_once, write_yaml_once
from healthvideo.storage.project_layout import resolve_project_layout

HANDOFF_DIR = Path("handoffs") / "second-model"
_REQUIRED = (Path("author/brief.yaml"), Path("evidence/ledger.yaml"))
_OPTIONAL = (Path("script/script.yaml"), Path("storyboard/storyboard.yaml"))
_MAX_ARTIFACT_BYTES = 64 * 1024


def _project(project_dir: Path) -> tuple[ProjectManifestV2, Path]:
    layout = resolve_project_layout(project_dir)
    if not isinstance(layout.manifest, ProjectManifestV2):
        raise TypeError("Second-model review requires a v2 project")
    return layout.manifest, layout.artifact_root


def _source_artifacts(
    revision_root: Path, *, names: tuple[Path, ...] | None = None
) -> dict[str, dict]:
    paths = names or _REQUIRED + tuple(
        p for p in _OPTIONAL if (revision_root / p).is_file()
    )
    result = {}
    for relative in paths:
        path = revision_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"Second-model review source is missing: {path}")
        if path.stat().st_size > _MAX_ARTIFACT_BYTES:
            raise ValueError(f"Second-model review source is too large: {path}")
        result[relative.as_posix()] = read_yaml(path)
    return result


def _packet_bytes(
    project: ProjectManifestV2, reason_code: str, sources: dict[str, dict]
) -> bytes:
    root = ElementTree.Element(
        "second-model-review",
        {
            "project": project.slug,
            "revision": project.active_revision,
            "reason": reason_code,
        },
    )
    for name, data in sources.items():
        artifact = ElementTree.SubElement(root, "artifact", {"path": name})
        artifact.text = json.dumps(
            data,
            default=_json_date,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _json_date(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Unsupported review artifact value: {type(value).__name__}")


def request_second_model_review(
    project_dir: Path, *, reason_code: str, now: datetime
) -> Path:
    """Publish a bounded request once, then pause at the existing side state."""
    project, revision_root = _project(project_dir)
    if project.state not in {WorkflowState.EVIDENCE_READY, WorkflowState.DRAFT_READY}:
        raise ValueError("Second-model review requires evidence_ready or draft_ready")
    if not reason_code.strip():
        raise ValueError("Second-model review reason is required")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Second-model review time must be timezone-aware")

    sources = _source_artifacts(revision_root)
    packet = _packet_bytes(project, reason_code, sources)
    packet_hash = hashlib.sha256(packet).hexdigest()
    timestamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    request_id = f"{timestamp}-{packet_hash[:12]}"
    request = AgentReviewRequest(
        request_id=request_id,
        project_slug=project.slug,
        revision=project.active_revision,
        reason_code=reason_code,
        created_at=now,
        source_state=project.state,
        artifact_hashes={
            name: canonical_json_hash(data) for name, data in sources.items()
        },
        packet_sha256=packet_hash,
    )
    request_hash = canonical_json_hash(request.model_dump(mode="json"))
    context = TransitionContext(
        active_revision=project.active_revision,
        current_input_hash=request_hash,
        validated_artifacts=frozenset(),
    )
    paused = transition_v2(
        project,
        WorkflowState.AWAITING_SECOND_MODEL_REVIEW,
        context,
        reason_code=reason_code,
        resume_state=project.state,
        entered_at=now,
    )

    parent = revision_root / HANDOFF_DIR
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / request_id
    if destination.exists():
        raise FileExistsError(
            f"Second-model review request already exists: {destination}"
        )
    staging = Path(mkdtemp(prefix=f".{request_id}-", dir=parent))
    try:
        (staging / "packet.xml").write_bytes(packet)
        write_yaml_once(staging / "request.yaml", request.model_dump(mode="json"))
        stored = AgentReviewRequest.model_validate(read_yaml(staging / "request.yaml"))
        if stored != request or sha256_file(staging / "packet.xml") != packet_hash:
            raise ValueError("Staged second-model packet failed validation")
        promote_directory_once(staging, destination)
        write_yaml_atomic(project_dir / "project.yaml", paused.model_dump(mode="json"))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination


def complete_second_model_review(
    project_dir: Path, response: AgentReviewResponse, *, now: datetime
) -> ProjectManifestV2:
    """Accept a bound response and resume or route blocking issues to revision."""
    project, revision_root = _project(project_dir)
    if project.state is not WorkflowState.AWAITING_SECOND_MODEL_REVIEW:
        raise ValueError("Project is not awaiting second-model review")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Second-model review time must be timezone-aware")
    request_dir = revision_root / HANDOFF_DIR / response.request_id
    request = AgentReviewRequest.model_validate(read_yaml(request_dir / "request.yaml"))
    if (
        request.request_id != response.request_id
        or response.revision != project.active_revision
        or request.revision != project.active_revision
        or request.project_slug != project.slug
        or request.source_state != project.side_state.resume_state
        or request.created_at != project.side_state.entered_at
        or request.reason_code != project.side_state.reason_code
        or response.request_hash != canonical_json_hash(request.model_dump(mode="json"))
    ):
        raise ValueError("Second-model response does not match the active request")
    if sha256_file(request_dir / "packet.xml") != request.packet_sha256:
        raise ValueError("Second-model packet has changed")
    names = tuple(Path(name) for name in request.artifact_hashes)
    current = _source_artifacts(revision_root, names=names)
    current_hashes = {name: canonical_json_hash(data) for name, data in current.items()}
    if current_hashes != request.artifact_hashes:
        raise ValueError("Second-model review sources are stale")
    response_path = request_dir / "response.yaml"
    persisted_response = None
    if response_path.exists():
        persisted_response = AgentReviewResponse.model_validate(
            read_yaml(response_path)
        )
        if persisted_response != response:
            raise FileExistsError(
                f"A different second-model response already exists: {response_path}"
            )
    context = TransitionContext(
        active_revision=project.active_revision,
        current_input_hash=canonical_json_hash(response.model_dump(mode="json")),
        validated_artifacts=frozenset(),
    )
    if any(issue.severity == "blocking" for issue in response.issues):
        resume_state = (
            WorkflowState.RESEARCH_IN_PROGRESS
            if request.source_state is WorkflowState.EVIDENCE_READY
            else WorkflowState.DRAFT_READY
        )
        changed = transition_v2(
            project,
            WorkflowState.NEEDS_MEDICAL_REVISION,
            context,
            reason_code="second_model_blocking",
            resume_state=resume_state,
            entered_at=now,
        )
    else:
        changed = transition_v2(project, request.source_state, context)
    if persisted_response is None:
        write_yaml_once(response_path, response.model_dump(mode="json"))
    write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
    return changed
