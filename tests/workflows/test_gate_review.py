from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

import healthvideo.tts.pronunciation as pronunciation_module
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import (
    TransitionContext,
    TransitionError,
    transition_v2,
)
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.workflows.gate_review import (
    MEDICAL_APPROVAL_ARTIFACT,
    approve_gate,
    hash_reviewed_artifacts,
    medical_reviewed_paths,
    reject_gate,
    reopen_gate,
    resume_gate,
)
from tests.helpers import (
    advance_v2_project_to_video_review,
    align_fixture_script,
    create_v2_project_fixture,
    write_critic_review_fixture,
)

REVIEWER = "BS Nguyễn Văn An"
NOW = datetime(2026, 9, 11, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize('kind', [GateKind.MEDICAL, GateKind.VIDEO])
@pytest.mark.parametrize('problem', ['missing', 'failed', 'stale'])
def test_doctor_gate_refuses_missing_failed_or_stale_critic(tmp_path, kind, problem):
    from healthvideo.workflows import factory, product_review, script_review

    project = create_v2_project_fixture(tmp_path / 'projects')
    if kind is GateKind.VIDEO:
        advance_v2_project_to_video_review(project, now=NOW)
        critic, digest_key, station = product_review, 'render_sha256', 'Trạm 12'
    else:
        _advance_to_awaiting_medical_review(project)
        critic, digest_key, station = script_review, 'script_sha256', 'Trạm 07'
    log_path = project / 'revisions/001' / critic.LOG
    if problem == 'missing':
        log_path.unlink()
    else:
        log = read_yaml(log_path)
        if problem == 'failed':
            log['rounds'][-1]['passed'] = False
        else:
            log['rounds'][-1][digest_key] = 'stale'
        write_yaml_atomic(log_path, log)
    manifest = ProjectManifestV2.model_validate(read_yaml(project / 'project.yaml'))
    assert factory.gate_for_project(project, manifest) is None
    before = (project / 'project.yaml').read_bytes()
    with pytest.raises(ValueError, match=station):
        approve_gate(project, kind, reviewer=REVIEWER, now=NOW)
    assert (project / 'project.yaml').read_bytes() == before
    assert not (project / 'revisions/001/reviews' / f'{kind.value}-approval.yaml').exists()


def _advance_to_awaiting_medical_review(project_dir: Path) -> None:
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset(
            {
                "script/script.yaml",
                "storyboard/storyboard.yaml",
                "assets/asset-manifest.yaml",
            }
        ),
    )
    changed = transition_v2(manifest, WorkflowState.AWAITING_MEDICAL_REVIEW, context)
    write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))


def _enable_visual_budget(
    project_dir: Path,
    *,
    passing_default: bool = True,
    override: dict[str, object] | None = None,
) -> Path:
    storyboard_path = (
        project_dir / "revisions" / "001" / "storyboard" / "storyboard.yaml"
    )
    board = read_yaml(storyboard_path)
    board["visual_budget_profile"] = "m6_5_v1"
    highlight = deepcopy(board["scenes"][0])
    whiteboard_frames = 900 if passing_default else 800
    highlight_frames = 300 if passing_default else 400
    board["scenes"] = [
        {
            "id": "S01",
            "start_frame": 0,
            "duration_frames": whiteboard_frames,
            "narration": "Visual whiteboard synthetic.",
            "claim_id": "C01",
            "source_marker": "[1]",
            "visual": "whiteboard", "on_screen_text": "Synthetic illustration.",
        },
        {
            **highlight,
            "id": "S02",
            "start_frame": whiteboard_frames,
            "duration_frames": highlight_frames,
        },
    ]
    if override is not None:
        board["visual_budget_override"] = override
    align_fixture_script(project_dir / "revisions/001", board)
    write_yaml_atomic(storyboard_path, board)
    return storyboard_path


def _override(
    *,
    rationale: str = "Fixture cần tỷ lệ chart cao hơn mặc định.",
    whiteboard: tuple[int, int] = (60, 70),
    chart: tuple[int, int] = (30, 40),
) -> dict[str, object]:
    return {
        "rationale": rationale,
        "whiteboard_svg": {
            "min_percent": whiteboard[0],
            "max_percent": whiteboard[1],
        },
        "chart_crop": {
            "min_percent": chart[0],
            "max_percent": chart[1],
        },
    }


