from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkflowState(StrEnum):
    IDEA = "idea"
    TOPIC_SELECTED = "topic_selected"
    AUTHOR_BRIEF_READY = "author_brief_ready"
    RESEARCH_IN_PROGRESS = "research_in_progress"
    EVIDENCE_READY = "evidence_ready"
    DRAFT_READY = "draft_ready"
    AWAITING_MEDICAL_REVIEW = "awaiting_medical_review"
    MEDICALLY_APPROVED = "medically_approved"
    PRODUCTION_IN_PROGRESS = "production_in_progress"
    AWAITING_VIDEO_REVIEW = "awaiting_video_review"
    VIDEO_APPROVED = "video_approved"
    PACKAGED = "packaged"
    PUBLISHED_MANUAL = "published_manual"
    AWAITING_BROWSER_LOGIN = "awaiting_browser_login"
    AWAITING_SECOND_MODEL_REVIEW = "awaiting_second_model_review"
    NEEDS_MEDICAL_REVISION = "needs_medical_revision"
    NEEDS_PRODUCTION_REVISION = "needs_production_revision"
    BLOCKED = "blocked"
    TOPIC_REJECTED = "topic_rejected"


MAIN_STATES = frozenset(
    {
        WorkflowState.IDEA,
        WorkflowState.TOPIC_SELECTED,
        WorkflowState.AUTHOR_BRIEF_READY,
        WorkflowState.RESEARCH_IN_PROGRESS,
        WorkflowState.EVIDENCE_READY,
        WorkflowState.DRAFT_READY,
        WorkflowState.AWAITING_MEDICAL_REVIEW,
        WorkflowState.MEDICALLY_APPROVED,
        WorkflowState.PRODUCTION_IN_PROGRESS,
        WorkflowState.AWAITING_VIDEO_REVIEW,
        WorkflowState.VIDEO_APPROVED,
        WorkflowState.PACKAGED,
        WorkflowState.PUBLISHED_MANUAL,
    }
)

RESUMABLE_SIDE_STATES = frozenset(
    {
        WorkflowState.AWAITING_BROWSER_LOGIN,
        WorkflowState.AWAITING_SECOND_MODEL_REVIEW,
        WorkflowState.NEEDS_MEDICAL_REVISION,
        WorkflowState.NEEDS_PRODUCTION_REVISION,
        WorkflowState.BLOCKED,
    }
)

SIDE_STATES = RESUMABLE_SIDE_STATES | {WorkflowState.TOPIC_REJECTED}


class ResumableSideState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal[
        WorkflowState.AWAITING_BROWSER_LOGIN,
        WorkflowState.AWAITING_SECOND_MODEL_REVIEW,
        WorkflowState.NEEDS_MEDICAL_REVISION,
        WorkflowState.NEEDS_PRODUCTION_REVISION,
        WorkflowState.BLOCKED,
    ]
    resume_state: WorkflowState
    reason_code: str = Field(pattern=r"\S")
    entered_at: datetime


class TopicRejectedSideState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal[WorkflowState.TOPIC_REJECTED]
    reason_code: str = Field(pattern=r"\S")
    entered_at: datetime


SideStateRecord = Annotated[
    ResumableSideState | TopicRejectedSideState,
    Field(discriminator="type"),
]


class ProjectManifestV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    language: str = "vi"
    state: WorkflowState = WorkflowState.IDEA
    active_revision: str = Field(default="001", pattern=r"^[0-9]{3}$")
    side_state: SideStateRecord | None = None
    artifact_hashes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_side_state(self) -> "ProjectManifestV2":
        if self.state in SIDE_STATES:
            if self.side_state is None or self.side_state.type != self.state:
                raise ValueError("side_state must match a side workflow state")
        elif self.side_state is not None:
            raise ValueError("side_state must be null for a main workflow state")
        return self
