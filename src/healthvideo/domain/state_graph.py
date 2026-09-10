"""Preconditioned main-path transitions for the parallel v2 workflow."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


class TransitionError(ValueError):
    """Raised when a v2 workflow transition does not meet its preconditions."""


@dataclass(frozen=True)
class TransitionContext:
    active_revision: str
    current_input_hash: str
    validated_artifacts: frozenset[str]
    reason_code: str | None = None
    new_revision_from: str | None = None
    run_published: bool | None = None
    staging_verified_unusable: bool | None = None


@dataclass(frozen=True)
class TransitionRule:
    required_artifacts: frozenset[str]
    requires_reason_code: bool = False
    requires_recovery_facts: bool = False

    def validate(
        self, project: ProjectManifestV2, context: TransitionContext
    ) -> None:
        if context.active_revision != project.active_revision:
            raise TransitionError("active revision does not match the project")
        if _SHA256_HEX.fullmatch(context.current_input_hash) is None:
            raise TransitionError("current input hash must be a lowercase SHA-256 hash")
        if context.new_revision_from is not None:
            raise TransitionError("new revision source must be confirmed by revision service")
        if not self.requires_recovery_facts and (
            context.run_published is not None
            or context.staging_verified_unusable is not None
        ):
            raise TransitionError("recovery facts are reserved for recovery transitions")
        if self.requires_reason_code and not (context.reason_code or "").strip():
            raise TransitionError("reason code is required for this transition")
        if self.requires_recovery_facts:
            if context.run_published is not False:
                raise TransitionError("run must be unpublished for recovery")
            if context.staging_verified_unusable is not True:
                raise TransitionError("staging must be verified unusable for recovery")

        missing = self.required_artifacts - context.validated_artifacts
        if missing:
            names = ", ".join(sorted(missing))
            raise TransitionError(f"missing required artifacts: {names}")


def _rule(
    *artifacts: str,
    requires_reason_code: bool = False,
    requires_recovery_facts: bool = False,
) -> TransitionRule:
    return TransitionRule(
        frozenset(artifacts), requires_reason_code, requires_recovery_facts
    )


MAIN_RULES: Mapping[tuple[WorkflowState, WorkflowState], TransitionRule] = {
    (WorkflowState.IDEA, WorkflowState.TOPIC_SELECTED): _rule("topic/card.yaml"),
    (WorkflowState.TOPIC_SELECTED, WorkflowState.AUTHOR_BRIEF_READY): _rule(
        "author/brief.yaml"
    ),
    (WorkflowState.AUTHOR_BRIEF_READY, WorkflowState.RESEARCH_IN_PROGRESS): _rule(
        "author/brief.yaml"
    ),
    (WorkflowState.RESEARCH_IN_PROGRESS, WorkflowState.EVIDENCE_READY): _rule(
        "evidence/ledger.yaml"
    ),
    (WorkflowState.EVIDENCE_READY, WorkflowState.DRAFT_READY): _rule(
        "script/script.yaml"
    ),
    (WorkflowState.DRAFT_READY, WorkflowState.AWAITING_MEDICAL_REVIEW): _rule(
        "script/script.yaml",
        "storyboard/storyboard.yaml",
        "assets/asset-manifest.yaml",
    ),
    (WorkflowState.AWAITING_MEDICAL_REVIEW, WorkflowState.MEDICALLY_APPROVED): _rule(
        "reviews/medical-approval.yaml"
    ),
    (WorkflowState.MEDICALLY_APPROVED, WorkflowState.PRODUCTION_IN_PROGRESS): _rule(
        "reviews/medical-approval.yaml"
    ),
    (WorkflowState.PRODUCTION_IN_PROGRESS, WorkflowState.AWAITING_VIDEO_REVIEW): _rule(
        "renders/render-manifest.json",
        "reviews/video-qa.json",
    ),
    (WorkflowState.AWAITING_VIDEO_REVIEW, WorkflowState.VIDEO_APPROVED): _rule(
        "reviews/video-approval.yaml"
    ),
    (WorkflowState.VIDEO_APPROVED, WorkflowState.PACKAGED): _rule(
        "publish/manifest.json"
    ),
    (WorkflowState.PACKAGED, WorkflowState.PUBLISHED_MANUAL): _rule(
        "publish/receipt.yaml"
    ),
    (WorkflowState.PRODUCTION_IN_PROGRESS, WorkflowState.MEDICALLY_APPROVED): _rule(
        "reviews/medical-approval.yaml",
        requires_reason_code=True,
        requires_recovery_facts=True,
    ),
}


def transition_v2(
    project: ProjectManifestV2,
    target: WorkflowState,
    context: TransitionContext,
) -> ProjectManifestV2:
    rule = MAIN_RULES.get((project.state, target))
    if rule is None:
        raise TransitionError(f"invalid v2 transition: {project.state} -> {target}")
    rule.validate(project, context)
    return project.model_copy(update={"state": target, "side_state": None})