def test_medical_reviewed_paths_includes_ledger_script_storyboard_manifest_and_semantic_assets(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision_root = project_dir / "revisions" / "001"
    paths = medical_reviewed_paths(revision_root)
    assert set(paths) == {
        "evidence/ledger.yaml",
        "script/script.yaml",
        "storyboard/storyboard.yaml",
        "assets/asset-manifest.yaml",
        "assets/license-ledger.yaml",
        "profiles/pronunciation.vi.yaml",
        "asset:assets/evidence-r01.svg",
        "asset:assets/evidence-r01-crop.png",
        "asset:assets/test-logo.svg",
    }


def test_approve_medical_rejects_missing_semantic_asset_bytes(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    (project_dir / "revisions" / "001" / "assets" / "evidence-r01.svg").write_bytes(b"changed")

    with pytest.raises(Exception, match="sha256"):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)


def test_approve_medical_rejects_invalid_pronunciation_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    profile = tmp_path / "pronunciation.vi.yaml"
    profile.write_text(
        "schema_version: '1.0'\nlanguage: en\nversion: '1'\nentries: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pronunciation_module, "PRONUNCIATION_PROFILE_PATH", profile)
    with pytest.raises(ValueError):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_medical_review"


def test_approve_medical_writes_record_once_and_advances_state(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)

    record = approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    approval_path = project_dir / "revisions" / "001" / MEDICAL_APPROVAL_ARTIFACT
    assert approval_path.is_file()
    assert read_yaml(approval_path)["reviewer"] == REVIEWER
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.MEDICALLY_APPROVED
    assert record.artifact_hashes
    assert "profiles/pronunciation.vi.yaml" in record.artifact_hashes

    with pytest.raises(FileExistsError):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)


def test_m6_5_default_budget_allows_normal_manual_medical_approval(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    _enable_visual_budget(project_dir)

    approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    revision = project_dir / "revisions/001"
    assert (revision / MEDICAL_APPROVAL_ARTIFACT).is_file()
    assert read_yaml(project_dir / "project.yaml")["state"] == "medically_approved"
    assert not (revision / "reviews/visual-budget-approval.yaml").exists()


def test_m6_5_invalid_default_budget_refuses_before_approval_or_state_change(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    _enable_visual_budget(project_dir, passing_default=False)

    with pytest.raises(ValueError, match="visual budget failed"):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    revision = project_dir / "revisions/001"
    assert not (revision / MEDICAL_APPROVAL_ARTIFACT).exists()
    assert read_yaml(project_dir / "project.yaml")["state"] == (
        "awaiting_medical_review"
    )


def test_m6_5_reviewed_override_changes_bounds_but_still_enforces_them(
    tmp_path: Path,
) -> None:
    passing = create_v2_project_fixture(
        tmp_path / "passing", state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    _enable_visual_budget(passing, passing_default=False, override=_override())
    approve_gate(passing, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    failing = create_v2_project_fixture(
        tmp_path / "failing", state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    _enable_visual_budget(
        failing,
        passing_default=False,
        override=_override(whiteboard=(70, 80), chart=(20, 30)),
    )
    with pytest.raises(ValueError, match="visual budget failed"):
        approve_gate(failing, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)


@pytest.mark.parametrize("mutation", ["timing", "profile", "bounds", "rationale"])
def test_m6_5_storyboard_policy_changes_make_medical_hash_stale(
    tmp_path: Path, mutation: str
) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    storyboard_path = _enable_visual_budget(
        project_dir, passing_default=False, override=_override()
    )
    record = approve_gate(
        project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW
    )
    board = read_yaml(storyboard_path)
    if mutation == "timing":
        board["scenes"][0]["duration_frames"] += 1
    elif mutation == "profile":
        board["visual_budget_profile"] = "explain_first_v1"
        del board["visual_budget_override"]
    elif mutation == "bounds":
        board["visual_budget_override"]["chart_crop"]["max_percent"] += 1
    else:
        board["visual_budget_override"]["rationale"] += " Đã sửa."
    write_yaml_atomic(storyboard_path, board)

    revision = project_dir / "revisions/001"
    current = hash_reviewed_artifacts(medical_reviewed_paths(revision))
    assert current != record.artifact_hashes


def test_reject_medical_enters_side_state_and_can_repeat_before_approval(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)

    first = reject_gate(
        project_dir,
        GateKind.MEDICAL,
        reviewer=REVIEWER,
        reason="Thiếu nguồn cho claim C01.",
        resume_state=WorkflowState.DRAFT_READY,
        now=NOW,
    )
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.NEEDS_MEDICAL_REVISION
    assert manifest.side_state.resume_state is WorkflowState.DRAFT_READY
    assert first.reason == "Thiếu nguồn cho claim C01."

    resume_gate(project_dir, GateKind.MEDICAL, target=WorkflowState.DRAFT_READY, now=NOW)
    _advance_to_awaiting_medical_review(project_dir)

    second = reject_gate(
        project_dir,
        GateKind.MEDICAL,
        reviewer=REVIEWER,
        reason="Vẫn còn một câu chưa khớp claim.",
        resume_state=WorkflowState.DRAFT_READY,
        now=NOW,
    )
    assert first != second


def test_reject_gate_requires_non_blank_reason(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    with pytest.raises(Exception, match="reason"):
        reject_gate(
            project_dir,
            GateKind.MEDICAL,
            reviewer=REVIEWER,
            reason="   ",
            resume_state=WorkflowState.DRAFT_READY,
            now=NOW,
        )


def test_reject_gate_invalid_resume_state_leaves_no_record(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    manifest_path = project_dir / "project.yaml"
    original = manifest_path.read_bytes()
    active_revision = read_yaml(manifest_path)["active_revision"]

    with pytest.raises(TransitionError, match="not a valid exit"):
        reject_gate(
            project_dir,
            GateKind.MEDICAL,
            reviewer=REVIEWER,
            reason="Cần sửa bằng chứng.",
            resume_state=WorkflowState.EVIDENCE_READY,
            now=NOW,
        )

    reviews = project_dir / "revisions" / active_revision / "reviews" / "medical"
    assert not list(reviews.glob("*-rejected*.yaml"))
    assert manifest_path.read_bytes() == original
    assert read_yaml(manifest_path)["state"] == "awaiting_medical_review"


def test_approve_video_hashes_render_manifest_and_mp4(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=NOW)

    record = approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=NOW)

    assert set(record.artifact_hashes) == {
        "renders/render-manifest.json",
        "renders/video.mp4",
        "posts/posts.yaml",
        "reviews/video-qa.json",
    }
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.VIDEO_APPROVED


def test_term_mismatch_blocks_video_gate(tmp_path):
    import json

    project = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project, now=NOW)
    revision = project / 'revisions/001'
    (revision / 'reviews/pronunciation-qa.json').write_text(json.dumps({
        'flags': [{'severity': 'block', 'script_word': 'gút'}],
    }), encoding='utf-8')
    with pytest.raises(ValueError, match='pronunciation'):
        approve_gate(project, GateKind.VIDEO, reviewer=REVIEWER, now=NOW)
    assert not (revision / 'reviews/video-approval.yaml').exists()


def test_doctor_accept_pronunciation_override_needs_pin(tmp_path):
    import json

    from healthvideo.approver_pin import set_pin
    from healthvideo.storage.files import canonical_json_hash

    project = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project, now=NOW)
    revision = project / 'revisions/001'
    report = {'flags': [{'severity': 'block', 'script_word': 'gút'}]}
    (revision / 'reviews/pronunciation-qa.json').write_text(json.dumps(report), encoding='utf-8')
    pin_file = tmp_path / 'pin.json'
    set_pin('123456', path=pin_file)
    for pin in (None, 'wrong'):
        with pytest.raises(ValueError, match='PIN'):
            approve_gate(project, GateKind.VIDEO, reviewer=REVIEWER, now=NOW,
                         accept_pronunciation=True, pronunciation_pin=pin, pin_file=pin_file)
    record = approve_gate(project, GateKind.VIDEO, reviewer=REVIEWER, now=NOW,
                          accept_pronunciation=True, pronunciation_pin='123456', pin_file=pin_file)
    assert record.pronunciation_acceptance == canonical_json_hash(report)
    assert 'reviews/pronunciation-qa.json' in record.artifact_hashes


def test_pronunciation_acceptance_cannot_override_other_video_qa_failure(tmp_path):
    import json

    project = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project, now=NOW)
    revision = project / 'revisions/001'
    (revision / 'reviews/video-qa.json').write_text(json.dumps({
        'status': 'failed', 'checks': {'output_exists': False},
        'pronunciation': {'passed': False},
    }), encoding='utf-8')
    with pytest.raises(ValueError, match='QA'):
        approve_gate(project, GateKind.VIDEO, reviewer=REVIEWER, now=NOW,
                     accept_pronunciation=True)


def test_pronunciation_acceptance_refuses_changed_render_report(tmp_path):
    import json

    project = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project, now=NOW)
    revision = project / 'revisions/001'
    (revision / 'reviews/pronunciation-qa.json').write_text(json.dumps({'flags': []}), encoding='utf-8')
    (revision / 'reviews/video-qa.json').write_text(json.dumps({
        'status': 'failed', 'checks': {'output_exists': True},
        'pronunciation': {'passed': False, 'report_sha256': '0' * 64},
    }), encoding='utf-8')
    with pytest.raises(ValueError, match='hash'):
        approve_gate(project, GateKind.VIDEO, reviewer=REVIEWER, now=NOW,
                     accept_pronunciation=True)


@pytest.mark.parametrize('broken', ['pronunciation_missing', 'both_missing', 'qa_missing', 'stale_report', 'stale_input'])
def test_modern_render_requires_bound_pronunciation_reports(tmp_path, broken):
    import json

    from healthvideo.storage.files import sha256_file

    project = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project, now=NOW)
    revision = project / 'revisions/001'
    pronunciation = revision / 'reviews/pronunciation-qa.json'
    video_qa = revision / 'reviews/video-qa.json'
    pronunciation.write_text(json.dumps({'flags': [], 'input_hash': 'current'}), encoding='utf-8')
    manifest = revision / 'renders/render-manifest.json'
    manifest.write_text(json.dumps({
        'input_hash': 'current',
        'alignment_sha256': {'pronunciation-qa.json': sha256_file(pronunciation)},
    }), encoding='utf-8')
    video_qa.write_text(json.dumps({'status': 'render_complete', 'input_hash': 'current'}), encoding='utf-8')
    if broken in {'pronunciation_missing', 'both_missing'}:
        pronunciation.unlink()
    if broken in {'qa_missing', 'both_missing'}:
        video_qa.unlink()
    if broken == 'stale_report':
        pronunciation.write_text(json.dumps({'flags': [], 'input_hash': 'other'}), encoding='utf-8')
    if broken == 'stale_input':
        video_qa.write_text(json.dumps({'status': 'render_complete', 'input_hash': 'other'}), encoding='utf-8')
    with pytest.raises(ValueError, match='QA'):
        approve_gate(project, GateKind.VIDEO, reviewer=REVIEWER, now=NOW)


def test_reject_video_with_semantic_issue_must_resume_to_draft_ready_with_that_reason_class(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=NOW)

    reject_gate(
        project_dir,
        GateKind.VIDEO,
        reviewer=REVIEWER,
        reason="Phát hiện câu thoại sai claim khi xem lại video.",
        resume_state=WorkflowState.DRAFT_READY,
        now=NOW,
    )

    with pytest.raises(Exception, match=r"reason (class|code)"):
        resume_gate(project_dir, GateKind.VIDEO, target=WorkflowState.DRAFT_READY, now=NOW)

    resume_gate(
        project_dir,
        GateKind.VIDEO,
        target=WorkflowState.DRAFT_READY,
        reason_code="semantic_issue",
        now=NOW,
    )
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.DRAFT_READY


def test_reject_video_without_semantic_issue_resumes_to_production_in_progress(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=NOW)

    reject_gate(
        project_dir,
        GateKind.VIDEO,
        reviewer=REVIEWER,
        reason="Âm lượng chưa chuẩn hoá.",
        resume_state=WorkflowState.PRODUCTION_IN_PROGRESS,
        now=NOW,
    )
    resume_gate(project_dir, GateKind.VIDEO, target=WorkflowState.PRODUCTION_IN_PROGRESS, now=NOW)

    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.PRODUCTION_IN_PROGRESS


def test_resume_to_production_refuses_after_medical_reviewed_storyboard_edit(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=NOW)
    reject_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, reason="Bố cục.",
                resume_state=WorkflowState.PRODUCTION_IN_PROGRESS, now=NOW)
    board_path = project_dir / "revisions/001/storyboard/storyboard.yaml"
    board = read_yaml(board_path)
    board["scenes"][0]["narration"] += " Sửa sau duyệt."
    write_yaml_atomic(board_path, board)

    with pytest.raises(ValueError, match="Mở lại cổng y khoa"):
        resume_gate(project_dir, GateKind.VIDEO,
                    target=WorkflowState.PRODUCTION_IN_PROGRESS, now=NOW)
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.NEEDS_PRODUCTION_REVISION


def _approved_project(tmp_path: Path, *, video: bool = False) -> Path:
    project = create_v2_project_fixture(
        tmp_path, state=WorkflowState.DRAFT_READY if video else WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    if video:
        advance_v2_project_to_video_review(project, now=NOW)
        approve_gate(project, GateKind.VIDEO, reviewer=REVIEWER, now=NOW)
    else:
        approve_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    return project


@pytest.mark.parametrize("video", [False, True])
def test_reopen_preserves_approval_bytes_and_prior_hashes(tmp_path: Path, video: bool) -> None:
    project = _approved_project(tmp_path, video=video)
    revision = project / "revisions/001"
    old = {kind.value: (revision / f"reviews/{kind.value}-approval.yaml").read_bytes()
           for kind in GateKind if kind is GateKind.MEDICAL or video}
    prior = read_yaml(revision / MEDICAL_APPROVAL_ARTIFACT)["artifact_hashes"]
    record = reopen_gate(
        project, GateKind.MEDICAL, reviewer=REVIEWER, reason="Revise storyboard",
        changed=["storyboard/storyboard.yaml"], resume_state=WorkflowState.DRAFT_READY, now=NOW,
    )
    manifest = ProjectManifestV2.model_validate(read_yaml(project / "project.yaml"))
    assert manifest.state is WorkflowState.NEEDS_MEDICAL_REVISION
    assert manifest.side_state.resume_state is WorkflowState.DRAFT_READY
    assert manifest.side_state.reason_code.startswith("medical_reopen:")
    assert record.prior_approval_hashes == prior
    assert record.invalidation_reasons == sorted(record.invalidation_reasons)
    for kind, content in old.items():
        assert not (revision / f"reviews/{kind}-approval.yaml").exists()
        assert (revision / record.superseded_approvals[kind]).read_bytes() == content
    assert len(list((revision / "reviews/medical").glob("*-reopened.yaml"))) == 1


@pytest.mark.parametrize(
    ("kind", "changed", "resume", "match"),
    [
        (GateKind.MEDICAL, ["renders/video.mp4"], WorkflowState.DRAFT_READY, "medical re-review: video"),
        (GateKind.MEDICAL, ["storyboard/storyboard.yaml"], WorkflowState.EVIDENCE_READY, "not a valid exit"),
        (GateKind.VIDEO, ["storyboard/storyboard.yaml"], WorkflowState.DRAFT_READY, "only the medical"),
        *[(GateKind.MEDICAL, [path], WorkflowState.DRAFT_READY, "POSIX path")
          for path in ["../script.yaml", "/script.yaml", "C:/script.yaml", "a\\b", "", "."]],
        (GateKind.MEDICAL, [], WorkflowState.DRAFT_READY, "nonempty"),
    ],
)
def test_reopen_refusal_writes_nothing(tmp_path: Path, kind, changed, resume, match: str) -> None:
    project = _approved_project(tmp_path)
    before = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match=match):
        reopen_gate(project, kind, reviewer=REVIEWER, reason="Revise", changed=changed,
                    resume_state=resume, now=NOW)
    assert {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()} == before


def test_reopen_refuses_pre_gate_state(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    with pytest.raises(ValueError, match="awaiting_medical_review"):
        reopen_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, reason="Revise",
                    changed=["script/script.yaml"], resume_state=WorkflowState.DRAFT_READY, now=NOW)


def test_reopen_resume_resubmit_and_approve(tmp_path: Path) -> None:
    from healthvideo.workflows.draft import submit_draft, submit_medical_review

    project = _approved_project(tmp_path)
    revision = project / "revisions/001"
    record = reopen_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, reason="Revise",
                         changed=["storyboard/storyboard.yaml"],
                         resume_state=WorkflowState.DRAFT_READY, now=NOW)
    resume_gate(project, GateKind.MEDICAL, target=WorkflowState.DRAFT_READY, now=NOW)
    board = read_yaml(revision / "storyboard/storyboard.yaml")
    board["scenes"][1]["anatomy"]["motion"] += " Revised draft."
    board_file = tmp_path / "new-board.yaml"
    write_yaml_atomic(board_file, board)
    submit_draft(project, revision / "script/script.yaml", board_file,
                 revision / "assets/asset-manifest.yaml")
    write_critic_review_fixture(project)
    submit_medical_review(project)
    approval = approve_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    assert approval.artifact_hashes != record.prior_approval_hashes
    assert (revision / MEDICAL_APPROVAL_ARTIFACT).is_file()
    assert (revision / record.superseded_approvals["medical"]).is_file()


