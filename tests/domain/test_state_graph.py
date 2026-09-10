from datetime import UTC, datetime

import pytest

from healthvideo.domain.project_v2 import (
    MAIN_STATES,
    SIDE_STATES,
    ProjectManifestV2,
    ResumableSideState,
    SideStateRecord,
    TopicRejectedSideState,
    WorkflowState,
)
from healthvideo.domain.state_graph import (
    MAIN_RULES,
    SIDE_ENTRY_RULES,
    SIDE_EXIT_RULES,
    TransitionContext,
    TransitionError,
    transition_v2,
)

MAIN_EDGES = {
    (WorkflowState.IDEA, WorkflowState.TOPIC_SELECTED),
    (WorkflowState.TOPIC_SELECTED, WorkflowState.AUTHOR_BRIEF_READY),
    (WorkflowState.AUTHOR_BRIEF_READY, WorkflowState.RESEARCH_IN_PROGRESS),
    (WorkflowState.RESEARCH_IN_PROGRESS, WorkflowState.EVIDENCE_READY),
    (WorkflowState.EVIDENCE_READY, WorkflowState.DRAFT_READY),
    (WorkflowState.DRAFT_READY, WorkflowState.AWAITING_MEDICAL_REVIEW),
    (WorkflowState.AWAITING_MEDICAL_REVIEW, WorkflowState.MEDICALLY_APPROVED),
    (WorkflowState.MEDICALLY_APPROVED, WorkflowState.PRODUCTION_IN_PROGRESS),
    (WorkflowState.PRODUCTION_IN_PROGRESS, WorkflowState.AWAITING_VIDEO_REVIEW),
    (WorkflowState.AWAITING_VIDEO_REVIEW, WorkflowState.VIDEO_APPROVED),
    (WorkflowState.VIDEO_APPROVED, WorkflowState.PACKAGED),
    (WorkflowState.PACKAGED, WorkflowState.PUBLISHED_MANUAL),
    (WorkflowState.PRODUCTION_IN_PROGRESS, WorkflowState.MEDICALLY_APPROVED),
}


def test_main_graph_requires_artifacts_and_active_revision() -> None:
    project = ProjectManifestV2(slug="muoi-va-huyet-ap", state="draft_ready")
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset(),
    )

    with pytest.raises(TransitionError, match="missing required artifacts"):
        transition_v2(project, WorkflowState.AWAITING_MEDICAL_REVIEW, context)


def test_main_graph_has_only_the_documented_main_and_recovery_edges() -> None:
    assert set(MAIN_RULES) == MAIN_EDGES


def test_main_graph_rejects_mismatched_revision_and_invalid_input_hash() -> None:
    project = ProjectManifestV2(slug="muoi-va-huyet-ap")
    artifacts = frozenset({"topic/card.yaml"})

    with pytest.raises(TransitionError, match="active revision"):
        transition_v2(
            project,
            WorkflowState.TOPIC_SELECTED,
            TransitionContext("002", "0" * 64, artifacts),
        )
    with pytest.raises(TransitionError, match="current input hash"):
        transition_v2(
            project,
            WorkflowState.TOPIC_SELECTED,
            TransitionContext("001", "not-a-hash", artifacts),
        )


def test_main_graph_advances_with_the_rule_specific_validated_artifacts() -> None:
    project = ProjectManifestV2(slug="muoi-va-huyet-ap")
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset({"topic/card.yaml"}),
    )

    changed = transition_v2(project, WorkflowState.TOPIC_SELECTED, context)

    assert changed.state is WorkflowState.TOPIC_SELECTED
    assert changed.side_state is None


def test_main_graph_rejects_non_main_edge() -> None:
    project = ProjectManifestV2(slug="muoi-va-huyet-ap")
    context = TransitionContext("001", "0" * 64, frozenset({"topic/card.yaml"}))

    with pytest.raises(TransitionError, match="invalid v2 transition"):
        transition_v2(project, WorkflowState.DRAFT_READY, context)


