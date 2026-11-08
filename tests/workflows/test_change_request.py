from datetime import UTC, datetime

import pytest

from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.workflows.change_request import (
    mark_applied,
    pending_note,
    request_change,
)
from healthvideo.workflows.factory_deps import reject_note
from healthvideo.workflows.script_review import (
    LOG,
    mark_submitted,
    next_script_action,
    script_hash,
)
from tests.helpers import create_v2_project_fixture as _fixture


def create_v2_project_fixture(root, *, state=WorkflowState.DRAFT_READY):
    project = _fixture(root)
    data = read_yaml(project / "project.yaml")
    write_yaml_atomic(project / "project.yaml", {**data, "state": state.value})
    return project

NOW = datetime(2026, 11, 8, 15, tzinfo=UTC)
CONTEXT = {'scene': 'S07', 'time_s': 192, 'revision': '001'}


def test_production_change_enters_needs_production_revision(tmp_path):
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.PRODUCTION_IN_PROGRESS)
    record = request_change(project, 'edit_production', 'Đổi hình kim', CONTEXT, now=NOW)
    layout = resolve_project_layout(project)
    assert layout.manifest.state == WorkflowState.NEEDS_PRODUCTION_REVISION
    assert layout.manifest.side_state.resume_state == WorkflowState.PRODUCTION_IN_PROGRESS
    assert record['by'] == 'doctor-chat' and record['applied'] is False
    assert 'S07 @ 03:12' in pending_note(project)
    assert len(list((layout.artifact_root / 'reviews/changes').glob('*-requested.yaml'))) == 1
    mark_applied(project)
    assert pending_note(project) is None


def test_script_change_after_medical_approval_reopens_without_pin(tmp_path):
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.MEDICALLY_APPROVED)
    rev = project / 'revisions/001'
    approval = rev / 'reviews/medical-approval.yaml'
    write_yaml_atomic(approval, {'history': 'unchanged'})
    request_change(project, 'edit_script', 'Đổi câu N01', CONTEXT, now=NOW)
    manifest = resolve_project_layout(project).manifest
    assert manifest.state == WorkflowState.NEEDS_MEDICAL_REVISION
    assert manifest.side_state.reason_code == 'chat_change'
    assert manifest.side_state.resume_state == WorkflowState.DRAFT_READY
    assert not approval.exists()
    assert read_yaml(next((rev / 'reviews/medical').glob('*-superseded-approval*.yaml'))) == {'history': 'unchanged'}


def test_script_change_at_draft_ready_restarts_review(tmp_path):
    project = create_v2_project_fixture(tmp_path)
    rev = project / 'revisions/001'
    write_yaml_atomic(rev / LOG, {'rounds': [{'script_sha256': script_hash(project), 'passed': True}]})
    assert next_script_action(project) == 'submit_medical'
    request_change(project, 'edit_script', 'Viết lại N01', CONTEXT, now=NOW)
    assert resolve_project_layout(project).manifest.state == WorkflowState.DRAFT_READY
    assert next_script_action(project) == 'script_review'
    mark_submitted(rev)


def test_invalid_state_raises(tmp_path):
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.IDEA)
    before = (project / 'project.yaml').read_bytes()
    with pytest.raises(ValueError, match='trạng thái'):
        request_change(project, 'edit_script', 'Sửa câu', {}, now=NOW)
    assert (project / 'project.yaml').read_bytes() == before
    assert not list(project.rglob('*-requested.yaml'))


def test_reject_note_includes_pending_brief(tmp_path):
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.EVIDENCE_READY)
    request_change(project, 'edit_script', 'Giải thích rõ hơn', CONTEXT, now=NOW)
    assert 'Giải thích rõ hơn' in reject_note(project)
    assert 'S07 @ 03:12' in reject_note(project)


def test_production_request_restarts_critic_cycle(tmp_path):
    from healthvideo.workflows import product_review

    project = create_v2_project_fixture(tmp_path, state=WorkflowState.PRODUCTION_IN_PROGRESS)
    rev = project / 'revisions/001'
    rounds = [{'passed': True}] * product_review.MAX_REVIEWS
    write_yaml_atomic(rev / product_review.LOG, {'rounds': rounds, 'submitted': 0})
    assert product_review.next_product_action(project) == 'submit_video'
    request_change(project, 'edit_production', 'Đổi hình S07', CONTEXT, now=NOW)
    assert read_yaml(rev / product_review.LOG)['submitted'] == len(rounds)