def test_reopen_collision_keeps_existing_history(tmp_path: Path) -> None:
    project = _approved_project(tmp_path)
    revision = project / "revisions/001"
    directory = revision / "reviews/medical"
    directory.mkdir()
    timestamp = NOW.astimezone().strftime("%Y%m%dT%H%M%S%f")
    for suffix in ("superseded-approval", "reopened"):
        (directory / f"{timestamp}-{suffix}.yaml").write_bytes(b"existing audit history")
    original = (revision / MEDICAL_APPROVAL_ARTIFACT).read_bytes()
    record = reopen_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, reason="Revise",
                         changed=["storyboard/storyboard.yaml"],
                         resume_state=WorkflowState.DRAFT_READY, now=NOW)
    assert record.superseded_approvals["medical"].endswith("-superseded-approval-1.yaml")
    assert (revision / record.superseded_approvals["medical"]).read_bytes() == original
    assert (directory / f"{timestamp}-reopened-1.yaml").is_file()
    for suffix in ("superseded-approval", "reopened"):
        assert (directory / f"{timestamp}-{suffix}.yaml").read_bytes() == b"existing audit history"


def test_reopen_missing_current_approval_writes_nothing(tmp_path: Path) -> None:
    project = _approved_project(tmp_path)
    revision = project / "revisions/001"
    (revision / MEDICAL_APPROVAL_ARTIFACT).unlink()
    original = (project / "project.yaml").read_bytes()
    with pytest.raises(FileNotFoundError):
        reopen_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, reason="Revise",
                    changed=["storyboard/storyboard.yaml"],
                    resume_state=WorkflowState.DRAFT_READY, now=NOW)
    assert (project / "project.yaml").read_bytes() == original
    assert not (revision / "reviews/medical").exists()


