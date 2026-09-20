"""Preconditioned main-path and side-state transitions for the parallel v2 workflow."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from healthvideo.domain.project_v2 import (
    MAIN_STATES,
    SIDE_STATES,
    ProjectManifestV2,
    ResumableSideState,
    SideStateRecord,
    TopicRejectedSideState,
    WorkflowState,
)

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9]{3}$")


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
    requires_new_revision: bool = False

    def validate(
        self, project: ProjectManifestV2, context: TransitionContext
    ) -> None:
        if context.active_revision != project.active_revision:
            raise TransitionError("active revision does not match the project")
        if _SHA256_HEX.fullmatch(context.current_input_hash) is None:
            raise TransitionError("current input hash must be a lowercase SHA-256 hash")
        self._validate_revision_source(project, context)
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

    def _validate_revision_source(
        self, project: ProjectManifestV2, context: TransitionContext
    ) -> None:
        parent = context.new_revision_from
        if not self.requires_new_revision:
            if parent is not None:
                raise TransitionError(
                    "new revision source must be confirmed by revision service"
                )
            return
        if parent is None:
            raise TransitionError(
                "reopening requires a new revision from the revision service"
            )
        if _REVISION.fullmatch(parent) is None:
            raise TransitionError("new revision source must be a three-digit revision")
        if int(project.active_revision) != int(parent) + 1:
            raise TransitionError(
                "active revision must be the increment of its parent revision"
            )


def _rule(
    *artifacts: str,
    requires_reason_code: bool = False,
    requires_recovery_facts: bool = False,
    requires_new_revision: bool = False,
) -> TransitionRule:
    return TransitionRule(
        frozenset(artifacts),
        requires_reason_code=requires_reason_code,
        requires_recovery_facts=requires_recovery_facts,
        requires_new_revision=requires_new_revision,
    )


_CONTEXT_ONLY = _rule()


MAIN_RULES: Mapping[tuple[WorkflowState, WorkflowState], TransitionRule] = {
    (WorkflowState.IDEA, WorkflowState.TOPIC_SELECTED): _rule("topic/card.yaml"),
    (
        WorkflowState.TOPIC_SELECTED,
        WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS,
    ): _rule("orientation/scope.yaml"),
    (
        WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS,
        WorkflowState.AWAITING_EDITORIAL_DIRECTION,
    ): _rule("orientation/completed/<run_id>.yaml"),
    (
        WorkflowState.AWAITING_EDITORIAL_DIRECTION,
        WorkflowState.AUTHOR_BRIEF_READY,
    ): _rule(
        "orientation/completed/<run_id>.yaml", "author/brief.yaml"
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


class ResumePolicy(Enum):
    """How a side state records the state the workflow returns to."""

    SOURCE = "source"
    EXIT = "exit"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class SideEntryRule:
    """Which states may enter a side state and how its resume state is checked."""

    sources: frozenset[WorkflowState]
    resume: ResumePolicy
    context_rule: TransitionRule = _CONTEXT_ONLY

    def validate(
        self,
        project: ProjectManifestV2,
        side: WorkflowState,
        context: TransitionContext,
        resume_state: WorkflowState | None,
        exits: frozenset[WorkflowState],
    ) -> None:
        if project.state not in self.sources:
            raise TransitionError(f"invalid v2 side entry: {project.state} -> {side}")
        if self.resume is ResumePolicy.TERMINAL:
            if resume_state is not None:
                raise TransitionError(
                    f"terminal side state {side} does not record a resume state"
                )
        elif resume_state is None:
            raise TransitionError(f"resume state is required to enter {side}")
        elif resume_state not in exits:
            raise TransitionError(
                f"resume state {resume_state} is not a valid exit of {side}"
            )
        elif self.resume is ResumePolicy.SOURCE and resume_state is not project.state:
            raise TransitionError("resume state must match the state being left")
        self.context_rule.validate(project, context)


@dataclass(frozen=True)
class SideExitRule:
    """What a side state must satisfy before it may return to a main state.

    `required_reason_class` is checked against the reason supplied *at exit time*
    (`TransitionContext.reason_code`), never against the side state's entry reason:
    §6 words that exit "nếu phát hiện lỗi semantic", i.e. the defect is discovered
    while in the side state, after the entry reason was frozen into the record.
    The entry reason stays exactly as recorded; nothing here mutates it.
    """

    context_rule: TransitionRule = _CONTEXT_ONLY
    resumes_recorded_state: bool = False
    required_reason_class: str | None = None

    def validate(
        self,
        project: ProjectManifestV2,
        target: WorkflowState,
        context: TransitionContext,
        side_state: SideStateRecord,
    ) -> None:
        if self.resumes_recorded_state and (
            not isinstance(side_state, ResumableSideState)
            or target is not side_state.resume_state
        ):
            raise TransitionError("exit must return to the recorded resume state")
        self.context_rule.validate(project, context)
        if (
            self.required_reason_class is not None
            and (context.reason_code or "").strip() != self.required_reason_class
        ):
            raise TransitionError(
                f"exit to {target} requires reason class {self.required_reason_class}"
            )


# Deviation from §6, recorded on purpose: the table says `blocked` may be entered from
# "mọi state chưa kết thúc", which literally admits the resumable side states too. We
# narrow the source set to the non-terminal MAIN states because `ProjectManifestV2` has
# a single `side_state` slot: entering `blocked` from another side state would overwrite
# that state's `resume_state` and silently lose the resume target. Widening this set
# needs a nested side-state schema, which M1 does not own — deferred to M2. Do not add
# `SIDE_STATES` here without that schema.
_NON_TERMINAL_MAIN_STATES = MAIN_STATES - {WorkflowState.PUBLISHED_MANUAL}

_POST_MEDICAL_GATE_STATES = frozenset(
    {
        WorkflowState.MEDICALLY_APPROVED,
        WorkflowState.PRODUCTION_IN_PROGRESS,
        WorkflowState.AWAITING_VIDEO_REVIEW,
        WorkflowState.VIDEO_APPROVED,
        WorkflowState.PACKAGED,
    }
)


SIDE_EXIT_RULES: Mapping[tuple[WorkflowState, WorkflowState], SideExitRule] = {
    (WorkflowState.AWAITING_BROWSER_LOGIN, WorkflowState.IDEA): SideExitRule(
        resumes_recorded_state=True
    ),
    (
        WorkflowState.AWAITING_BROWSER_LOGIN,
        WorkflowState.RESEARCH_IN_PROGRESS,
    ): SideExitRule(resumes_recorded_state=True),
    (
        WorkflowState.AWAITING_SECOND_MODEL_REVIEW,
        WorkflowState.EVIDENCE_READY,
    ): SideExitRule(resumes_recorded_state=True),
    (
        WorkflowState.AWAITING_SECOND_MODEL_REVIEW,
        WorkflowState.DRAFT_READY,
    ): SideExitRule(resumes_recorded_state=True),
    (
        WorkflowState.NEEDS_MEDICAL_REVISION,
        WorkflowState.RESEARCH_IN_PROGRESS,
    ): SideExitRule(),
    (WorkflowState.NEEDS_MEDICAL_REVISION, WorkflowState.DRAFT_READY): SideExitRule(),
    (
        WorkflowState.NEEDS_PRODUCTION_REVISION,
        WorkflowState.PRODUCTION_IN_PROGRESS,
    ): SideExitRule(),
    (WorkflowState.NEEDS_PRODUCTION_REVISION, WorkflowState.DRAFT_READY): SideExitRule(
        context_rule=_rule(requires_reason_code=True),
        required_reason_class="semantic_issue",
    ),
    **{
        (WorkflowState.BLOCKED, target): SideExitRule(resumes_recorded_state=True)
        for target in sorted(_NON_TERMINAL_MAIN_STATES)
    },
    (WorkflowState.TOPIC_REJECTED, WorkflowState.TOPIC_SELECTED): SideExitRule(
        context_rule=_rule("topic/card.yaml", requires_new_revision=True)
    ),
}


SIDE_ENTRY_RULES: Mapping[WorkflowState, SideEntryRule] = {
    WorkflowState.AWAITING_BROWSER_LOGIN: SideEntryRule(
        frozenset({WorkflowState.IDEA, WorkflowState.RESEARCH_IN_PROGRESS}),
        ResumePolicy.SOURCE,
    ),
    WorkflowState.AWAITING_SECOND_MODEL_REVIEW: SideEntryRule(
        frozenset({WorkflowState.EVIDENCE_READY, WorkflowState.DRAFT_READY}),
        ResumePolicy.SOURCE,
    ),
    WorkflowState.NEEDS_MEDICAL_REVISION: SideEntryRule(
        _POST_MEDICAL_GATE_STATES
        | {
            WorkflowState.AWAITING_MEDICAL_REVIEW,
            WorkflowState.AWAITING_SECOND_MODEL_REVIEW,
        },
        ResumePolicy.EXIT,
    ),
    WorkflowState.NEEDS_PRODUCTION_REVISION: SideEntryRule(
        frozenset(
            {
                WorkflowState.PRODUCTION_IN_PROGRESS,
                WorkflowState.AWAITING_VIDEO_REVIEW,
                WorkflowState.VIDEO_APPROVED,
                WorkflowState.PACKAGED,
            }
        ),
        ResumePolicy.EXIT,
    ),
    WorkflowState.BLOCKED: SideEntryRule(
        _NON_TERMINAL_MAIN_STATES, ResumePolicy.SOURCE
    ),
    WorkflowState.TOPIC_REJECTED: SideEntryRule(
        frozenset({WorkflowState.RESEARCH_IN_PROGRESS, WorkflowState.EVIDENCE_READY}),
        ResumePolicy.TERMINAL,
    ),
}


def _exit_targets(side: WorkflowState) -> frozenset[WorkflowState]:
    return frozenset(target for source, target in SIDE_EXIT_RULES if source is side)


def _side_state_record(
    side: WorkflowState,
    resume_state: WorkflowState | None,
    reason_code: str,
    entered_at: datetime,
) -> SideStateRecord:
    if resume_state is None:
        return TopicRejectedSideState(
            type=side, reason_code=reason_code, entered_at=entered_at
        )
    return ResumableSideState(
        type=side,
        resume_state=resume_state,
        reason_code=reason_code,
        entered_at=entered_at,
    )


def _enter_side_state(
    project: ProjectManifestV2,
    side: WorkflowState,
    context: TransitionContext,
    reason_code: str | None,
    resume_state: WorkflowState | None,
    entered_at: datetime | None,
) -> ProjectManifestV2:
    rule = SIDE_ENTRY_RULES.get(side)
    if rule is None:
        raise TransitionError(f"unknown v2 side state: {side}")
    rule.validate(project, side, context, resume_state, _exit_targets(side))
    if context.reason_code is not None:
        raise TransitionError("a side-state reason must be passed as reason_code")
    if not (reason_code or "").strip():
        raise TransitionError(f"reason code is required to enter {side}")
    if entered_at is None:
        raise TransitionError(f"entered at is required to enter {side}")
    record = _side_state_record(side, resume_state, reason_code, entered_at)
    return project.model_copy(update={"state": side, "side_state": record})


def _exit_side_state(
    project: ProjectManifestV2,
    target: WorkflowState,
    context: TransitionContext,
) -> ProjectManifestV2:
    side_state = project.side_state
    if side_state is None:
        raise TransitionError(f"side state record is missing for {project.state}")
    rule = SIDE_EXIT_RULES.get((project.state, target))
    if rule is None:
        raise TransitionError(f"invalid v2 side exit: {project.state} -> {target}")
    rule.validate(project, target, context, side_state)
    return project.model_copy(update={"state": target, "side_state": None})


def _reject_side_state_fields(
    reason_code: str | None,
    resume_state: WorkflowState | None,
    entered_at: datetime | None,
) -> None:
    if reason_code is not None or resume_state is not None or entered_at is not None:
        raise TransitionError(
            "reason code, resume state and entered at are reserved for side-state entry"
        )


def transition_v2(
    project: ProjectManifestV2,
    target: WorkflowState,
    context: TransitionContext,
    *,
    reason_code: str | None = None,
    resume_state: WorkflowState | None = None,
    entered_at: datetime | None = None,
) -> ProjectManifestV2:
    if target in SIDE_STATES:
        return _enter_side_state(
            project, target, context, reason_code, resume_state, entered_at
        )
    _reject_side_state_fields(reason_code, resume_state, entered_at)
    if project.state in SIDE_STATES:
        return _exit_side_state(project, target, context)
    rule = MAIN_RULES.get((project.state, target))
    if rule is None:
        raise TransitionError(f"invalid v2 transition: {project.state} -> {target}")
    rule.validate(project, context)
    return project.model_copy(update={"state": target, "side_state": None})