@pytest.mark.parametrize(
    ("run_published", "staging_verified_unusable", "reason_code", "message"),
    [
        (None, True, "staging_unusable", "run must be unpublished"),
        (True, True, "staging_unusable", "run must be unpublished"),
        (False, None, "staging_unusable", "staging must be verified unusable"),
        (False, False, "staging_unusable", "staging must be verified unusable"),
        (False, True, None, "reason code"),
        (False, True, "", "reason code"),
        (False, True, "   ", "reason code"),
    ],
)
def test_recovery_requires_verified_unpublished_unusable_run(
    run_published: bool | None,
    staging_verified_unusable: bool | None,
    reason_code: str | None,
    message: str,
) -> None:
    project = ProjectManifestV2(
        slug="muoi-va-huyet-ap", state=WorkflowState.PRODUCTION_IN_PROGRESS
    )
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset({"reviews/medical-approval.yaml"}),
        reason_code=reason_code,
        run_published=run_published,
        staging_verified_unusable=staging_verified_unusable,
    )

    with pytest.raises(TransitionError, match=message):
        transition_v2(project, WorkflowState.MEDICALLY_APPROVED, context)


def test_recovery_advances_only_after_verified_unpublished_unusable_run() -> None:
    project = ProjectManifestV2(
        slug="muoi-va-huyet-ap", state=WorkflowState.PRODUCTION_IN_PROGRESS
    )
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset({"reviews/medical-approval.yaml"}),
        reason_code="staging_unusable",
        run_published=False,
        staging_verified_unusable=True,
    )

    assert transition_v2(project, WorkflowState.MEDICALLY_APPROVED, context).state is (
        WorkflowState.MEDICALLY_APPROVED
    )


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"new_revision_from": "000"}, "revision service"),
        ({"run_published": False}, "reserved for recovery"),
        ({"staging_verified_unusable": True}, "reserved for recovery"),
    ],
)
def test_ordinary_edge_rejects_revision_and_recovery_only_context(
    extra: dict[str, bool | str], message: str
) -> None:
    project = ProjectManifestV2(slug="muoi-va-huyet-ap")
    valid = {
        "active_revision": "001",
        "current_input_hash": "0" * 64,
        "validated_artifacts": frozenset({"topic/card.yaml"}),
    }

    with pytest.raises(TransitionError, match=message):
        transition_v2(
            project,
            WorkflowState.TOPIC_SELECTED,
            TransitionContext(**valid, **extra),
        )


FROZEN_NOW = datetime(2026, 9, 10, 7, 30, tzinfo=UTC)

ALL_ARTIFACTS = frozenset(
    {
        "topic/card.yaml",
        "author/brief.yaml",
        "evidence/ledger.yaml",
        "script/script.yaml",
        "storyboard/storyboard.yaml",
        "assets/asset-manifest.yaml",
        "reviews/medical-approval.yaml",
        "renders/render-manifest.json",
        "reviews/video-qa.json",
        "reviews/video-approval.yaml",
        "publish/manifest.json",
        "publish/receipt.yaml",
    }
)