def test_telegram_bot_gates_match_station_07_and_12_without_revoking_approvals(
    tmp_path: Path, monkeypatch
) -> None:
    from healthvideo.workflows import product_review, script_review, telegram_bot

    root = tmp_path
    med = create_v2_project_fixture(root / "projects", state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    prior_approval = med / "revisions/001" / MEDICAL_APPROVAL_ARTIFACT
    prior_bytes = b"kind: medical\nreviewer: BS Cu\n"
    prior_approval.write_bytes(prior_bytes)

    # Break Station 07 (missing script-review-log.yaml)
    (med / "revisions/001" / script_review.LOG).unlink()

    # Also test video gate with stale Station 12
    vid_root = tmp_path / "vid_root"
    vid = create_v2_project_fixture(vid_root / "projects", state=WorkflowState.DRAFT_READY)
    advance_v2_project_to_video_review(vid, now=NOW)
    vid_log = vid / "revisions/001" / product_review.LOG
    log_data = read_yaml(vid_log)
    log_data["rounds"][-1]["render_sha256"] = "stale"
    write_yaml_atomic(vid_log, log_data)

    monkeypatch.setattr(telegram_bot.channel_analytics, "channel_overview_payload", lambda _r: {})
    monkeypatch.setattr(telegram_bot.researcher, "inbox_summary", lambda _r: {"total": 0, "tier_a": 0, "tier_b": 0})

    sent: list[str] = []

    def capture_send(text: str, *, reply_markup=None, chat_id=None, **_kwargs):
        sent.append(text)
        return {"ok": True}

    state = telegram_bot.load_state(root)
    telegram_bot._send_gate_review(root, state, None, "1", send_fn=capture_send)
    assert "không có project nào đang chờ" in sent[-1]
    telegram_bot._send_gate_review(root, state, med.name, "1", send_fn=capture_send)
    assert "Trạm 07/12" in sent[-1]
    telegram_bot._send_status(root, state, "1", capture_send)
    assert "Chờ bác sĩ duyệt cổng: 0" in sent[-1]
    telegram_bot._send_projects(root, state, "1", capture_send)
    assert "CHỜ DUYỆT CỔNG" not in sent[-1]
    assert prior_approval.read_bytes() == prior_bytes

    state_vid = telegram_bot.load_state(vid_root)
    telegram_bot._send_gate_review(vid_root, state_vid, vid.name, "1", send_fn=capture_send)
    assert "Trạm 07/12" in sent[-1]


@pytest.mark.parametrize('status', [None, 'skipped', 'unknown', [], {}])
def test_video_qa_refuses_missing_or_unknown_status(tmp_path, status):
    import json

    from healthvideo.workflows.gate_review import _check_video_qa

    revision = tmp_path
    (revision / 'reviews').mkdir()
    data = {} if status is None else {'status': status}
    (revision / 'reviews/video-qa.json').write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='QA'):
        _check_video_qa(revision, accept_pronunciation=False, pronunciation_pin=None, pin_file=None)


