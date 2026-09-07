from enum import StrEnum

from pydantic import BaseModel, Field


class ProjectState(StrEnum):
    IDEA = "idea"
    EVIDENCE_IN_PROGRESS = "evidence_in_progress"
    EVIDENCE_READY = "evidence_ready"
    AWAITING_MEDICAL_REVIEW = "awaiting_medical_review"
    SCRIPT_APPROVED = "script_approved"
    PRODUCING = "producing"
    RENDERED = "rendered"
    AWAITING_VIDEO_REVIEW = "awaiting_video_review"
    APPROVED_TO_PUBLISH = "approved_to_publish"
    PUBLISHED = "published"


ORDER = list(ProjectState)


class ProjectManifest(BaseModel):
    schema_version: str = "1.0"
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    language: str = "vi"
    state: ProjectState = ProjectState.IDEA
    artifact_hashes: dict[str, str] = Field(default_factory=dict)


def transition(project: ProjectManifest, target: ProjectState) -> ProjectManifest:
    current_index = ORDER.index(project.state)
    if current_index + 1 >= len(ORDER) or ORDER[current_index + 1] is not target:
        raise ValueError(f"Invalid transition: {project.state} -> {target}")
    return project.model_copy(update={"state": target})