SIDE_ENTRY_CASES = [
    (WorkflowState.IDEA, WorkflowState.AWAITING_BROWSER_LOGIN, WorkflowState.IDEA),
    (
        WorkflowState.RESEARCH_IN_PROGRESS,
        WorkflowState.AWAITING_BROWSER_LOGIN,
        WorkflowState.RESEARCH_IN_PROGRESS,
    ),
    (
        WorkflowState.EVIDENCE_READY,
        WorkflowState.AWAITING_SECOND_MODEL_REVIEW,
        WorkflowState.EVIDENCE_READY,
    ),
    (
        WorkflowState.DRAFT_READY,
        WorkflowState.AWAITING_SECOND_MODEL_REVIEW,
        WorkflowState.DRAFT_READY,
    ),
    (
        WorkflowState.AWAITING_MEDICAL_REVIEW,
        WorkflowState.NEEDS_MEDICAL_REVISION,
        WorkflowState.RESEARCH_IN_PROGRESS,
    ),
    (
        WorkflowState.MEDICALLY_APPROVED,
        WorkflowState.NEEDS_MEDICAL_REVISION,
        WorkflowState.DRAFT_READY,
    ),
    (
        WorkflowState.PACKAGED,
        WorkflowState.NEEDS_MEDICAL_REVISION,
        WorkflowState.DRAFT_READY,
    ),
    (
        WorkflowState.AWAITING_SECOND_MODEL_REVIEW,
        WorkflowState.NEEDS_MEDICAL_REVISION,
        WorkflowState.DRAFT_READY,
    ),
    (
        WorkflowState.PRODUCTION_IN_PROGRESS,
        WorkflowState.NEEDS_PRODUCTION_REVISION,
        WorkflowState.PRODUCTION_IN_PROGRESS,
    ),
    (
        WorkflowState.AWAITING_VIDEO_REVIEW,
        WorkflowState.NEEDS_PRODUCTION_REVISION,
        WorkflowState.PRODUCTION_IN_PROGRESS,
    ),
    (
        WorkflowState.VIDEO_APPROVED,
        WorkflowState.NEEDS_PRODUCTION_REVISION,
        WorkflowState.DRAFT_READY,
    ),
    (
        WorkflowState.PACKAGED,
        WorkflowState.NEEDS_PRODUCTION_REVISION,
        WorkflowState.PRODUCTION_IN_PROGRESS,
    ),
    (WorkflowState.IDEA, WorkflowState.BLOCKED, WorkflowState.IDEA),
    (WorkflowState.DRAFT_READY, WorkflowState.BLOCKED, WorkflowState.DRAFT_READY),
    (WorkflowState.PACKAGED, WorkflowState.BLOCKED, WorkflowState.PACKAGED),
]

SIDE_EXIT_EDGES = {
    (WorkflowState.AWAITING_BROWSER_LOGIN, WorkflowState.IDEA),
    (WorkflowState.AWAITING_BROWSER_LOGIN, WorkflowState.RESEARCH_IN_PROGRESS),
    (WorkflowState.AWAITING_SECOND_MODEL_REVIEW, WorkflowState.EVIDENCE_READY),
    (WorkflowState.AWAITING_SECOND_MODEL_REVIEW, WorkflowState.DRAFT_READY),
    (WorkflowState.NEEDS_MEDICAL_REVISION, WorkflowState.RESEARCH_IN_PROGRESS),
    (WorkflowState.NEEDS_MEDICAL_REVISION, WorkflowState.DRAFT_READY),
    (WorkflowState.NEEDS_PRODUCTION_REVISION, WorkflowState.PRODUCTION_IN_PROGRESS),
    (WorkflowState.NEEDS_PRODUCTION_REVISION, WorkflowState.DRAFT_READY),
    (WorkflowState.TOPIC_REJECTED, WorkflowState.TOPIC_SELECTED),
} | {
    (WorkflowState.BLOCKED, state)
    for state in MAIN_STATES - {WorkflowState.PUBLISHED_MANUAL}
}


@pytest.fixture
def frozen_now() -> datetime:
    return FROZEN_NOW


def manifest_at(
    state: WorkflowState,
    *,
    active_revision: str = "001",
    resume_state: WorkflowState | None = None,
    reason_code: str = "review_required",
    entered_at: datetime = FROZEN_NOW,
) -> ProjectManifestV2:
    side_state: SideStateRecord | None = None
    if state is WorkflowState.TOPIC_REJECTED:
        side_state = TopicRejectedSideState(
            type=state, reason_code=reason_code, entered_at=entered_at
        )
    elif state in SIDE_STATES:
        side_state = ResumableSideState(
            type=state,
            resume_state=resume_state or state,
            reason_code=reason_code,
            entered_at=entered_at,
        )
    return ProjectManifestV2(
        slug="muoi-va-huyet-ap",
        state=state,
        active_revision=active_revision,
        side_state=side_state,
    )


def valid_context(active_revision: str = "001", **extra: object) -> TransitionContext:
    return TransitionContext(
        active_revision=active_revision,
        current_input_hash="0" * 64,
        validated_artifacts=ALL_ARTIFACTS,
        **extra,
    )


def test_side_tables_cover_exactly_the_documented_side_states() -> None:
    assert set(SIDE_ENTRY_RULES) == set(SIDE_STATES)
    assert set(SIDE_EXIT_RULES) == SIDE_EXIT_EDGES