@pytest.mark.parametrize('status', ['render_complete', 'passed'])
def test_video_qa_accepts_known_success_status(tmp_path, status):
    import json

    from healthvideo.workflows.gate_review import _check_video_qa

    (tmp_path / 'reviews').mkdir()
    (tmp_path / 'reviews/video-qa.json').write_text(json.dumps({'status': status}), encoding='utf-8')
    assert _check_video_qa(tmp_path, accept_pronunciation=False,
                           pronunciation_pin=None, pin_file=None) is None
def test_r5_snapshot_binds_source_bytes_and_license(tmp_path):
    from healthvideo.domain.storyboard import Storyboard
    from healthvideo.workflows.gate_review import (
        load_r5_revision_assets,
        snapshot_r5_assets,
    )
    from tests.render.test_quality import board, shot

    revision = tmp_path / "revisions/001"
    (revision / "assets").mkdir(parents=True)
    (revision / "storyboard").mkdir()
    (revision / "evidence").mkdir()
    asset = revision / "assets/cell.svg"
    asset.write_bytes(b"<svg/>")
    record = {"id": "cell", "file": "assets/cell.svg", "source_page": "https://smart.servier.com/smart_image/cell/",
              "original_url": "https://smart.servier.com/cell.svg", "author": "Fixture author",
              "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
              "sha256": sha256_file(asset)}
    write_yaml_atomic(revision / "assets/r5/catalog.yaml", {"assets": [record]})
    write_yaml_atomic(revision / "assets/asset-manifest.yaml", {"schema_version": "2.0", "assets": [{
        "path": "assets/cell.svg", "kind": "medical_diagram", "semantic": True,
        "creator": record["author"], "revision": "001",
        "source": record["source_page"], "license": record["license"], "sha256": record["sha256"],
    }]})
    original = board([{**shot(0, 90), "kind": "mechanism", "asset_paths": ["assets/cell.svg"]}], frames=90)
    write_yaml_atomic(revision / "storyboard/storyboard.yaml", original.model_dump(mode="json"))
    source = revision / "evidence/source.txt"
    source.write_bytes(b"fixture source")
    snapshot_r5_assets(revision, original)
    paths = medical_reviewed_paths(revision)
    before = hash_reviewed_artifacts(paths)
    assert load_r5_revision_assets(revision, original)[0].author == "Fixture author"
    source.write_bytes(b"changed source")
    assert before != hash_reviewed_artifacts(medical_reviewed_paths(revision))
    source.unlink()
    assert before != hash_reviewed_artifacts(medical_reviewed_paths(revision))
    (revision / "assets/r5/license-ledger.yaml").unlink()
    assert before != hash_reviewed_artifacts(medical_reviewed_paths(revision))
    with pytest.raises((ValueError, FileNotFoundError)):
        load_r5_revision_assets(revision, original)
    # Removing the opt-in cannot reuse an approval that included R5 artifacts.
    write_yaml_atomic(revision / "storyboard/storyboard.yaml", Storyboard(title="Legacy").model_dump(mode="json"))
    assert before != hash_reviewed_artifacts(medical_reviewed_paths(revision))


