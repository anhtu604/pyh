"""Topic discovery, triage inbox management, and topic selection workflow (§8)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.domain.topic import TopicCard, TopicScores, calculate_triage_rank
from healthvideo.storage.files import canonical_json_hash, read_yaml, write_yaml_atomic


def list_topics(inbox_dir: Path, status: str | None = None) -> list[TopicCard]:
    """List topic cards from inbox, optionally filtered by status, sorted by triage rank."""
    if not inbox_dir.is_dir():
        return []

    cards: list[TopicCard] = []
    for file_path in inbox_dir.glob("*.yaml"):
        try:
            data = read_yaml(file_path)
            card = TopicCard.model_validate(data)
            if status is None or card.status == status:
                cards.append(card)
        except (TypeError, ValueError, KeyError):
            pass

    cards.sort(key=lambda c: calculate_triage_rank(c.scores), reverse=True)
    return cards


def create_topic(
    inbox_dir: Path,
    title: str,
    question: str,
    slug: str,
    target_audience: str = "",
    scores: TopicScores | None = None,
    now: datetime | None = None,
) -> TopicCard:
    """Create a new topic card and persist it in the inbox directory."""
    inbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now or datetime.now().astimezone()
    card = TopicCard(
        slug=slug,
        title=title,
        question=question,
        target_audience=target_audience,
        scores=scores or TopicScores(),
        created_at=timestamp,
        status="inbox",
    )
    card_path = inbox_dir / f"{slug}.yaml"
    write_yaml_atomic(card_path, card.model_dump(mode="json"))
    return card


def reject_topic(
    card_path: Path,
    reason: str,
    now: datetime | None = None,
) -> TopicCard:
    """Mark a candidate topic as rejected with reason and audit timestamp."""
    data = read_yaml(card_path)
    data["status"] = "rejected"
    data["rejection_reason"] = reason.strip()
    card = TopicCard.model_validate(data)
    write_yaml_atomic(card_path, card.model_dump(mode="json"))
    return card


def select_topic(
    project_dir: Path,
    card: TopicCard,
    now: datetime | None = None,
) -> ProjectManifestV2:
    """Select a topic for a v2 project, save topic/card.yaml, and transition state."""
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    revision_root = project_dir / "revisions" / manifest.active_revision
    topic_dir = revision_root / "topic"
    topic_dir.mkdir(parents=True, exist_ok=True)

    card_dict = card.model_dump(mode="json")
    card_dict["status"] = "selected"
    if card.created_at is None:
        card_dict["created_at"] = (now or datetime.now().astimezone()).isoformat()

    card_file = topic_dir / "card.yaml"
    write_yaml_atomic(card_file, card_dict)

    input_hash = canonical_json_hash(card_dict)
    context = TransitionContext(
        active_revision=manifest.active_revision,
        current_input_hash=input_hash,
        validated_artifacts=frozenset({"topic/card.yaml"}),
    )
    new_manifest = transition_v2(manifest, WorkflowState.TOPIC_SELECTED, context)
    write_yaml_atomic(project_dir / "project.yaml", new_manifest.model_dump(mode="json"))
    return new_manifest
