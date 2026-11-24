"""Unit tests for 0-100% project progress calculation and render/TTS sub-progress."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.project_v2 import ProjectManifestV2
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import project_progress
from tests.helpers import create_v2_project_fixture


def _make_project(tmp_path: Path, state: str) -> tuple[Path, ProjectManifestV2]:
    project_dir = create_v2_project_fixture(tmp_path / 'projects')
    data = read_yaml(project_dir / 'project.yaml')
    data['state'] = state
    data['side_state'] = None
    write_yaml_atomic(project_dir / 'project.yaml', data)
    video_mp4 = project_dir / 'revisions/001/renders/video.mp4'
    if state in {'medically_approved', 'production_in_progress'} and video_mp4.exists():
        video_mp4.unlink()
    return project_dir, ProjectManifestV2.model_validate(data)


def test_stage_weights_sum_to_100_and_production_is_heaviest():
    total = sum(weight for _, weight in project_progress.STAGE_WEIGHTS)
    assert total == 100
    weights = dict(project_progress.STAGE_WEIGHTS)
    assert weights['Sản xuất'] == 40
    assert weights['Sản xuất'] > max(w for name, w in weights.items() if name != 'Sản xuất')


@pytest.mark.parametrize(
    ('state', 'expected_percent', 'expected_stage'),
    [
        ('idea', 0, 'Chủ đề'),
        ('topic_selected', 5, 'Chủ đề'),
        ('research_in_progress', 5, 'Nghiên cứu'),
        ('evidence_ready', 20, 'Kịch bản'),
        ('draft_ready', 30, 'Kịch bản'),
        ('awaiting_medical_review', 40, 'Duyệt y khoa'),
        ('medically_approved', 45, 'Sản xuất'),
        ('production_in_progress', 45, 'Sản xuất'),
        ('awaiting_video_review', 85, 'Duyệt video'),
        ('video_approved', 95, 'Đóng gói'),
        ('packaged', 100, 'Đóng gói'),
        ('published_manual', 100, 'Đóng gói'),
    ],
)
def test_base_percent_by_workflow_state(tmp_path: Path, state: str, expected_percent: int, expected_stage: str):
    project_dir, manifest = _make_project(tmp_path, state)
    gate = (
        'medical' if state == 'awaiting_medical_review'
        else ('video' if state == 'awaiting_video_review' else None)
    )
    info = project_progress.compute_project_progress(
        tmp_path,
        project_dir,
        manifest,
        gate=gate,
        updated_dt=datetime(2026, 11, 24, 14, 35, tzinfo=UTC),
    )
    assert info['percent'] == expected_percent
    assert info['stage_name'] == expected_stage
    assert len(info['updated_hhmm']) == 5 and ':' in info['updated_hhmm']


def test_waiting_at_doctor_gate_reports_gate_status_and_label(tmp_path: Path):
    project_dir, manifest = _make_project(tmp_path, 'awaiting_medical_review')
    info = project_progress.compute_project_progress(
        tmp_path, project_dir, manifest, gate='medical',
    )
    assert info['status'] == 'gate'
    assert info['label'] == 'Chờ bác sĩ duyệt'
    assert info['detail'] == 'Cổng y khoa'
    assert info['percent'] == 40


def test_packaged_is_always_100_percent_done(tmp_path: Path):
    project_dir, manifest = _make_project(tmp_path, 'packaged')
    info = project_progress.compute_project_progress(tmp_path, project_dir, manifest)
    assert info['percent'] == 100
    assert info['status'] == 'done'
    assert info['label'] == 'Đã đóng gói'


def test_blocked_project_reports_error_status_and_short_reason(tmp_path: Path):
    project_dir, manifest = _make_project(tmp_path, 'production_in_progress')
    info = project_progress.compute_project_progress(
        tmp_path,
        project_dir,
        manifest,
        blocked_note='log_path: topics/logs/x.log\nRender CL01 lỗi: Chrome timeout 25s\nchi tiết dòng 2',
    )
    assert info['status'] == 'error'
    assert info['detail'] == 'Render CL01 lỗi: Chrome timeout 25s'
    assert info['percent'] == 45


def test_render_log_subprogress_reads_tail_and_updates_overall_percent(tmp_path: Path):
    project_dir, manifest = _make_project(tmp_path, 'production_in_progress')
    slug = project_dir.name
    render_dir = tmp_path / 'topics' / 'logs' / 'render'
    render_dir.mkdir(parents=True, exist_ok=True)
    log_path = render_dir / '20261124T210000000000.log'
    # Include a large filler block so we verify tail-only reading works on big logs.
    filler = 'Bundling 1%\n' * 2000
    log_path.write_text(
        f'node pnpm.cjs --dir video render --output projects/{slug}/revisions/001/video.mp4\n\n'
        + filler
        + 'Rendered 450/1800\rRendered 900/1800, time remaining: 1m 20s\r',
        encoding='utf-8',
    )

    info = project_progress.compute_project_progress(
        tmp_path, project_dir, manifest, producing=True,
    )
    assert info['status'] == 'running'
    assert info['sub_percent'] == 50
    assert info['sub_label'] == 'Đang render 50%'
    # 45 (base) + 10 (TTS) + 50% of 30 (render) = 70
    assert info['percent'] == 70


def test_tts_line_subprogress_from_staging_dir(tmp_path: Path):
    project_dir, manifest = _make_project(tmp_path, 'production_in_progress')
    slug = project_dir.name
    rev_dir = project_dir / 'revisions' / manifest.active_revision
    write_yaml_atomic(
        rev_dir / 'script' / 'script.yaml',
        {'lines': [{'id': f'L{i:02d}', 'text': f'line {i}'} for i in range(1, 11)]},
    )
    staging = rev_dir / f'.{slug}.produce-abc123' / 'audio' / 'lines'
    staging.mkdir(parents=True, exist_ok=True)
    for i in range(1, 6):
        (staging / f'L{i:02d}.wav').write_bytes(b'RIFF1234WAVE')
    # Zero-byte incomplete file must not be counted.
    (staging / 'L06.wav').write_bytes(b'')

    info = project_progress.compute_project_progress(
        tmp_path, project_dir, manifest, producing=True,
    )
    assert info['sub_percent'] == 50
    assert info['sub_label'] == 'Đọc giọng 5/10 dòng'
    # 45 (base) + 50% of 10 (TTS) = 50
    assert info['percent'] == 50


def test_missing_empty_or_corrupt_render_log_never_raises(tmp_path: Path):
    project_dir, manifest = _make_project(tmp_path, 'production_in_progress')
    slug = project_dir.name

    # 1. Missing render log directory -> falls back cleanly to base percent, no fabrication
    info_missing = project_progress.compute_project_progress(
        tmp_path, project_dir, manifest, producing=True,
    )
    assert info_missing['percent'] == 45
    assert info_missing['sub_percent'] is None

    # 2. Corrupt binary / empty render log -> no exception, falls back cleanly
    render_dir = tmp_path / 'topics' / 'logs' / 'render'
    render_dir.mkdir(parents=True, exist_ok=True)
    bad_log = render_dir / '20261124T210100000000.log'
    bad_log.write_bytes(
        f'pnpm render projects/{slug}/revisions/001/out.mp4\n'.encode()
        + b'\xff\xfe\x00\x00corrupt-bytes-without-percent'
    )
    info_corrupt = project_progress.compute_project_progress(
        tmp_path, project_dir, manifest, producing=True,
    )
    assert info_corrupt['percent'] == 45
    assert info_corrupt['sub_percent'] is None
    assert project_progress.parse_render_log_percent(tmp_path / 'does-not-exist.log') is None