@pytest.mark.parametrize(("source", "side", "resume"), SIDE_ENTRY_CASES)
def test_side_state_entry_records_resume_reason_and_time(
    source: WorkflowState,
    side: WorkflowState,
    resume: WorkflowState,
    frozen_now: datetime,
) -> None:
    changed = transition_v2(
        manifest_at(source),
        side,
        valid_context(),
        reason_code="review_required",
        resume_state=resume,
        entered_at=frozen_now,
    )

    assert changed.side_state is not None
    assert changed.side_state.reason_code == "review_required"
    assert changed.side_state.entered_at == frozen_now
    assert changed.state is side
    assert changed.side_state.type is side
    assert changed.side_state.resume_state is resume


def test_topic_rejected_entry_records_no_resume_state(frozen_now: datetime) -> None:
    changed = transition_v2(
        manifest_at(WorkflowState.EVIDENCE_READY),
        WorkflowState.TOPIC_REJECTED,
        valid_context(),
        reason_code="doctor_rejected_topic",
        entered_at=frozen_now,
    )

    assert changed.state is WorkflowState.TOPIC_REJECTED
    assert changed.side_state == TopicRejectedSideState(
        type=WorkflowState.TOPIC_REJECTED,
        reason_code="doctor_rejected_topic",
        entered_at=frozen_now,
    )


@pytest.mark.parametrize(
    ("source", "side", "resume"),
    [
        (
            WorkflowState.DRAFT_READY,
            WorkflowState.AWAITING_BROWSER_LOGIN,
            WorkflowState.DRAFT_READY,
        ),
        (
            WorkflowState.TOPIC_SELECTED,
            WorkflowState.AWAITING_SECOND_MODEL_REVIEW,
            WorkflowState.TOPIC_SELECTED,
        ),
        (
            WorkflowState.IDEA,
            WorkflowState.NEEDS_MEDICAL_REVISION,
            WorkflowState.DRAFT_READY,
        ),
        (
            WorkflowState.EVIDENCE_READY,
            WorkflowState.NEEDS_PRODUCTION_REVISION,
            WorkflowState.PRODUCTION_IN_PROGRESS,
        ),
        (
            WorkflowState.PUBLISHED_MANUAL,
            WorkflowState.BLOCKED,
            WorkflowState.PUBLISHED_MANUAL,
        ),
        (WorkflowState.DRAFT_READY, WorkflowState.TOPIC_REJECTED, None),
    ],
)
def test_side_state_entry_rejects_sources_outside_the_table(
    source: WorkflowState, side: WorkflowState, resume: WorkflowState | None
) -> None:
    with pytest.raises(TransitionError, match="invalid v2 side entry"):
        transition_v2(
            manifest_at(source),
            side,
            valid_context(),
            reason_code="review_required",
            resume_state=resume,
            entered_at=FROZEN_NOW,
        )


@pytest.mark.parametrize(
    ("source", "side", "resume", "message"),
    [
        (
            WorkflowState.IDEA,
            WorkflowState.AWAITING_BROWSER_LOGIN,
            WorkflowState.RESEARCH_IN_PROGRESS,
            "resume state must match",
        ),
        (
            WorkflowState.EVIDENCE_READY,
            WorkflowState.AWAITING_SECOND_MODEL_REVIEW,
            WorkflowState.DRAFT_READY,
            "resume state must match",
        ),
        (
            WorkflowState.DRAFT_READY,
            WorkflowState.BLOCKED,
            WorkflowState.EVIDENCE_READY,
            "resume state must match",
        ),
        (
            WorkflowState.PACKAGED,
            WorkflowState.NEEDS_MEDICAL_REVISION,
            WorkflowState.PACKAGED,
            "not a valid exit",
        ),
        (
            WorkflowState.AWAITING_MEDICAL_REVIEW,
            WorkflowState.NEEDS_MEDICAL_REVISION,
            WorkflowState.AWAITING_MEDICAL_REVIEW,
            "not a valid exit",
        ),
        (
            WorkflowState.VIDEO_APPROVED,
            WorkflowState.NEEDS_PRODUCTION_REVISION,
            WorkflowState.VIDEO_APPROVED,
            "not a valid exit",
        ),
        (
            WorkflowState.RESEARCH_IN_PROGRESS,
            WorkflowState.TOPIC_REJECTED,
            WorkflowState.RESEARCH_IN_PROGRESS,
            "terminal side state",
        ),
    ],
)
def test_side_state_entry_rejects_a_resume_state_it_cannot_honour(
    source: WorkflowState,
    side: WorkflowState,
    resume: WorkflowState,
    message: str,
) -> None:
    with pytest.raises(TransitionError, match=message):
        transition_v2(
            manifest_at(source),
            side,
            valid_context(),
            reason_code="review_required",
            resume_state=resume,
            entered_at=FROZEN_NOW,
        )


