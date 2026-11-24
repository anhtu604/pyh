"""Project-level 0-100% progress calculation for the factory dashboard.

Computes a deterministic overall percentage from the workflow stage weights,
optionally refined with live sub-progress from Remotion render logs (tail-only
read) or TTS line audio files during production. Never fabricates sub-progress
when no live signal exists.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path

import yaml

from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.storage.files import read_yaml

# Fixed stage weights summing to 100. Production (TTS + visuals + Remotion render)
# carries the largest share because it dominates wall-clock time.
STAGE_WEIGHTS: tuple[tuple[str, int], ...] = (
    ('Chủ đề', 5),
    ('Nghiên cứu', 15),
    ('Kịch bản', 20),
    ('Duyệt y khoa', 5),
    ('Sản xuất', 40),
    ('Duyệt video', 10),
    ('Đóng gói', 5),
)

# Cumulative start percent for each workflow state before adding live sub-progress.
STATE_BASE_PERCENT: dict[WorkflowState, int] = {
    WorkflowState.IDEA: 0,
    WorkflowState.TOPIC_SELECTED: 5,
    WorkflowState.TOPIC_REJECTED: 0,
    WorkflowState.RESEARCH_IN_PROGRESS: 5,
    WorkflowState.EVIDENCE_READY: 20,
    WorkflowState.DRAFT_READY: 30,
    WorkflowState.NEEDS_MEDICAL_REVISION: 30,
    WorkflowState.AWAITING_MEDICAL_REVIEW: 40,
    WorkflowState.MEDICALLY_APPROVED: 45,
    WorkflowState.PRODUCTION_IN_PROGRESS: 45,
    WorkflowState.NEEDS_PRODUCTION_REVISION: 45,
    WorkflowState.AWAITING_VIDEO_REVIEW: 85,
    WorkflowState.VIDEO_APPROVED: 95,
    WorkflowState.PACKAGED: 100,
    WorkflowState.PUBLISHED_MANUAL: 100,
}

# Production stage (weight 40: 45% -> 85%) sub-phase budget:
# TTS voice synthesis gets 10 points (45 -> 55), Remotion render gets 30 points (55 -> 85).
PRODUCTION_TTS_WEIGHT = 10
PRODUCTION_RENDER_WEIGHT = 30
PRODUCTION_POST_RENDER_PERCENT = 82

_PRODUCTION_STATES: frozenset[WorkflowState] = frozenset({
    WorkflowState.MEDICALLY_APPROVED,
    WorkflowState.PRODUCTION_IN_PROGRESS,
    WorkflowState.NEEDS_PRODUCTION_REVISION,
})
_DONE_STATES: frozenset[WorkflowState] = frozenset({
    WorkflowState.PACKAGED,
    WorkflowState.PUBLISHED_MANUAL,
})

_STAGE_INDEX: dict[WorkflowState, int] = {
    WorkflowState.IDEA: 0,
    WorkflowState.TOPIC_SELECTED: 0,
    WorkflowState.TOPIC_REJECTED: 0,
    WorkflowState.RESEARCH_IN_PROGRESS: 1,
    WorkflowState.EVIDENCE_READY: 2,
    WorkflowState.DRAFT_READY: 2,
    WorkflowState.NEEDS_MEDICAL_REVISION: 2,
    WorkflowState.AWAITING_MEDICAL_REVIEW: 3,
    WorkflowState.MEDICALLY_APPROVED: 4,
    WorkflowState.PRODUCTION_IN_PROGRESS: 4,
    WorkflowState.NEEDS_PRODUCTION_REVISION: 4,
    WorkflowState.AWAITING_VIDEO_REVIEW: 5,
    WorkflowState.VIDEO_APPROVED: 6,
    WorkflowState.PACKAGED: 6,
    WorkflowState.PUBLISHED_MANUAL: 6,
}

_RENDER_HEADER_BYTES = 4096
_RENDER_TAIL_BYTES = 16384

_FRAME_PROGRESS_RE = re.compile(
    r'(?:Rendered|Encoded|Stitching|Rendering)\s+(\d+)\s*/\s*(\d+)',
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r'(\d{1,3}(?:\.\d+)?)\s*%')
_FAILED_TAIL_RE = re.compile(
    r'Command failed with exit code|TimeoutError:|Error:\s',
    re.IGNORECASE,
)


def _safe_astimezone(dt: datetime) -> datetime:
    try:
        return dt.astimezone()
    except (OSError, OverflowError, ValueError):
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _format_hhmm(dt: datetime | None) -> str:
    if dt is None:
        return ''
    local_dt = _safe_astimezone(dt)
    try:
        return local_dt.strftime('%H:%M')
    except (OSError, OverflowError, ValueError):
        return ''


def _safe_mtime(path: Path) -> datetime | None:
    try:
        return _safe_astimezone(datetime.fromtimestamp(path.stat().st_mtime, tz=UTC))
    except (OSError, OverflowError, ValueError):
        return None


def _short_reason(text: str, limit: int = 120) -> str:
    for raw in str(text or '').splitlines():
        line = raw.strip()
        if line and not line.startswith('log_path:'):
            return (line[: limit - 1].rstrip() + '…') if len(line) > limit else line
    return ''


def parse_render_log_percent(log_path: Path) -> int | None:
    """Read only the tail of a Remotion render log and return the latest 0..100 percent."""
    try:
        with log_path.open('rb') as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            if size <= 0:
                return None
            stream.seek(max(0, size - _RENDER_TAIL_BYTES))
            chunk = stream.read().decode('utf-8', errors='replace')
    except OSError:
        return None

    # Split on both \n and \r because Remotion overwrites progress lines with carriage returns.
    segments = [seg.strip() for seg in re.split(r'[\r\n]+', chunk) if seg.strip()]
    for seg in reversed(segments):
        if _FAILED_TAIL_RE.search(seg):
            # Keep scanning upward in case a progress line preceded the failure,
            # but never parse numbers from stack-trace lines.
            continue
        frame_match = _FRAME_PROGRESS_RE.search(seg)
        if frame_match:
            done = int(frame_match.group(1))
            total = int(frame_match.group(2))
            if total > 0 and done >= 0:
                pct = round(min(1.0, done / total) * 100)
                return max(0, min(100, pct))
        pct_match = _PERCENT_RE.search(seg)
        if pct_match:
            try:
                val = float(pct_match.group(1))
            except ValueError:
                continue
            if 0.0 <= val <= 100.0:
                return max(0, min(100, round(val)))
    return None


def _log_matches_slug(log_path: Path, slug: str) -> bool:
    """Check only the first few KB (command line header) of a render log for the project slug."""
    if not slug:
        return False
    try:
        with log_path.open('rb') as stream:
            header = stream.read(_RENDER_HEADER_BYTES).decode('utf-8', errors='replace')
    except OSError:
        return False
    first_lines = '\n'.join(header.splitlines()[:4])
    return (
        f'projects/{slug}/' in first_lines
        or f'projects\\{slug}\\' in first_lines
        or f'.{slug}.produce-' in first_lines
    )


def scan_render_logs(root: Path) -> list[tuple[float, Path]]:
    """Return render log paths sorted newest-first using a single directory scan."""
    render_dir = root / 'topics' / 'logs' / 'render'
    if not render_dir.is_dir():
        return []
    entries: list[tuple[float, Path]] = []
    try:
        with os.scandir(render_dir) as it:
            for entry in it:
                if not entry.name.endswith('.log'):
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    entries.append((entry.stat(follow_symlinks=False).st_mtime, Path(entry.path)))
                except OSError:
                    continue
    except OSError:
        return []
    entries.sort(key=lambda pair: pair[0], reverse=True)
    return entries


def _find_render_subprogress(
    root: Path,
    slug: str,
    render_logs: list[tuple[float, Path]] | None = None,
) -> tuple[int, datetime | None] | None:
    logs = scan_render_logs(root) if render_logs is None else render_logs
    for mtime, log_path in logs[:12]:
        if not _log_matches_slug(log_path, slug):
            continue
        pct = parse_render_log_percent(log_path)
        if pct is None:
            return None
        try:
            dt = _safe_astimezone(datetime.fromtimestamp(mtime, tz=UTC))
        except (OSError, OverflowError, ValueError):
            dt = None
        return pct, dt
    return None


def _count_script_lines(rev_dir: Path) -> int:
    script_path = rev_dir / 'script' / 'script.yaml'
    if not script_path.is_file():
        return 0
    try:
        data = read_yaml(script_path)
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        return 0
    lines = data.get('lines') if isinstance(data, dict) else None
    return len(lines) if isinstance(lines, list) else 0


def _find_tts_subprogress(
    rev_dir: Path,
    slug: str,
    *,
    total_lines: int | None = None,
) -> tuple[int, int, datetime | None] | None:
    """Detect active TTS synthesis line count from staging dir without fabricating data."""
    if not rev_dir.is_dir():
        return None
    prefix = f'.{slug}.produce-'
    newest_dir: Path | None = None
    newest_mtime = -1.0
    try:
        with os.scandir(rev_dir) as it:
            for entry in it:
                if not entry.name.startswith(prefix):
                    continue
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    mt = entry.stat(follow_symlinks=False).st_mtime
                except OSError:
                    continue
                if mt > newest_mtime:
                    newest_mtime = mt
                    newest_dir = Path(entry.path)
    except OSError:
        return None
    if newest_dir is None:
        return None

    lines_dir = newest_dir / 'audio' / 'lines'
    if not lines_dir.is_dir():
        return None

    done = 0
    latest_wav_mtime: float | None = None
    try:
        with os.scandir(lines_dir) as it:
            for entry in it:
                if not entry.name.endswith('.wav'):
                    continue
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if st.st_size > 0:
                    done += 1
                    if latest_wav_mtime is None or st.st_mtime > latest_wav_mtime:
                        latest_wav_mtime = st.st_mtime
    except OSError:
        return None

    total = total_lines if (total_lines is not None and total_lines > 0) else _count_script_lines(rev_dir)
    if total <= 0 or done <= 0:
        return None
    done = min(done, total)
    dt: datetime | None = None
    if latest_wav_mtime is not None:
        try:
            dt = _safe_astimezone(datetime.fromtimestamp(latest_wav_mtime, tz=UTC))
        except (OSError, OverflowError, ValueError):
            dt = None
    return done, total, dt


def compute_project_progress(
    root: Path,
    project_dir: Path,
    project: ProjectManifestV2,
    *,
    gate: str | None = None,
    blocked_note: str = '',
    paused: bool = False,
    doctor_question: dict | None = None,
    producing: bool = False,
    total_lines: int | None = None,
    updated_dt: datetime | None = None,
    render_logs: list[tuple[float, Path]] | None = None,
) -> dict:
    """Compute a project's 0-100% progress payload for dashboard cards and detail view."""
    effective_state = project.state
    if effective_state is WorkflowState.BLOCKED and project.side_state is not None:
        effective_state = project.side_state.resume_state or effective_state

    stage_idx = _STAGE_INDEX.get(effective_state, 0)
    stage_name = STAGE_WEIGHTS[stage_idx][0]
    percent = STATE_BASE_PERCENT.get(effective_state, 0)
    sub_percent: int | None = None
    sub_label = ''
    best_dt = updated_dt or _safe_mtime(project_dir / 'project.yaml')

    is_done = project.state in _DONE_STATES
    is_gate = bool(gate)
    is_question = bool(doctor_question) and not is_gate
    is_error = (project.state is WorkflowState.BLOCKED or bool(blocked_note)) and not is_gate and not is_done
    is_paused = bool(paused) and not is_gate and not is_done and not is_error

    if is_done:
        percent = 100
        status = 'done'
        label = 'Đã đóng gói' if project.state is WorkflowState.PACKAGED else 'Đã đăng'
        detail = ''
    elif is_gate:
        status = 'gate'
        label = 'Chờ bác sĩ duyệt'
        detail = 'Cổng y khoa' if gate == 'medical' else ('Cổng video' if gate == 'video' else '')
    elif is_question:
        status = 'gate'
        label = 'Chờ ý kiến bác sĩ'
        detail = _short_reason(str(doctor_question.get('question') or '')) if isinstance(doctor_question, dict) else ''
    elif is_error:
        status = 'error'
        label = stage_name
        detail = _short_reason(blocked_note) or 'Đang bị chặn'
    elif is_paused:
        status = 'paused'
        label = stage_name
        detail = 'Tạm dừng'
    else:
        status = 'running'
        label = stage_name
        detail = ''

        if effective_state in _PRODUCTION_STATES:
            rev_dir = project_dir / 'revisions' / project.active_revision
            # 1. Check Remotion render log tail first (later phase of production).
            render_info = _find_render_subprogress(root, project_dir.name, render_logs=render_logs)
            if render_info is not None:
                r_pct, r_dt = render_info
                sub_percent = r_pct
                sub_label = f'Đang render {r_pct}%'
                detail = sub_label
                percent = STATE_BASE_PERCENT[WorkflowState.PRODUCTION_IN_PROGRESS] + PRODUCTION_TTS_WEIGHT + round(
                    PRODUCTION_RENDER_WEIGHT * (r_pct / 100.0)
                )
                if r_dt is not None and (best_dt is None or r_dt > best_dt):
                    best_dt = r_dt
            else:
                # 2. Check active TTS line synthesis progress if staging lines exist.
                tts_info = _find_tts_subprogress(rev_dir, project_dir.name, total_lines=total_lines)
                if tts_info is not None:
                    done_lines, tot_lines, t_dt = tts_info
                    ratio = min(1.0, done_lines / tot_lines)
                    sub_percent = round(ratio * 100)
                    sub_label = f'Đọc giọng {done_lines}/{tot_lines} dòng'
                    detail = sub_label
                    percent = STATE_BASE_PERCENT[WorkflowState.PRODUCTION_IN_PROGRESS] + round(
                        PRODUCTION_TTS_WEIGHT * ratio
                    )
                    if t_dt is not None and (best_dt is None or t_dt > best_dt):
                        best_dt = t_dt
                elif not producing and (rev_dir / 'renders' / 'video.mp4').is_file():
                    percent = PRODUCTION_POST_RENDER_PERCENT
                    detail = 'Đã dựng xong, chờ kiểm định'

    percent = max(0, min(100, int(percent)))
    return {
        'percent': percent,
        'stage_index': stage_idx,
        'stage_name': stage_name,
        'status': status,
        'label': label,
        'detail': detail,
        'sub_percent': sub_percent,
        'sub_label': sub_label,
        'updated_hhmm': _format_hhmm(best_dt),
        'updated_at': best_dt.isoformat(timespec='seconds') if best_dt is not None else '',
    }