def test_r5_video_gate_rejects_stale_cache_and_enforces_pin(tmp_path, monkeypatch):
    import json

    from healthvideo.approver_pin import set_pin
    from healthvideo.tts.silent import SilentTTS
    from healthvideo.workflows.produce import produce_project
    from tests.helpers import submit_video_fixture
    from tests.workflows.test_produce import (
        V2_REVIEWED_AT,
        _r5_alignment,
        _r5_project,
        _write_synthetic_output,
    )

    project = _r5_project(tmp_path)
    revision = project / "revisions/001"
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=V2_REVIEWED_AT)
    _r5_alignment(monkeypatch)
    produce_project(project, SilentTTS(), lambda argv: (_write_synthetic_output(argv), 0)[1], music=False)
    submit_video_fixture(project)
    # Tampering quality-report or stale medical source must never pass the video gate.
    (revision / "reviews/quality-report.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="stale|quality"):
        approve_gate(project, GateKind.VIDEO, reviewer="doctor", now=V2_REVIEWED_AT)
    (revision / "reviews/quality-report.json").write_bytes((revision / "renders/quality-report.json").read_bytes())
    # Pronunciation override still enforces doctor PIN (no bypass for R5).
    pin_file = tmp_path / "pin.json"
    set_pin("123456", path=pin_file)
    qa = json.loads((revision / "reviews/video-qa.json").read_text(encoding="utf-8"))
    qa["status"] = "failed"
    qa["pronunciation"] = {
        "passed": False,
        "blocking_count": 1,
        "report_sha256": sha256_file(revision / "renders/pronunciation-qa.json"),
    }
    (revision / "reviews/video-qa.json").write_text(json.dumps(qa), encoding="utf-8")
    with pytest.raises(ValueError, match="PIN"):
        approve_gate(
            project, GateKind.VIDEO, reviewer="doctor", now=V2_REVIEWED_AT,
            accept_pronunciation=True, pronunciation_pin=None, pin_file=pin_file,
        )


def test_r5_medical_gate_is_read_only_and_rejects_missing_snapshot(tmp_path):
    from healthvideo.domain.storyboard import Storyboard
    from healthvideo.workflows.gate_review import (
        R5_CATALOG,
        R5_LICENSE_LEDGER,
        R5_USED_ASSETS,
        snapshot_r5_assets,
    )
    from tests.workflows.test_produce import V2_REVIEWED_AT, _r5_project

    project = _r5_project(tmp_path)
    revision = project / "revisions/001"
    library_dir = tmp_path / "library"
    (library_dir / "assets").mkdir(parents=True)
    lib_asset = library_dir / "assets/cell.svg"
    lib_asset.write_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'/>")
    digest = sha256_file(lib_asset)
    record = {
        "id": "cell",
        "file": "assets/cell.svg",
        "source_page": "https://smart.servier.com/smart_image/cell/",
        "original_url": "https://smart.servier.com/cell.svg",
        "author": "Fixture author",
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "sha256": digest,
    }
    write_yaml_atomic(revision / R5_CATALOG, {"assets": [record]})
    manifest_data = read_yaml(revision / "assets/asset-manifest.yaml")
    manifest_data["assets"].append({
        "path": "assets/cell.svg",
        "kind": "medical_diagram",
        "semantic": True,
        "creator": record["author"],
        "revision": "001",
        "source": record["source_page"],
        "license": record["license"],
        "sha256": digest,
    })
    write_yaml_atomic(revision / "assets/asset-manifest.yaml", manifest_data)
    board_data = read_yaml(revision / "storyboard/storyboard.yaml")
    board_data["scenes"][0]["shots"][0]["asset_paths"] = ["assets/cell.svg"]
    write_yaml_atomic(revision / "storyboard/storyboard.yaml", board_data)
    board = Storyboard.model_validate(board_data)

    def _tree(root: Path) -> dict[str, bytes]:
        return {
            p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*"))
            if p.is_file()
        }

    # Without snapshot, medical gate must refuse and write ZERO files.
    before_missing = _tree(revision)
    with pytest.raises((FileNotFoundError, ValueError)):
        approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=V2_REVIEWED_AT)
    assert _tree(revision) == before_missing
    assert not (revision / R5_USED_ASSETS).exists()
    assert not (revision / R5_LICENSE_LEDGER).exists()

    # Snapshotting from library source copies and verifies asset into revision.
    snapshot_r5_assets(revision, board, source_root=library_dir)
    assert (revision / "assets/cell.svg").read_bytes() == lib_asset.read_bytes()
    assert (revision / R5_USED_ASSETS).is_file()
    assert (revision / R5_LICENSE_LEDGER).is_file()

    # Once snapshot exists, approve_gate(MEDICAL) must not write or alter any
    # revision files other than the approval record (and standards pin).
    before_approve = _tree(revision)
    approve_gate(project, GateKind.MEDICAL, reviewer="doctor", now=V2_REVIEWED_AT)
    after_approve = _tree(revision)
    created_or_changed = {
        k for k, v in after_approve.items() if before_approve.get(k) != v
    }
    assert created_or_changed <= {
        MEDICAL_APPROVAL_ARTIFACT,
        "workflow/standards.yaml",
        "reviews/.results.preproduction.lock",
    }
    if "reviews/.results.preproduction.lock" in created_or_changed:
        assert after_approve["reviews/.results.preproduction.lock"] == b""
    assert set(before_approve) <= set(after_approve)

    # Snapshot must refuse to overwrite after medical approval exists.
    with pytest.raises(ValueError, match="reopening"):
        snapshot_r5_assets(revision, board, source_root=library_dir)