@pytest.mark.parametrize(
    ("reason_code", "entered_at", "message"),
    [
        (None, FROZEN_NOW, "reason code"),
        ("", FROZEN_NOW, "reason code"),
        ("   ", FROZEN_NOW, "reason code"),
        ("review_required", None, "entered at"),
    ],
)
def test_side_state_entry_requires_a_reason_and_a_timestamp(
    reason_code: str | None, entered_at: datetime | None, message: str
) -> None:
    with pytest.raises(TransitionError, match=message):
        transition_v2(
            manifest_at(WorkflowState.IDEA),
            WorkflowState.AWAITING_BROWSER_LOGIN,
            valid_context(),
            reason_code=reason_code,
            resume_state=WorkflowState.IDEA,
            entered_at=entered_at,
        )


def test_side_state_entry_still_enforces_the_context_preconditions() -> None:
    with pytest.raises(TransitionError, match="active revision"):
        transition_v2(
            manifest_at(WorkflowState.IDEA),
            WorkflowState.BLOCKED,
            valid_context("002"),
            reason_code="lock_conflict",
            resume_state=WorkflowState.IDEA,
            entered_at=FROZEN_NOW,
        )
    with pytest.raises(TransitionError, match="reserved for recovery"):
        transition_v2(
            manifest_at(WorkflowState.IDEA),
            WorkflowState.BLOCKED,
            valid_context(run_published=False),
            reason_code="lock_conflict",
            resume_state=WorkflowState.IDEA,
            entered_at=FROZEN_NOW,
        )


@pytest.mark.parametrize(
    ("side", "resume", "reason_code", "target", "exit_reason_class"),
    [
        (
            WorkflowState.AWAITING_BROWSER_LOGIN,
            WorkflowState.IDEA,
            "login_expired",
            WorkflowState.IDEA,
            None,
        ),
        (
            WorkflowState.AWAITING_BROWSER_LOGIN,
            WorkflowState.RESEARCH_IN_PROGRESS,
            "login_expired",
            WorkflowState.RESEARCH_IN_PROGRESS,
            None,
        ),
        (
            WorkflowState.AWAITING_SECOND_MODEL_REVIEW,
            WorkflowState.EVIDENCE_READY,
            "review_required",
            WorkflowState.EVIDENCE_READY,
            None,
        ),
        (
            WorkflowState.NEEDS_MEDICAL_REVISION,
            WorkflowState.RESEARCH_IN_PROGRESS,
            "evidence_changed",
            WorkflowState.RESEARCH_IN_PROGRESS,
            None,
        ),
        (
            WorkflowState.NEEDS_MEDICAL_REVISION,
            WorkflowState.DRAFT_READY,
            "script_changed",
            WorkflowState.DRAFT_READY,
            None,
        ),
        (
            WorkflowState.NEEDS_PRODUCTION_REVISION,
            WorkflowState.PRODUCTION_IN_PROGRESS,
            "asset_qa_failed",
            WorkflowState.PRODUCTION_IN_PROGRESS,
            None,
        ),
        (
            WorkflowState.NEEDS_PRODUCTION_REVISION,
            WorkflowState.PRODUCTION_IN_PROGRESS,
            "asset_qa_failed",
            WorkflowState.DRAFT_READY,
            "semantic_issue",
        ),
        (
            WorkflowState.BLOCKED,
            WorkflowState.PACKAGED,
            "lock_conflict",
            WorkflowState.PACKAGED,
            None,
        ),
    ],
)
def test_side_state_exit_clears_the_record_on_a_documented_edge(
    side: WorkflowState,
    resume: WorkflowState,
    reason_code: str,
    target: WorkflowState,
    exit_reason_class: str | None,
) -> None:
    project = manifest_at(side, resume_state=resume, reason_code=reason_code)
    extra = {} if exit_reason_class is None else {"reason_code": exit_reason_class}

    changed = transition_v2(project, target, valid_context(**extra))

    assert changed.state is target
    assert changed.side_state is None


