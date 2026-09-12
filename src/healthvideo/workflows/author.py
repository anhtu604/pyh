"""Persist author-owned briefs in the active v2 revision."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from healthvideo.domain.author import AuthorBrief
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.files import canonical_json_hash, read_yaml, write_yaml_atomic


def save_author_brief(
    project_dir: Path, brief: AuthorBrief, *, confirm: bool, now: datetime
) -> ProjectManifestV2:
    """Save an author brief and optionally confirm the guarded workflow edge."""
    del now
    manifest_path = project_dir / "project.yaml"
    manifest = ProjectManifestV2.model_validate(read_yaml(manifest_path))
    if confirm and manifest.state is not WorkflowState.TOPIC_SELECTED:
        raise ValueError("author brief can only be confirmed from topic_selected")

    brief_path = (
        project_dir
        / "revisions"
        / manifest.active_revision
        / "author"
        / "brief.yaml"
    )
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_data = brief.model_dump(mode="json")
    write_yaml_atomic(brief_path, brief_data)

    if not confirm:
        return manifest

    context = TransitionContext(
        active_revision=manifest.active_revision,
        current_input_hash=canonical_json_hash(brief_data),
        validated_artifacts=frozenset({"author/brief.yaml"}),
    )
    updated = transition_v2(manifest, WorkflowState.AUTHOR_BRIEF_READY, context)
    write_yaml_atomic(manifest_path, updated.model_dump(mode="json"))
    return updated
