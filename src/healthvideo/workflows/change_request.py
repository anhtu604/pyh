"""Confirmed doctor chat requests, applied only between factory steps."""

import os
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.files import canonical_json_hash, read_yaml, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.workflows import product_review
from healthvideo.workflows.script_review import mark_submitted

EARLY = frozenset({WorkflowState.TOPIC_SELECTED, WorkflowState.RESEARCH_IN_PROGRESS,
                   WorkflowState.EVIDENCE_READY, WorkflowState.DRAFT_READY})
PRODUCTION = frozenset({WorkflowState.PRODUCTION_IN_PROGRESS, WorkflowState.AWAITING_VIDEO_REVIEW,
                        WorkflowState.VIDEO_APPROVED, WorkflowState.PACKAGED})
MEDICAL = PRODUCTION | {WorkflowState.MEDICALLY_APPROVED, WorkflowState.AWAITING_MEDICAL_REVIEW}


def request_change(project_dir: Path, kind: Literal['edit_production', 'edit_script'],
                   brief: str, context: dict, *, now: datetime) -> dict:
    """Record a confirmed request and invalidate approvals without granting any."""
    layout = resolve_project_layout(project_dir)
    project, revision = layout.manifest, layout.artifact_root
    if not brief.strip():
        raise ValueError('Yêu cầu sửa cần mô tả công việc.')
    if context.get('revision') not in (None, project.active_revision):
        raise ValueError('Revision đã thay đổi; gửi lại yêu cầu sửa.')
    if now.tzinfo is None:
        raise ValueError('Thời điểm yêu cầu phải có múi giờ.')
    early = kind == 'edit_script' and project.state in EARLY
    if not early and not ((kind == 'edit_production' and project.state in PRODUCTION)
                          or (kind == 'edit_script' and project.state in MEDICAL)):
        raise ValueError(f'Không thể yêu cầu sửa ở trạng thái {project.state.value}.')
    record = {'at': now.isoformat(), 'by': 'doctor-chat', 'kind': kind,
              'brief': brief.strip(), 'context': context, 'applied': False}
    updated = project
    if not early:
        target, resume = (
            (WorkflowState.NEEDS_MEDICAL_REVISION, WorkflowState.DRAFT_READY)
            if kind == 'edit_script' else
            (WorkflowState.NEEDS_PRODUCTION_REVISION, WorkflowState.PRODUCTION_IN_PROGRESS)
        )
        updated = transition_v2(project, target, TransitionContext(
            active_revision=project.active_revision, current_input_hash=canonical_json_hash(record),
            validated_artifacts=frozenset()), reason_code='chat_change',
            resume_state=resume, entered_at=now)
    stamp = now.strftime('%Y%m%dT%H%M%S%f') + '-' + uuid4().hex
    # Preserve approvals as audit history; active approval filenames must cease to exist.
    gates = ('medical', 'video') if kind == 'edit_script' and not early else ('video',)
    for gate in gates:
        approval = revision / 'reviews' / f'{gate}-approval.yaml'
        if approval.exists():
            destination = revision / 'reviews' / gate / f'{stamp}-superseded-approval.yaml'
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(approval, destination)
    if kind == 'edit_script' and project.state == WorkflowState.DRAFT_READY:
        mark_submitted(revision)
    if not early:
        product_review.mark_submitted(revision)
    write_yaml_atomic(revision / 'reviews/changes' / f'{stamp}-requested.yaml', record)
    if updated is not project:
        write_yaml_atomic(project_dir / 'project.yaml', updated.model_dump(mode='json'))
    return record


def pending(project_dir: Path) -> list[tuple[Path, dict]]:
    if not any((project_dir / 'revisions').glob('*/reviews/changes/*-requested.yaml')):
        return []
    directory = resolve_project_layout(project_dir).artifact_root / 'reviews/changes'
    return [(path, data) for path in sorted(directory.glob('*-requested.yaml'))
            if not (data := read_yaml(path)).get('applied')]


def context_label(context: dict) -> str:
    scene = str(context.get('scene') or '')
    seconds = context.get('time_s')
    if isinstance(seconds, (int, float)) and seconds >= 0:
        scene += f' @ {int(seconds) // 60:02d}:{int(seconds) % 60:02d}'
    return scene.strip()


def pending_note(project_dir: Path) -> str | None:
    requests = pending(project_dir)
    if not requests:
        return None
    record = requests[-1][1]
    return f"{record['brief']}\n{context_label(record['context'])}".strip()


def mark_applied(project_dir: Path) -> None:
    for path, record in pending(project_dir):
        write_yaml_atomic(path, {**record, 'applied': True})