@pytest.mark.parametrize(
    ("exit_reason_class", "message"),
    [
        (None, "reason code is required"),
        ("", "reason code is required"),
        ("   ", "reason code is required"),
        ("asset_qa_failed", "requires reason class semantic_issue"),
        ("semantic", "requires reason class semantic_issue"),
    ],
)
def test_production_revision_exit_to_draft_ready_needs_an_exit_reason_class(
    exit_reason_class: str | None, message: str
) -> None:
    project = manifest_at(
        WorkflowState.NEEDS_PRODUCTION_REVISION,
        resume_state=WorkflowState.PRODUCTION_IN_PROGRESS,
        reason_code="asset_qa_failed",
    )
    extra = {} if exit_reason_class is None else {"reason_code": exit_reason_class}

    with pytest.raises(TransitionError, match=message):
        transition_v2(project, WorkflowState.DRAFT_READY, valid_context(**extra))


def test_production_revision_exit_to_draft_ready_ignores_the_entry_reason() -> None:
    project = manifest_at(
        WorkflowState.NEEDS_PRODUCTION_REVISION,
        resume_state=WorkflowState.PRODUCTION_IN_PROGRESS,
        reason_code="semantic_issue",
    )

    with pytest.raises(TransitionError, match="reason code is required"):
        transition_v2(project, WorkflowState.DRAFT_READY, valid_context())


def test_production_revision_exit_reads_the_reason_class_at_exit_time() -> None:
    project = manifest_at(
        WorkflowState.NEEDS_PRODUCTION_REVISION,
        resume_state=WorkflowState.PRODUCTION_IN_PROGRESS,
        reason_code="asset_qa_failed",
    )

    changed = transition_v2(
        project,
        WorkflowState.DRAFT_READY,
        valid_context(reason_code="semantic_issue"),
    )

    assert changed.state is WorkflowState.DRAFT_READY
    assert changed.side_state is None
    assert project.side_state is not None
    assert project.side_state.reason_code == "asset_qa_failed"


@pytest.mark.parametrize(
    ("side", "resume", "reason_code", "target", "message"),
    [
        (
            WorkflowState.NEEDS_MEDICAL_REVISION,
            WorkflowState.DRAFT_READY,
            "script_changed",
            WorkflowState.MEDICALLY_APPROVED,
            "invalid v2 side exit",
        ),
        (
            WorkflowState.NEEDS_MEDICAL_REVISION,
            WorkflowState.DRAFT_READY,
            "script_changed",
            WorkflowState.AWAITING_MEDICAL_REVIEW,
            "invalid v2 side exit",
        ),
        (
            WorkflowState.AWAITING_BROWSER_LOGIN,
            WorkflowState.IDEA,
            "login_expired",
            WorkflowState.RESEARCH_IN_PROGRESS,
            "recorded resume state",
        ),
        (
            WorkflowState.AWAITING_SECOND_MODEL_REVIEW,
            WorkflowState.EVIDENCE_READY,
            "review_required",
            WorkflowState.DRAFT_READY,
            "recorded resume state",
        ),
        (
            WorkflowState.BLOCKED,
            WorkflowState.DRAFT_READY,
            "lock_conflict",
            WorkflowState.EVIDENCE_READY,
            "recorded resume state",
        ),
        (
            WorkflowState.BLOCKED,
            WorkflowState.DRAFT_READY,
            "lock_conflict",
            WorkflowState.PUBLISHED_MANUAL,
            "invalid v2 side exit",
        ),
        (
            WorkflowState.TOPIC_REJECTED,
            None,
            "doctor_rejected_topic",
            WorkflowState.DRAFT_READY,
            "invalid v2 side exit",
        ),
    ],
)
def test_side_state_exit_rejects_edges_outside_the_table(
    side: WorkflowState,
    resume: WorkflowState | None,
    reason_code: str,
    target: WorkflowState,
    message: str,
) -> None:
    project = manifest_at(side, resume_state=resume, reason_code=reason_code)

    with pytest.raises(TransitionError, match=message):
        transition_v2(project, target, valid_context())


def test_side_state_exit_rejects_side_state_fields() -> None:
    project = manifest_at(
        WorkflowState.BLOCKED,
        resume_state=WorkflowState.DRAFT_READY,
        reason_code="lock_conflict",
    )

    with pytest.raises(TransitionError, match="reserved for side-state entry"):
        transition_v2(
            project,
            WorkflowState.DRAFT_READY,
            valid_context(),
            resume_state=WorkflowState.DRAFT_READY,
        )


@pytest.mark.parametrize(
    "extra",
    [
        {"reason_code": "review_required"},
        {"resume_state": WorkflowState.IDEA},
        {"entered_at": FROZEN_NOW},
    ],
)
def test_main_edge_rejects_side_state_fields(extra: dict[str, object]) -> None:
    with pytest.raises(TransitionError, match="reserved for side-state entry"):
        transition_v2(
            manifest_at(WorkflowState.IDEA),
            WorkflowState.TOPIC_SELECTED,
            valid_context(),
            **extra,
        )


def test_side_state_entry_rejects_a_reason_code_hidden_in_the_context() -> None:
    with pytest.raises(TransitionError, match="must be passed as reason_code"):
        transition_v2(
            manifest_at(WorkflowState.IDEA),
            WorkflowState.BLOCKED,
            valid_context(reason_code="lock_conflict"),
            reason_code="lock_conflict",
            resume_state=WorkflowState.IDEA,
            entered_at=FROZEN_NOW,
        )


def test_topic_rejected_reopens_only_as_new_revision() -> None:
    rejected = manifest_at(WorkflowState.TOPIC_REJECTED, active_revision="001")
    with pytest.raises(TransitionError, match="new revision"):
        transition_v2(rejected, WorkflowState.TOPIC_SELECTED, valid_context("001"))


def test_topic_rejected_reopens_after_the_revision_service_increments() -> None:
    rejected = manifest_at(WorkflowState.TOPIC_REJECTED, active_revision="002")

    changed = transition_v2(
        rejected,
        WorkflowState.TOPIC_SELECTED,
        valid_context("002", new_revision_from="001"),
    )

    assert changed.state is WorkflowState.TOPIC_SELECTED
    assert changed.side_state is None
    assert changed.active_revision == "002"


@pytest.mark.parametrize(
    ("active_revision", "new_revision_from", "message"),
    [
        ("001", "001", "increment of its parent"),
        ("003", "001", "increment of its parent"),
        ("002", "002", "increment of its parent"),
        ("002", "00a", "three-digit revision"),
    ],
)
def test_topic_rejected_reopen_requires_the_parent_revision(
    active_revision: str, new_revision_from: str, message: str
) -> None:
    rejected = manifest_at(
        WorkflowState.TOPIC_REJECTED, active_revision=active_revision
    )

    with pytest.raises(TransitionError, match=message):
        transition_v2(
            rejected,
            WorkflowState.TOPIC_SELECTED,
            valid_context(active_revision, new_revision_from=new_revision_from),
        )


def test_topic_rejected_reopen_requires_the_topic_card() -> None:
    rejected = manifest_at(WorkflowState.TOPIC_REJECTED, active_revision="002")
    context = TransitionContext(
        active_revision="002",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset(),
        new_revision_from="001",
    )

    with pytest.raises(TransitionError, match="missing required artifacts"):
        transition_v2(rejected, WorkflowState.TOPIC_SELECTED, context)
