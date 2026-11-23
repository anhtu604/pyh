"""Bounded product review: a critic agent scores the finished video before the doctor sees it.

Production holds a fresh final render at ``production_in_progress`` with a pending marker.
The critic scores it; fixable issues return for correction and another review.
Only a passing current review allows submission to the doctor.
"""

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from healthvideo.domain.asset_manifest import (
    AssetManifest,
    load_asset_manifest,
    validate_asset_manifest,
)
from healthvideo.domain.clip_plan import (
    ClipPlan,
    resolve_clip_scenes,
    validate_clip_plan,
)
from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.gate_review import GateApprovalRecord, GateKind
from healthvideo.domain.hook_outro import validate_hook_outro
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import (
    Storyboard,
    validate_anatomy_subjects,
    validate_style_a_mascot_poses,
)
from healthvideo.storage.explainer import read_explainer
from healthvideo.storage.files import (
    canonical_json_hash,
    read_agent_yaml,
    read_yaml,
    sha256_file,
    validate_agent_text,
    write_yaml_atomic,
)
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.tts import pronunciation as pronunciation_module
from healthvideo.tts.pronunciation import load_pronunciation_lexicon, pronunciation_hash
from healthvideo.visuals.anatomy_library import LIBRARY_PATH, load_library
from healthvideo.workflows import doctor_questions, scoped_review
from healthvideo.workflows.citations import resolve_citations
from healthvideo.workflows.decision_card import (
    MAX_DECISIONS,
    Decision,
    validate_decisions,
)
from healthvideo.workflows.draft import validate_estimated_layout
from healthvideo.workflows.factory_standards import style_a_active
from healthvideo.workflows.shorts_plan import ShortsPlan
from healthvideo.workflows.voice_prep import VoicePrepSheet, load_voice_prep_lexicon

PENDING = 'reviews/product/pending.yaml'
REBUILD_MARKER = 'reviews/product/rebuild-requested.yaml'
APPLIED_ANSWERS_FILE = 'reviews/product/applied-doctor-answers.yaml'
REPORT = 'reviews/product-review.yaml'
LOG = 'reviews/product-review-log.yaml'
MEDICAL_HASH_SYNC_LOG = 'reviews/product/medical-hash-sync-log.yaml'
RENDER_MANIFEST = 'renders/render-manifest.json'
PASS_SCORE = 7
MAX_REVIEWS = 4  # one first look plus three surgical fixes, then the doctor sees the score
STYLE_CRITERION = 'dung_phong_cach_pyh'
LEGACY_CRITERIA: dict[str, str] = {
    'hinh_khop_loi': 'Hình khớp lời đọc từng cảnh, đúng cơ chế',
    'hinh_ro': 'Hình rõ, nhãn tiếng Việt đọc được, không chồng hay cắt chữ',
    'nhip_dung': 'Nhịp dựng nhanh, không giữ một hình quá lâu',
    'am_thanh_phu_de': 'Phụ đề khớp lời, phát âm thuật ngữ đúng, nhạc không lấn giọng',
    'mo_ket': 'Mở đầu cuốn hút, kết rõ ràng có nhận diện kênh',
    'bai_dang': 'Bài đăng đúng nội dung video, không hứa hẹn quá đà',
}
CRITERIA: dict[str, str] = {
    **LEGACY_CRITERIA,
    STYLE_CRITERION: 'Đúng phong cách PYH (màu, chữ, mascot đúng nghĩa, sơ đồ dựng dần, phụ đề)',
}
ProductAction = Literal['product_review', 'revise_product', 'submit_video', 'wait_doctor', 'produce']

_REBUILD_TEXT_RE = re.compile(
    r'dựng\s+lại|dung\s+lai|chấm\s+lại|cham\s+lai|từ\s+đầu|tu\s+dau'
    r'|render\s+lại|sửa\s+hình|sua\s+hinh|tách\s+cảnh|tach\s+canh'
    r'|kể\s+cả\s+giọng|tạo\s+lại\s+giọng|làm\s+lại\s+giọng|rebuild|rerender',
    re.IGNORECASE,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCENE_ID_RE = re.compile(r'\b(?:S\d+|HOOK|OUTRO)\b')
_CLIP_ID_RE = re.compile(r'\bCL\d+\b')
_LOCAL_VALUE_IMPORT_RE = re.compile(
    r"^\s*import\s+(?!type\b).*?\s+from\s+['\"](\./[^'\"]+)['\"]",
    re.MULTILINE,
)
_VIDEO_SRC_DIRS = ('video/src/anatomy', 'video/src/components', 'video/src/scenes')
_REVISION_YAML_DIRS = ('script', 'storyboard', 'assets', 'evidence', 'explainer', 'posts')
_LOCKED_SCENE_FIELDS = (
    'id',
    'script_line_id',
    'narration',
    'claim_id',
    'chapter_id',
    'source_marker',
    'source_card',
    'evidence_highlight',
)
_EDITABLE_REV_YAMLS = frozenset({
    'storyboard/storyboard.yaml',
    'assets/asset-manifest.yaml',
    'script/clip-plan.yaml',
    'script/voice-prep.yaml',
    'posts/posts.yaml',
    'posts/shorts-plan.yaml',
})
_PRESENTATION_APPROVAL_KEYS = frozenset({
    'storyboard/storyboard.yaml',
    'assets/asset-manifest.yaml',
    'script/clip-plan.yaml',
})
_VIDEO_VISUAL_CRITERIA = frozenset({
    'hinh_khop_loi',
    'hinh_ro',
    'nhip_dung',
    'mo_ket',
    STYLE_CRITERION,
})
_DISPLAY_OUTRO_FILES = frozenset({
    'video/src/scenes/OutroScene.tsx',
    'video/src/scenes/YouTubeEndCard.tsx',
    'video/src/components/VisualAsset.tsx',
    'video/src/components/logoContrast.ts',
})
_SHARED_ANATOMY_INFRA = frozenset({'annotations.tsx', 'palette.ts', 'shade.ts', 'registry.ts'})
_POSTSET_KEYS = frozenset({
    'schema_version',
    'youtube_titles',
    'youtube_description',
    'youtube_tags',
    'clip_captions',
    'facebook_post',
    'youtube_community',
})


class ProductIssue(BaseModel):
    model_config = ConfigDict(extra='forbid')

    at: str = Field(min_length=1)  # scene id, mm:ss, or 'posts'
    criterion: str
    problem: str = Field(min_length=1)
    fix: str = Field(min_length=1)
    fixable: bool  # the production agent may fix it without reopening the medical gate
    issue_id: str = ''
    blocking_safety: bool = False
    edits: list[scoped_review.EditScope] = Field(default_factory=list)


class ProductReviewReport(BaseModel):
    model_config = ConfigDict(extra='forbid')

    scores: dict[str, int]
    summary: str = Field(min_length=1)
    issues: list[ProductIssue] = Field(default_factory=list)
    dropped_issues: list[dict] = Field(default_factory=list)
    checked: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    issue_statuses: dict[str, Literal['resolved', 'still_open']] = Field(default_factory=dict)
    overall: str = ''

    _normalize_issue_statuses = field_validator('issue_statuses', mode='before')(
        scoped_review.normalize_issue_statuses
    )


def _root(project: Path) -> Path:
    return resolve_project_layout(project).artifact_root


def _log(root: Path) -> dict:
    path = root / LOG
    data = read_yaml(path) if path.is_file() else {}
    return {'rounds': list(data.get('rounds', [])), 'submitted': int(data.get('submitted', 0))}


def _cycle(root: Path) -> list[dict]:
    """Rounds since the last submission to the doctor."""
    log = _log(root)
    return log['rounds'][log['submitted']:]


def render_hash(project: Path) -> str:
    return sha256_file(_root(project) / RENDER_MANIFEST)


def _parse_utc_dt(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def current_pronunciation_sha256(rev: Path) -> str | None:
    """Compute the active pronunciation lexicon hash (shared profile + revision voice-prep)."""
    profile_path = pronunciation_module.PRONUNCIATION_PROFILE_PATH
    if not profile_path.is_file():
        return None
    lexicon = load_pronunciation_lexicon(profile_path)
    if (rev / 'script/voice-prep.yaml').is_file():
        lexicon = load_voice_prep_lexicon(rev, lexicon)
    return pronunciation_hash(lexicon)


def rebuild_requested(artifact_root: Path) -> bool:
    """Return True when a doctor decision or stale-render reset requires re-running produce."""
    marker = artifact_root / REBUILD_MARKER
    if not marker.is_file():
        return False
    try:
        data = read_yaml(marker)
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return True
    before_sha = str(data.get('before_render_sha256') or '').strip()
    manifest_path = artifact_root / RENDER_MANIFEST
    if not before_sha or not manifest_path.is_file():
        return True
    try:
        return sha256_file(manifest_path) == before_sha
    except OSError:
        return True


def _medical_approval_time(rev: Path) -> datetime | None:
    approval_path = rev / 'reviews/medical-approval.yaml'
    if not approval_path.is_file():
        return None
    try:
        data = read_yaml(approval_path)
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return None
    return _parse_utc_dt(data.get('reviewed_at'))


def _render_mtime_utc(rev: Path) -> datetime | None:
    video_path = rev / 'renders/video.mp4'
    manifest_path = rev / RENDER_MANIFEST
    target = video_path if video_path.is_file() else manifest_path if manifest_path.is_file() else None
    if target is None:
        return None
    try:
        return datetime.fromtimestamp(target.stat().st_mtime, tz=UTC)
    except OSError:
        return None


def render_is_stale(project: Path) -> bool:
    """Return True when the rendered cut does not match current script, storyboard, or pronunciation."""
    try:
        rev = _root(project)
    except (OSError, ValueError):
        return False
    if rebuild_requested(rev):
        return True
    manifest_path = rev / RENDER_MANIFEST
    if not manifest_path.is_file():
        return True
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return True
    if not isinstance(manifest, Mapping):
        return True

    if 'pronunciation_sha256' in manifest:
        try:
            current_pron = current_pronunciation_sha256(rev)
        except (OSError, TypeError, ValueError):
            current_pron = None
        if current_pron is not None and manifest.get('pronunciation_sha256') != current_pron:
            return True

    video_path = rev / 'renders/video.mp4'
    has_real_render = video_path.is_file() or 'input_hash' in manifest
    if not has_real_render:
        return False

    render_target = video_path if video_path.is_file() else manifest_path
    try:
        render_mtime = render_target.stat().st_mtime
    except OSError:
        return True

    approved_at = _medical_approval_time(rev)
    if approved_at is not None and approved_at > datetime.fromtimestamp(render_mtime, tz=UTC):
        return True

    for rel in (
        'storyboard/storyboard.yaml',
        'script/script.yaml',
        'script/voice-prep.yaml',
        'assets/asset-manifest.yaml',
    ):
        candidate = rev / rel
        if candidate.is_file():
            try:
                if candidate.stat().st_mtime > render_mtime:
                    return True
            except OSError:
                continue
    return False


def pending(project: Path) -> bool:
    try:
        rev = _root(project)
        if not (rev / PENDING).is_file():
            return False
        return not render_is_stale(project)
    except (OSError, ValueError):
        return False


def hold(artifact_root: Path, input_hash: str) -> None:
    """Called by production after a final render: wait for the critic, not the doctor."""
    (artifact_root / REBUILD_MARKER).unlink(missing_ok=True)
    write_yaml_atomic(artifact_root / PENDING, {'version': 1, 'input_hash': input_hash})


def _applied_answers_set(rev: Path) -> set[str]:
    path = rev / APPLIED_ANSWERS_FILE
    if not path.is_file():
        return set()
    try:
        data = read_yaml(path)
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return set()
    ids = data.get('question_ids')
    return {str(item) for item in ids if item} if isinstance(ids, list) else set()


def _mark_answer_applied(rev: Path, question_id: str) -> None:
    qid = str(question_id or '').strip()
    if not qid:
        return
    ids = _applied_answers_set(rev)
    if qid in ids:
        return
    ids.add(qid)
    write_yaml_atomic(rev / APPLIED_ANSWERS_FILE, {'version': 1, 'question_ids': sorted(ids)})


def classify_doctor_answer(answered: Mapping[str, Any]) -> Literal['rebuild', 'accept', 'other']:
    """Classify a doctor's Station 12 decision into rebuild, accept, or other."""
    ans = answered.get('answer')
    if not isinstance(ans, Mapping):
        return 'other'
    opt_id = str(ans.get('option_id') or '').strip()
    text = str(ans.get('text') or '').strip()
    if opt_id == 'accept_for_video_gate':
        return 'accept'
    if opt_id in {'fix_visuals', 'split_long_scenes'}:
        return 'rebuild'
    if text and _REBUILD_TEXT_RE.search(text):
        return 'rebuild'
    return 'other'


def reset_cycle_for_rebuild(
    project: Path,
    *,
    question_id: str | None = None,
    reason: str = '',
) -> None:
    """Clear stale pending hold, advance log cycle, and mark rebuild required before produce."""
    rev = _root(project)
    if question_id:
        _mark_answer_applied(rev, question_id)
    manifest_path = rev / RENDER_MANIFEST
    before_sha = sha256_file(manifest_path) if manifest_path.is_file() else ''
    write_yaml_atomic(
        rev / REBUILD_MARKER,
        {
            'version': 1,
            'before_render_sha256': before_sha,
            'question_id': question_id or None,
            'reason': str(reason or '').strip(),
            'requested_at': datetime.now(UTC).isoformat(timespec='seconds'),
        },
    )
    log_path = rev / LOG
    if log_path.is_file():
        log = _log(rev)
        if log['submitted'] < len(log['rounds']):
            for old_round in log['rounds']:
                old_round.pop('snapshot', None)
            log['submitted'] = len(log['rounds'])
            write_yaml_atomic(log_path, {'version': 1, **log})
    (rev / PENDING).unlink(missing_ok=True)


def apply_doctor_answer(project: Path, answered: Mapping[str, Any]) -> str:
    """Apply a doctor's answered Station 12 stuck_issue decision to the revision state."""
    if str(answered.get('station') or '') != '12' or str(answered.get('kind') or '') != 'stuck_issue':
        return 'other'
    rev = _root(project)
    qid = str(answered.get('id') or '').strip()
    action = classify_doctor_answer(answered)
    if action == 'rebuild':
        ans = answered.get('answer') or {}
        reason = str(ans.get('text') or ans.get('option_label') or ans.get('option_id') or '').strip()
        reset_cycle_for_rebuild(project, question_id=qid or None, reason=reason)
    elif qid:
        _mark_answer_applied(rev, qid)
    return action


def _stuck_fingerprint(latest_round: Mapping[str, Any], context: Sequence[Mapping[str, Any]]) -> str:
    return canonical_json_hash({
        'station': '12',
        'kind': 'stuck_issue',
        'round': latest_round.get('round'),
        'render_sha256': str(latest_round.get('render_sha256') or ''),
        'issues': sorted((str(c.get('code') or ''), str(c.get('location') or '')) for c in context),
    })


def _stuck_context_and_options(latest_round: Mapping[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    statuses = latest_round.get('issue_statuses') or {}
    issues = list(latest_round.get('issues') or [])
    open_issues = [
        item for item in issues
        if not statuses or statuses.get(item.get('issue_id', '')) == 'still_open'
    ] or issues
    context = [
        {
            'code': str(item.get('issue_id') or ''),
            'location': str(item.get('at') or ''),
            'summary': str(item.get('problem') or '').strip()[:200],
        }
        for item in open_issues
    ]
    options = [
        {
            'id': 'fix_visuals',
            'label': 'Sửa hình các cảnh bị nêu',
            'detail': 'Giao Thợ dựng sửa lại hình ảnh và bố cục các cảnh còn mở ở vòng cuối.',
        },
        {
            'id': 'split_long_scenes',
            'label': 'Tách cảnh dài',
            'detail': 'Tách các cảnh dài để cải thiện nhịp dựng và khớp lời đọc.',
        },
    ]
    if all(not bool(item.get('blocking_safety', False)) for item in open_issues):
        options.append({
            'id': 'accept_for_video_gate',
            'label': 'Chấp nhận như hiện tại và nộp bác sĩ duyệt video',
            'detail': 'Giữ bản dựng hiện tại và chuyển chỉ đạo cho Điều phối viên xem xét trước cổng duyệt video.',
        })
    return context, options


def reconcile_doctor_question(root: Path, project: Path) -> None:
    """Clear obsolete Station 12 stuck questions and apply unapplied doctor rebuild directives."""
    try:
        rev = _root(project)
    except (OSError, ValueError):
        return
    slug = project.name
    open_q = doctor_questions.open_question(root, slug)
    render_dt = _render_mtime_utc(rev)
    stale = render_is_stale(project)

    if (
        open_q is not None
        and str(open_q.get('station') or '') == '12'
        and str(open_q.get('kind') or '') == 'stuck_issue'
    ):
        approved_at = _medical_approval_time(rev)
        created_at = _parse_utc_dt(open_q.get('created_at'))
        approval_newer = (
            approved_at is not None and created_at is not None and approved_at > created_at
        )
        matched_hist = doctor_questions.has_matching_answered_history(
            root, slug, open_q, min_answered_at=render_dt,
        )
        if approval_newer or stale or matched_hist is not None:
            reason = (
                'medical_approval_newer' if approval_newer
                else 'stale_render' if stale
                else 'already_answered_in_history'
            )
            doctor_questions.supersede(root, slug, reason=reason)
            if approval_newer or stale:
                reset_cycle_for_rebuild(project, reason=reason)
            open_q = None

    if open_q is None:
        applied = _applied_answers_set(rev)
        for entry in reversed(doctor_questions.history(root, slug)):
            if (
                entry.get('status') == 'answered'
                and str(entry.get('station') or '') == '12'
                and str(entry.get('kind') or '') == 'stuck_issue'
            ):
                qid = str(entry.get('id') or '').strip()
                ans = entry.get('answer')
                ans_at = _parse_utc_dt(ans.get('at')) if isinstance(ans, Mapping) else None
                if qid and qid not in applied and (render_dt is None or ans_at is None or ans_at >= render_dt):
                    apply_doctor_answer(project, entry)
                break

    if (rev / PENDING).is_file() and render_is_stale(project):
        reset_cycle_for_rebuild(project, reason='stale_render')


def next_product_action(
    project: Path,
    *,
    root: Path | None = None,
    create_question: bool = True,
) -> ProductAction:
    if render_is_stale(project):
        if create_question:
            reset_cycle_for_rebuild(project, reason='stale_render')
        return 'produce'
    rev = _root(project)
    rounds = _cycle(rev)
    # A rebuilt render deserves a fresh review: "stuck" only applies to the render already reviewed.
    if not rounds or rounds[-1]['render_sha256'] != render_hash(project):
        return 'product_review'
    if scoped_review.stuck(rounds) and not rounds[-1]['passed']:
        latest_round = rounds[-1]
        context, options = _stuck_context_and_options(latest_round)
        fingerprint = _stuck_fingerprint(latest_round, context)
        factory_root = root if root is not None else project.resolve().parents[1]
        probe = {'station': '12', 'kind': 'stuck_issue', 'context': context, 'fingerprint': fingerprint}
        answered = doctor_questions.has_matching_answered_history(
            factory_root,
            project.name,
            probe,
            min_answered_at=_render_mtime_utc(rev),
        )
        if answered is not None:
            decision = classify_doctor_answer(answered)
            if decision == 'rebuild':
                if create_question:
                    apply_doctor_answer(project, answered)
                return 'produce'
            if decision == 'accept':
                if create_question:
                    apply_doctor_answer(project, answered)
                require_passed_review(project, root=factory_root)
                return 'submit_video'
            return 'wait_doctor'
        if create_question:
            doctor_questions.ask(
                factory_root,
                project.name,
                station='12',
                kind='stuck_issue',
                question='Trạm 12 kẹt cùng issue qua 2 vòng duyệt sản phẩm; bác sĩ chọn hướng xử lý tiếp theo.',
                context=context,
                options=options,
                allow_free_text=True,
                fingerprint=fingerprint,
            )
        return 'wait_doctor'
    latest = rounds[-1]
    if latest['passed']:
        require_passed_review(project)
        return 'submit_video'
    if len(rounds) >= MAX_REVIEWS:
        raise ValueError('Trạm 12 chưa đạt sau các vòng sửa; cần xử lý nhận xét trước khi nộp bác sĩ.')
    if len(latest.get('decisions', [])) > MAX_DECISIONS:
        return 'product_review' if latest.get('fix_attempted') else 'revise_product'
    if latest.get('fix_attempted'):
        return 'product_review'
    if not any(item['fixable'] for item in latest['issues']):
        raise ValueError('Trạm 12 chưa đạt; lỗi vượt phạm vi thợ dựng, cần xử lý trước khi nộp bác sĩ.')
    return 'revise_product'


def criteria_for_revision(root: Path) -> dict[str, str]:
    """Return blocking Station 12 criteria: 7 for Style A revisions, 6 for legacy revisions."""
    return CRITERIA if style_a_active(root) else LEGACY_CRITERIA


def _has_doctor_video_gate_override(
    project: Path,
    latest_round: Mapping[str, Any],
    *,
    root: Path | None = None,
) -> bool:
    """Return True when the doctor explicitly accepted the current non-safety stuck round for the video gate."""
    issues = list(latest_round.get('issues') or [])
    if any(bool(item.get('blocking_safety', False)) for item in issues if isinstance(item, Mapping)):
        return False
    if latest_round.get('render_sha256') != render_hash(project):
        return False
    rev = _root(project)
    context, _ = _stuck_context_and_options(latest_round)
    fingerprint = _stuck_fingerprint(latest_round, context)
    factory_root = root if root is not None else project.resolve().parents[1]
    probe = {'station': '12', 'kind': 'stuck_issue', 'context': context, 'fingerprint': fingerprint}
    answered = doctor_questions.has_matching_answered_history(
        factory_root,
        project.name,
        probe,
        min_answered_at=_render_mtime_utc(rev),
    )
    return answered is not None and classify_doctor_answer(answered) == 'accept'


def require_passed_review(project: Path, *, root: Path | None = None) -> None:
    rev_root = _root(project)
    rounds = _log(rev_root)['rounds']
    if not rounds:
        raise ValueError('Trạm 12 chưa có kết quả kiểm định sản phẩm.')
    latest = rounds[-1]
    if latest.get('render_sha256') != render_hash(project):
        raise ValueError('Trạm 12 cần kiểm định lại bản dựng hiện hành.')
    report = ProductReviewReport.model_validate({
        key: latest[key] for key in ProductReviewReport.model_fields if key in latest
    })
    style_required = style_a_active(rev_root)
    _validated(report, allow_legacy=not style_required, style_required=style_required)
    if (
        len(report.decisions) <= MAX_DECISIONS
        and _has_doctor_video_gate_override(project, latest, root=root)
    ):
        return
    blocking = criteria_for_revision(rev_root)
    if (latest.get('passed') is not True
            or any(report.scores[key] < PASS_SCORE for key in blocking)
            or len(report.decisions) > MAX_DECISIONS):
        raise ValueError('Trạm 12 chưa đạt; chưa được nộp bác sĩ duyệt video.')


def _validated(
    report: ProductReviewReport,
    *,
    allow_legacy: bool = False,
    style_required: bool | None = None,
) -> None:
    if style_required is None:
        style_required = not allow_legacy
    validate_decisions(report.decisions)
    allowed_keys = (set(CRITERIA), set(LEGACY_CRITERIA)) if allow_legacy else (set(CRITERIA),)
    if set(report.scores) not in allowed_keys:
        raise ValueError('Báo cáo duyệt sản phẩm phải có đủ đúng các tiêu chí.')
    if any(not 1 <= score <= 10 for score in report.scores.values()):
        raise ValueError('Điểm duyệt sản phẩm phải từ 1 đến 10.')
    for issue in report.issues:
        if issue.criterion not in CRITERIA:
            raise ValueError(f'Tiêu chí không tồn tại: {issue.criterion}')
    covered = {issue.criterion for issue in report.issues}
    checked_keys = CRITERIA if style_required else LEGACY_CRITERIA
    missing = [key for key in checked_keys
               if report.scores.get(key, PASS_SCORE) < PASS_SCORE and key not in covered]
    if missing:
        raise ValueError('Tiêu chí chưa đạt thiếu chỗ cần sửa: ' + ', '.join(missing))


def _allowed_scene_ids(issues: Sequence[Mapping[str, Any] | ProductIssue]) -> set[str]:
    """Extract scene IDs (S\\d+) from ``at`` and ``edits`` of open fixable issues."""
    allowed: set[str] = set()
    for item in issues:
        fixable = item['fixable'] if isinstance(item, Mapping) else item.fixable
        if not fixable:
            continue
        at = item.get('at', '') if isinstance(item, Mapping) else item.at
        allowed.update(_SCENE_ID_RE.findall(str(at)))
        edits = (item.get('edits') if isinstance(item, Mapping) else item.edits) or []
        for scope in edits:
            if isinstance(scope, Mapping):
                allowed.update(_SCENE_ID_RE.findall(str(scope.get('path', ''))))
                allowed.update(_SCENE_ID_RE.findall(str(scope.get('scene_id', ''))))
            else:
                allowed.update(_SCENE_ID_RE.findall(str(getattr(scope, 'path', ''))))
    return allowed


def _is_test_source(path: Path) -> bool:
    return '.test.' in path.name


def _open_edit_paths(root: Path) -> set[str]:
    rounds = _cycle(root)
    if not rounds or rounds[-1].get('passed'):
        return set()
    return {
        scope['path']
        for item in rounds[-1].get('issues', [])
        for scope in item.get('edits', [])
        if isinstance(scope, Mapping) and scope.get('path')
    }


def _load_anatomy_library(repo: Path) -> dict[str, dict[str, Any]]:
    if (repo / LIBRARY_PATH).is_file():
        return load_library(repo)
    if (_REPO_ROOT / LIBRARY_PATH).is_file():
        return load_library(_REPO_ROOT)
    return {}


def _anatomy_component_paths(repo: Path, subjects: Iterable[str]) -> set[str]:
    """Resolve anatomy TSX files for ``subjects`` and their non-infra diagram imports."""
    library = _load_anatomy_library(repo)
    resolved: set[str] = set()
    queue: list[str] = []
    for subject in subjects:
        info = library.get(subject)
        if not info or not info.get('file'):
            continue
        rel = f"video/src/anatomy/{info['file']}"
        if rel not in resolved:
            resolved.add(rel)
            queue.append(rel)
    while queue:
        rel = queue.pop()
        file_path = repo / rel
        if not file_path.is_file():
            continue
        try:
            text = file_path.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            continue
        for imp in _LOCAL_VALUE_IMPORT_RE.findall(text):
            stem = imp[2:]
            for suffix in ('.tsx', '.ts'):
                candidate_name = f'{stem}{suffix}'
                if candidate_name in _SHARED_ANATOMY_INFRA:
                    continue
                candidate = (file_path.parent / candidate_name).resolve()
                try:
                    cand_rel = candidate.relative_to(repo.resolve()).as_posix()
                except ValueError:
                    continue
                if candidate.is_file() and cand_rel not in resolved:
                    resolved.add(cand_rel)
                    queue.append(cand_rel)
                    break
    return resolved


def _storyboard_related_video_src(
    repo: Path,
    root: Path,
    available_video_src: Iterable[str],
) -> set[str]:
    sb_path = root / 'storyboard/storyboard.yaml'
    if not sb_path.is_file():
        return set()
    try:
        sb_text = sb_path.read_text(encoding='utf-8')
        sb_data = yaml.safe_load(sb_text) or {}
    except (OSError, UnicodeError, yaml.YAMLError):
        return set()
    scenes = sb_data.get('scenes', []) if isinstance(sb_data, Mapping) else []
    subjects = {
        scene['anatomy']['subject']
        for scene in scenes
        if isinstance(scene, Mapping)
        and isinstance(scene.get('anatomy'), Mapping)
        and scene['anatomy'].get('subject')
    }
    related = _anatomy_component_paths(repo, subjects)
    assets_path = root / 'assets/asset-manifest.yaml'
    combined_text = sb_text
    if assets_path.is_file():
        try:
            combined_text += '\n' + assets_path.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            pass
    for rel in available_video_src:
        if rel in combined_text or Path(rel).name in combined_text:
            related.add(rel)
    return related


def record_review(project: Path, reviewed_hash: str) -> dict:
    """Validate the critic's report, append it to the log and consume the report."""
    root = _root(project)
    if render_hash(project) != reviewed_hash:
        raise ValueError('Agent duyệt sản phẩm không được dựng lại hay sửa bản dựng.')
    report_file = root / REPORT
    if not report_file.is_file():
        raise ValueError('Agent duyệt sản phẩm chưa ghi báo cáo (thiếu reviews/product-review.yaml).')
    try:
        report = ProductReviewReport.model_validate(read_agent_yaml(report_file))
    except yaml.YAMLError as exc:
        raise ValueError(f'Báo cáo duyệt sản phẩm sai YAML: {exc}') from exc
    log = _log(root)
    previous = log['rounds'][-1] if len(log['rounds']) > log['submitted'] else None
    report = ProductReviewReport.model_validate(scoped_review.reconcile(
        previous if previous and not previous['passed'] and previous.get('snapshot') is not None else None,
        report.model_dump(mode='json'), 'at'))
    style_required = style_a_active(root)
    _validated(report, allow_legacy=not style_required, style_required=style_required)
    blocking = criteria_for_revision(root)
    edit_paths = {scope.path for item in report.issues for scope in item.edits}
    entry = {
        'round': len(log['rounds']) + 1,
        'render_sha256': reviewed_hash,
        'passed': (all(score >= PASS_SCORE for key, score in report.scores.items() if key in blocking)
                   and len(report.decisions) <= MAX_DECISIONS),
        **report.model_dump(mode='json'),
        'snapshot': snapshot(project, extra_paths=edit_paths),
    }
    log['rounds'].append(entry)
    for old_round in log['rounds'][:-1]:
        old_round.pop('snapshot', None)
    write_yaml_atomic(root / LOG, {'version': 1, **log})
    report_file.unlink()
    return entry


def repair_files(project: Path) -> dict[str, bytes]:
    """Capture permitted product sources, plus locked YAML to detect collateral edits."""
    root = _root(project)
    repo = project.parent.parent
    edit_paths = _open_edit_paths(root)
    files: dict[str, bytes] = {}
    for subdir in _VIDEO_SRC_DIRS:
        base = repo / subdir
        if not base.is_dir():
            continue
        for p in base.rglob('*'):
            if not p.is_file() or p.suffix not in {'.ts', '.tsx'}:
                continue
            rel = p.relative_to(repo).as_posix()
            if _is_test_source(p) and rel not in edit_paths:
                continue
            files[rel] = p.read_bytes()
    for directory in _REVISION_YAML_DIRS:
        dir_path = root / directory
        if not dir_path.is_dir():
            continue
        for p in dir_path.rglob('*.yaml'):
            if p.is_file():
                files[p.relative_to(repo).as_posix()] = p.read_bytes()
    return files


def snapshot(project: Path, *, extra_paths: Iterable[str] | None = None) -> dict[str, str]:
    """Keep revision YAMLs plus storyboard-relevant and edit-scoped ``video/src/`` files."""
    root = _root(project)
    repo = project.parent.parent
    files = repair_files(project)
    edit_paths = _open_edit_paths(root) | set(extra_paths or ())
    for rel in edit_paths:
        if rel not in files and rel.startswith('video/src/') and (repo / rel).is_file():
            files[rel] = (repo / rel).read_bytes()
    keep_video_src = edit_paths | _storyboard_related_video_src(
        repo,
        root,
        [path for path in files if path.startswith('video/src/')],
    )
    return {
        path: raw.decode('utf-8')
        for path, raw in files.items()
        if not path.startswith('video/src/') or path in keep_video_src
    }


def incremental_context(project: Path, *, writer: bool = False) -> str:
    root = _root(project)
    rounds = _cycle(root)
    if not rounds or rounds[-1]['passed'] or 'snapshot' not in rounds[-1]:
        return ''
    latest = rounds[-1]
    if writer:
        current = snapshot(project)
        fragments: dict[str, str] = {}
        for item in latest['issues']:
            for scope in item.get('edits', []):
                path = scope['path']
                fragments[f"{path}:{scope['start_line']}-{scope['end_line']}"] = ''.join(
                    current.get(path, '').splitlines(keepends=True)[scope['start_line']-1:scope['end_line']])
        parts = [
            'Open issues:\n' + yaml.safe_dump(latest['issues'], allow_unicode=True),
            '\nEditable fragments:\n' + yaml.safe_dump(fragments, allow_unicode=True),
        ]
        allowed_scenes = sorted(_allowed_scene_ids(latest['issues']))
        sb_path = root / 'storyboard/storyboard.yaml'
        if allowed_scenes and sb_path.is_file():
            sb_data = read_yaml(sb_path)
            scenes = [
                scene for scene in sb_data.get('scenes', [])
                if isinstance(scene, Mapping) and scene.get('id') in allowed_scenes
            ]
            if scenes:
                parts.append(
                    '\nEditable storyboard scenes:\n'
                    + yaml.safe_dump(scenes, allow_unicode=True, sort_keys=False)
                )
        notes = revision_notes(project)
        if notes:
            parts.append('\n' + notes)
        return ''.join(parts)
    return (scoped_review.packet(latest['issues'], latest['snapshot'], snapshot(project))
            + _motion_evidence(root)
            + '\nĐiểm và điểm khó đã ghi (chỉ đọc):\n' + yaml.safe_dump(
                {'scores': latest['scores'], 'decisions': latest.get('decisions', [])}, allow_unicode=True))


def _motion_evidence(root: Path) -> str:
    """Attach measured intervals to the critic's incremental evidence packet."""
    path = root / 'reviews/motion-report.json'
    if not path.is_file():
        return '\nMotion evidence: motion-report.json unavailable; do not infer motion from stills.\n'
    try:
        report = json.loads(path.read_text(encoding='utf-8'))
        if report['video_sha256'] != sha256_file(root / 'renders/video.mp4'):
            return '\nMotion evidence: stale motion-report.json; video hash differs.\n'
        summary = {key: report[key] for key in ('passed', 'max_static_s', 'scenes_with_violation')}
        summary['static_runs'] = [
            {key: run[key] for key in ('scene_ids', 'start_s', 'end_s', 'duration_s')}
            for run in report['static_runs']
        ]
        return '\nMeasured motion-report.json evidence:\n' + json.dumps(summary, ensure_ascii=False)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return f'\nMotion evidence unavailable: {error}\n'


def _is_locked_medical_rel(rel: str) -> bool:
    return (
        rel in {'script/script.yaml', 'assets/license-ledger.yaml', 'script/outline.yaml', 'script/questions.yaml'}
        or rel.startswith(('evidence/', 'explainer/'))
    )


def _normalize_scope_path(path: str, rev_prefix: str) -> str:
    if path.startswith(('video/src/', rev_prefix + '/')):
        return path
    if path in _EDITABLE_REV_YAMLS or _is_locked_medical_rel(path):
        return f'{rev_prefix}/{path}'
    return path


def _validate_storyboard_explainer_bindings(root: Path, storyboard: Storyboard) -> None:
    explainer = read_explainer(root)
    layers = {layer.id: layer for layer in explainer.layers}
    for scene in storyboard.scenes:
        if scene.explainer_layer_id is None:
            continue
        layer = layers.get(scene.explainer_layer_id)
        if layer is None:
            raise ValueError(f'Scene {scene.id}: unknown explainer layer {scene.explainer_layer_id}')
        if scene.visual != layer.visual.kind:
            raise ValueError(
                f'Scene {scene.id}: visual must match explainer layer '
                f'{layer.id}: {layer.visual.kind}'
            )


def _scene_asset_refs(sb_data: Mapping[str, Any] | None) -> dict[str, set[str]]:
    refs: dict[str, set[str]] = {}
    if not isinstance(sb_data, Mapping):
        return refs
    for scene in sb_data.get('scenes', []):
        if not isinstance(scene, Mapping) or not scene.get('id'):
            continue
        sid = str(scene['id'])
        for asset_ref in scene.get('visual_assets') or ():
            if isinstance(asset_ref, Mapping) and asset_ref.get('path'):
                refs.setdefault(str(asset_ref['path']), set()).add(sid)
    return refs


def _is_audio_related_at(at: str) -> bool:
    low = at.lower()
    return any(token in low for token in (
        'voice-prep', 'pronunciation', 'video-qa', 'audio', 'âm thanh', 'phát âm', 'phụ đề',
    ))


def _is_shorts_related_issue(item: Mapping[str, Any]) -> bool:
    text = f"{item.get('at', '')} {item.get('problem', '')} {item.get('fix', '')}".lower()
    return 'short' in text or 'clip' in text or bool(_CLIP_ID_RE.search(str(item.get('at', ''))))


def _shorts_revision_hash(root: Path) -> str:
    return canonical_json_hash({
        'script': read_yaml(root / 'script/script.yaml'),
        'storyboard': read_yaml(root / 'storyboard/storyboard.yaml'),
    })


def _check_edit_targets(
    fixable_issues: Sequence[Mapping[str, Any]],
    rev_prefix: str,
) -> dict[str, list[dict]]:
    by_path: dict[str, list[dict]] = {}
    for item in fixable_issues:
        for raw_scope in item.get('edits', []):
            norm = _normalize_scope_path(raw_scope['path'], rev_prefix)
            scope = {**raw_scope, 'path': norm}
            if norm.startswith(rev_prefix + '/'):
                rel = norm[len(rev_prefix) + 1:]
                if _is_locked_medical_rel(rel):
                    raise ValueError('Repair scope violation: medical artifact is locked')
                if rel not in _EDITABLE_REV_YAMLS:
                    raise ValueError('Repair scope violation: product target is locked')
            elif not (norm.startswith(('video/src/anatomy/', 'video/src/components/', 'video/src/scenes/'))
                      and norm.endswith(('.ts', '.tsx'))):
                raise ValueError('Repair scope violation: product target is locked')
            by_path.setdefault(norm, []).append(scope)
    return by_path


def _check_storyboard_repair(
    project: Path,
    root: Path,
    before_raw: bytes | None,
    after_raw: bytes | None,
    allowed_scenes: set[str],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    before_data = yaml.safe_load(before_raw) if before_raw is not None else {}
    after_data = yaml.safe_load(after_raw) if after_raw is not None else {}
    if before_raw == after_raw:
        return before_data, after_data
    if before_raw is None or after_raw is None or not allowed_scenes:
        raise ValueError('Repair scope violation: product target is locked')
    scoped_review.check_nodes(before_raw, after_raw, allowed_scenes, 'scenes')
    before_scenes = {
        s['id']: s for s in before_data.get('scenes', []) if isinstance(s, Mapping) and 'id' in s
    }
    after_scenes = {
        s['id']: s for s in after_data.get('scenes', []) if isinstance(s, Mapping) and 'id' in s
    }
    for sid in allowed_scenes:
        if sid not in before_scenes or sid not in after_scenes:
            continue
        for field in _LOCKED_SCENE_FIELDS:
            if before_scenes[sid].get(field) != after_scenes[sid].get(field):
                raise ValueError(f'Repair scope violation: medical field {field} in scene {sid} is locked')
    storyboard = Storyboard.model_validate(after_data)
    validate_anatomy_subjects(storyboard)
    if style_a_active(root):
        validate_style_a_mascot_poses(storyboard)
    script_path = root / 'script/script.yaml'
    ledger_path = root / 'evidence/ledger.yaml'
    script = Script.model_validate(read_yaml(script_path)) if script_path.is_file() else None
    if script is not None:
        validate_hook_outro(
            script,
            storyboard,
            require_brand=script.format_profile == 'hook_outro_v1',
            allow_line_references=True,
        )
    if script is not None and ledger_path.is_file():
        resolve_citations(
            script,
            read_yaml(ledger_path),
            storyboard.scenes,
            strict_line_ids=script.format_profile == 'hook_outro_v1',
        )
    assets_path = root / 'assets/asset-manifest.yaml'
    manifest = load_asset_manifest(assets_path) if assets_path.is_file() else None
    if manifest is not None:
        validate_asset_manifest(root, manifest)
        manifest_paths = {PurePosixPath(a.path).as_posix() for a in manifest.assets}
        before_refs = {
            PurePosixPath(ref['path']).as_posix()
            for scene in before_data.get('scenes', [])
            if isinstance(scene, Mapping)
            for ref in (scene.get('visual_assets') or ())
            if isinstance(ref, Mapping) and isinstance(ref.get('path'), str)
        }
        after_refs = {
            PurePosixPath(ref.path).as_posix()
            for s in storyboard.scenes
            for ref in s.visual_assets
        }
        orphaned = sorted((before_refs & manifest_paths) - after_refs)
        if orphaned:
            raise ValueError(f'visual asset is not referenced by storyboard: {orphaned[0]}')
    if (root / 'explainer/explainer.yaml').is_file():
        _validate_storyboard_explainer_bindings(root, storyboard)
    if script is not None:
        validate_estimated_layout(project, script, storyboard, manifest)
    return before_data, after_data


def _check_asset_manifest_repair(
    root: Path,
    before_raw: bytes | None,
    after_raw: bytes | None,
    before_sb: Mapping[str, Any],
    after_sb: Mapping[str, Any],
    allowed_scenes: set[str],
) -> None:
    if before_raw == after_raw:
        return
    if before_raw is None or after_raw is None:
        raise ValueError('Repair scope violation: product target is locked')
    before_manifest = AssetManifest.model_validate(yaml.safe_load(before_raw))
    after_manifest = AssetManifest.model_validate(yaml.safe_load(after_raw))
    validate_asset_manifest(root, after_manifest)
    before_by_path = {asset.path: asset for asset in before_manifest.assets}
    after_by_path = {asset.path: asset for asset in after_manifest.assets}
    for path, asset in before_by_path.items():
        if asset.semantic or asset.storyboard_role == 'brand':
            updated = after_by_path.get(path)
            if (updated is None
                    or updated.sha256 != asset.sha256
                    or updated.semantic != asset.semantic
                    or updated.storyboard_role != asset.storyboard_role):
                msg = ('Repair scope violation: medical artifact is locked'
                       if asset.semantic else 'Repair scope violation: product target is locked')
                raise ValueError(msg)
    refs_before = _scene_asset_refs(before_sb)
    refs_after = _scene_asset_refs(after_sb)
    for path in before_by_path.keys() | after_by_path.keys():
        if before_by_path.get(path) == after_by_path.get(path):
            continue
        updated = after_by_path.get(path)
        if updated is not None and (updated.semantic or updated.storyboard_role == 'brand'):
            raise ValueError('Repair scope violation: product target is locked')
        referencing = refs_before.get(path, set()) | refs_after.get(path, set())
        if not allowed_scenes or not referencing or not referencing.issubset(allowed_scenes):
            raise ValueError('Repair scope violation: product target is locked')


def _check_clip_plan_repair(
    root: Path,
    cp_key: str,
    before_raw: bytes | None,
    after_raw: bytes | None,
    before_sb: Mapping[str, Any],
    after_sb: Mapping[str, Any],
    fixable_issues: Sequence[Mapping[str, Any]],
    allowed_scenes: set[str],
    edits_by_path: Mapping[str, list[dict]],
) -> None:
    if before_raw == after_raw:
        return
    if before_raw is None or after_raw is None:
        raise ValueError('Repair scope violation: product target is locked')
    before_cp = ClipPlan.model_validate(yaml.safe_load(before_raw))
    after_cp = ClipPlan.model_validate(yaml.safe_load(after_raw))
    if cp_key in edits_by_path:
        scoped_review.check_edits({cp_key: before_raw}, {cp_key: after_raw}, edits_by_path[cp_key])
    else:
        explicit_clips = {
            cid for item in fixable_issues for cid in _CLIP_ID_RE.findall(str(item.get('at', '')))
        }
        sb_before = Storyboard.model_validate(before_sb) if before_sb else None
        sb_after = Storyboard.model_validate(after_sb) if after_sb else None
        allowed_clips = set(explicit_clips)
        for plan, sb in ((before_cp, sb_before), (after_cp, sb_after)):
            if sb is None:
                continue
            for clip in plan.clips:
                try:
                    scenes = resolve_clip_scenes(clip, sb)
                except ValueError:
                    allowed_clips.add(clip.id)
                    continue
                if any(scene.id in allowed_scenes for scene in scenes):
                    allowed_clips.add(clip.id)
        if not allowed_clips:
            raise ValueError('Repair scope violation: product target is locked')
        scoped_review.check_nodes(before_raw, after_raw, allowed_clips, 'clips')
    if after_sb:
        sb_after = Storyboard.model_validate(after_sb)
        if sb_after.format_profile == 'youtube_long':
            ledger = read_yaml(root / 'evidence/ledger.yaml')
            claims = {
                c.id: c
                for c in (EvidenceClaim.model_validate(item) for item in ledger.get('claims', []))
            }
            validate_clip_plan(after_cp, sb_after, claims)


def _check_voice_prep_repair(
    root: Path,
    vp_key: str,
    before_raw: bytes | None,
    after_raw: bytes | None,
    fixable_issues: Sequence[Mapping[str, Any]],
    edits_by_path: Mapping[str, list[dict]],
) -> None:
    if before_raw == after_raw:
        return
    if before_raw is None or after_raw is None:
        raise ValueError('Repair scope violation: product target is locked')
    has_audio_issue = any(
        item.get('criterion') == 'am_thanh_phu_de' or _is_audio_related_at(str(item.get('at', '')))
        for item in fixable_issues
    )
    if not has_audio_issue and vp_key not in edits_by_path:
        raise ValueError('Repair scope violation: product target is locked')
    if vp_key in edits_by_path and not any(
        not item.get('edits') and (item.get('criterion') == 'am_thanh_phu_de'
                                   or _is_audio_related_at(str(item.get('at', ''))))
        for item in fixable_issues
    ):
        scoped_review.check_edits({vp_key: before_raw}, {vp_key: after_raw}, edits_by_path[vp_key])
    sheet = VoicePrepSheet.model_validate(yaml.safe_load(after_raw))
    expected_hash = canonical_json_hash(read_yaml(root / 'script/script.yaml'))
    if sheet.script_hash != expected_hash:
        raise ValueError('script/voice-prep.yaml script_hash không khớp script/script.yaml')


def _check_posts_repairs(
    root: Path,
    rev_prefix: str,
    before: Mapping[str, bytes],
    after: Mapping[str, bytes],
    fixable_issues: Sequence[Mapping[str, Any]],
    edits_by_path: Mapping[str, list[dict]],
) -> None:
    from healthvideo.workflows.gate_review import check_revision_posts

    posts_key = f'{rev_prefix}/posts/posts.yaml'
    if before.get(posts_key) != after.get(posts_key):
        before_raw, after_raw = before.get(posts_key), after.get(posts_key)
        if before_raw is None or after_raw is None:
            raise ValueError('Repair scope violation: product target is locked')
        has_posts_issue = any(
            item.get('criterion') == 'bai_dang' or 'posts' in str(item.get('at', '')).lower()
            for item in fixable_issues
        )
        if not has_posts_issue and posts_key not in edits_by_path:
            raise ValueError('Repair scope violation: product target is locked')
        if posts_key in edits_by_path and not any(
            not item.get('edits') and (item.get('criterion') == 'bai_dang'
                                       or 'posts' in str(item.get('at', '')).lower())
            for item in fixable_issues
        ):
            scoped_review.check_edits(
                {posts_key: before_raw}, {posts_key: after_raw}, edits_by_path[posts_key]
            )
        before_posts = yaml.safe_load(before_raw)
        is_postset = isinstance(before_posts, Mapping) and bool(set(before_posts) & _POSTSET_KEYS)
        if is_postset:
            errors = check_revision_posts(root)
            if errors:
                raise ValueError('; '.join(errors))

    sp_key = f'{rev_prefix}/posts/shorts-plan.yaml'
    if before.get(sp_key) != after.get(sp_key):
        before_raw, after_raw = before.get(sp_key), after.get(sp_key)
        if before_raw is None or after_raw is None:
            raise ValueError('Repair scope violation: product target is locked')
        before_sp = ShortsPlan.model_validate(yaml.safe_load(before_raw))
        after_sp = ShortsPlan.model_validate(yaml.safe_load(after_raw))
        has_shorts_issue = any(_is_shorts_related_issue(item) for item in fixable_issues)
        if sp_key in edits_by_path and not any(
            not item.get('edits') and _is_shorts_related_issue(item) for item in fixable_issues
        ):
            scoped_review.check_edits(
                {sp_key: before_raw}, {sp_key: after_raw}, edits_by_path[sp_key]
            )
        elif not has_shorts_issue and sp_key not in edits_by_path:
            expected_rev_hash = _shorts_revision_hash(root)
            if after_sp != before_sp.model_copy(update={'revision_hash': expected_rev_hash}):
                raise ValueError('Repair scope violation: product target is locked')


def _check_video_src_repairs(
    repo: Path,
    before: Mapping[str, bytes],
    after: Mapping[str, bytes],
    before_sb: Mapping[str, Any],
    after_sb: Mapping[str, Any],
    fixable_issues: Sequence[Mapping[str, Any]],
    edits_by_path: Mapping[str, list[dict]],
) -> None:
    video_keys = {k for k in (before.keys() | after.keys()) if k.startswith('video/src/')}
    for key in video_keys:
        if (key in before) != (key in after):
            raise ValueError('Repair scope violation: product target is locked')
    subjects_by_scene: dict[str, str] = {}
    for sb_data in (before_sb, after_sb):
        if not isinstance(sb_data, Mapping):
            continue
        for scene in sb_data.get('scenes', []):
            if (isinstance(scene, Mapping) and scene.get('id')
                    and isinstance(scene.get('anatomy'), Mapping)
                    and scene['anatomy'].get('subject')):
                subjects_by_scene[str(scene['id'])] = str(scene['anatomy']['subject'])
    allowed_empty_edit_files: set[str] = set()
    for item in fixable_issues:
        if item.get('edits') or item.get('criterion') not in _VIDEO_VISUAL_CRITERIA:
            continue
        allowed_empty_edit_files.update(_DISPLAY_OUTRO_FILES)
        scene_ids = _allowed_scene_ids([item])
        subjects = {subjects_by_scene[sid] for sid in scene_ids if sid in subjects_by_scene}
        allowed_empty_edit_files.update(_anatomy_component_paths(repo, subjects))
    for key in video_keys:
        if before[key] == after[key]:
            continue
        if key in edits_by_path:
            scoped_review.check_edits({key: before[key]}, {key: after[key]}, edits_by_path[key])
        elif key not in allowed_empty_edit_files:
            raise ValueError('Repair scope violation: product target is locked')


def _revise_product_guidance_brief(repo: Path, slug: str, active_revision: str) -> str:
    """Return active Coordinator brief targeting ``revise_product`` for this revision, if any."""
    path = repo / 'topics/logs' / slug / 'leader-guidance.yaml'
    if not path.is_file():
        return ''
    try:
        data = read_yaml(path)
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return ''
    if not isinstance(data, Mapping):
        return ''
    if str(data.get('revision') or '') != active_revision or str(data.get('step') or '') != 'revise_product':
        return ''
    return str(data.get('brief') or '').strip()


def check_repair(project: Path, before: dict[str, bytes]) -> None:
    """Verify surgical Station 12 repair stayed strictly within permitted product targets."""
    root = _root(project)
    layout = resolve_project_layout(project)
    repo = project.parent.parent
    guidance_brief = _revise_product_guidance_brief(repo, project.name, layout.manifest.active_revision)
    rounds = _cycle(root)
    if not rounds and not guidance_brief:
        return
    if rounds:
        latest = rounds[-1]
    else:
        all_rounds = _log(root)['rounds']
        latest = all_rounds[-1] if all_rounds else {'issues': []}
    fixable_issues = [item for item in latest.get('issues', []) if item.get('fixable')]
    if guidance_brief:
        fixable_issues.append({
            'at': guidance_brief,
            'criterion': 'mo_ket',
            'fixable': True,
            'edits': [],
        })
    rev_prefix = root.relative_to(repo).as_posix()
    edits_by_path = _check_edit_targets(fixable_issues, rev_prefix)
    after = repair_files(project)

    for key, raw in after.items():
        if key.startswith(rev_prefix + '/') and key.endswith('.yaml') and before.get(key) != raw:
            validate_agent_text(yaml.safe_load(raw), key)

    for key in before.keys() | after.keys():
        if not key.startswith(rev_prefix + '/'):
            continue
        rel = key[len(rev_prefix) + 1:]
        if _is_locked_medical_rel(rel):
            if before.get(key) != after.get(key):
                raise ValueError('Repair scope violation: medical artifact is locked')
        elif (rel not in _EDITABLE_REV_YAMLS and before.get(key) != after.get(key)) or (
            rel in _EDITABLE_REV_YAMLS and (key in before) != (key in after)
        ):
            raise ValueError('Repair scope violation: product target is locked')

    allowed_scenes = _allowed_scene_ids(latest.get('issues', []))
    if guidance_brief:
        allowed_scenes |= set(_SCENE_ID_RE.findall(guidance_brief))
    sb_key = f'{rev_prefix}/storyboard/storyboard.yaml'
    before_sb, after_sb = _check_storyboard_repair(
        project, root, before.get(sb_key), after.get(sb_key), allowed_scenes
    )
    am_key = f'{rev_prefix}/assets/asset-manifest.yaml'
    _check_asset_manifest_repair(
        root, before.get(am_key), after.get(am_key), before_sb, after_sb, allowed_scenes
    )
    cp_key = f'{rev_prefix}/script/clip-plan.yaml'
    _check_clip_plan_repair(
        root, cp_key, before.get(cp_key), after.get(cp_key),
        before_sb, after_sb, fixable_issues, allowed_scenes, edits_by_path,
    )
    vp_key = f'{rev_prefix}/script/voice-prep.yaml'
    _check_voice_prep_repair(
        root, vp_key, before.get(vp_key), after.get(vp_key), fixable_issues, edits_by_path
    )
    _check_posts_repairs(root, rev_prefix, before, after, fixable_issues, edits_by_path)
    _check_video_src_repairs(repo, before, after, before_sb, after_sb, fixable_issues, edits_by_path)


def finalize_product_repair(project: Path, before: dict[str, bytes]) -> None:
    """Sync derived presentation hashes after surgical Station 12 repairs pass check_repair."""
    from healthvideo.workflows.gate_review import (
        MEDICAL_APPROVAL_ARTIFACT,
        hash_reviewed_artifacts,
        medical_reviewed_paths,
    )

    root = _root(project)
    repo = project.parent.parent
    rev_prefix = root.relative_to(repo).as_posix()
    sb_path = root / 'storyboard/storyboard.yaml'
    sb_changed = (
        sb_path.is_file()
        and before.get(f'{rev_prefix}/storyboard/storyboard.yaml') != sb_path.read_bytes()
    )
    shorts_path = root / 'posts/shorts-plan.yaml'
    if sb_changed and shorts_path.is_file():
        plan = ShortsPlan.model_validate(read_yaml(shorts_path))
        new_rev_hash = _shorts_revision_hash(root)
        if plan.revision_hash != new_rev_hash:
            updated_plan = plan.model_copy(update={'revision_hash': new_rev_hash})
            write_yaml_atomic(shorts_path, updated_plan.model_dump(mode='json'))

    changed_presentation: list[str] = []
    for rel in sorted(_PRESENTATION_APPROVAL_KEYS):
        path = root / rel
        current_raw = path.read_bytes() if path.is_file() else None
        if before.get(f'{rev_prefix}/{rel}') != current_raw:
            changed_presentation.append(rel)

    approval_path = root / MEDICAL_APPROVAL_ARTIFACT
    if not (approval_path.is_file() and changed_presentation):
        return
    approval = GateApprovalRecord.model_validate(read_yaml(approval_path))
    if approval.kind is not GateKind.MEDICAL:
        raise ValueError('reviews/medical-approval.yaml phải là bản duyệt y khoa')
    current_hashes = hash_reviewed_artifacts(medical_reviewed_paths(root))
    for key in approval.artifact_hashes.keys() | current_hashes.keys():
        if key in _PRESENTATION_APPROVAL_KEYS:
            continue
        if approval.artifact_hashes.get(key) != current_hashes.get(key):
            raise ValueError(f'Khóa y khoa lõi không khớp bản duyệt gốc: {key}')
    old_hashes = dict(approval.artifact_hashes)
    new_hashes = dict(approval.artifact_hashes)
    for rel in _PRESENTATION_APPROVAL_KEYS:
        if rel in current_hashes:
            new_hashes[rel] = current_hashes[rel]
        elif not (root / rel).is_file():
            new_hashes.pop(rel, None)
    write_yaml_atomic(
        approval_path,
        approval.model_copy(update={'artifact_hashes': new_hashes}).model_dump(mode='json'),
    )
    sync_log_path = root / MEDICAL_HASH_SYNC_LOG
    existing = read_yaml(sync_log_path) if sync_log_path.is_file() else {}
    entries = list(existing.get('entries', []))
    rounds = _cycle(root)
    entries.append({
        'at': datetime.now(UTC).isoformat(),
        'round': rounds[-1]['round'] if rounds else None,
        'allowed_scenes': sorted(_allowed_scene_ids(rounds[-1]['issues'])) if rounds else [],
        'changed_artifacts': changed_presentation,
        'updated_hashes': {
            rel: {'before': old_hashes.get(rel), 'after': new_hashes.get(rel)}
            for rel in changed_presentation
        },
    })
    write_yaml_atomic(sync_log_path, {'version': 1, 'entries': entries})


def mark_fix_attempted(project: Path) -> None:
    root = _root(project)
    log = _log(root)
    if not log['rounds']:
        return
    log['rounds'][-1]['fix_attempted'] = True
    write_yaml_atomic(root / LOG, {'version': 1, **log})


def mark_submitted(artifact_root: Path) -> None:
    """A new submission starts a new review cycle; the latest score stays visible."""
    log = _log(artifact_root)
    for old_round in log['rounds'][:-1]:
        old_round.pop('snapshot', None)
    log['submitted'] = len(log['rounds'])
    write_yaml_atomic(artifact_root / LOG, {'version': 1, **log})
    (artifact_root / PENDING).unlink(missing_ok=True)


def revision_notes(project: Path) -> str:
    """Render the fixable issues of the latest round as instructions for the fixer."""
    root = _root(project)
    layout = resolve_project_layout(project)
    repo = project.parent.parent
    guidance_brief = _revise_product_guidance_brief(repo, project.name, layout.manifest.active_revision)
    rounds = _cycle(root)
    if not rounds and not guidance_brief:
        return ''
    if not rounds:
        all_rounds = _log(root)['rounds']
        latest = all_rounds[-1] if all_rounds else {'round': 0, 'summary': '', 'issues': []}
        allowed_scenes = sorted(_allowed_scene_ids(latest.get('issues', [])) | set(_SCENE_ID_RE.findall(guidance_brief)))
        rows = [f'- Yêu cầu điều phối từ Leader: {guidance_brief}']
        if allowed_scenes:
            rows.append(
                f"Cảnh được phép sửa trong storyboard/assets: {', '.join(allowed_scenes)}. "
                'Giữ nguyên tuyệt đối các trường y khoa và xuất xứ '
                '(id, script_line_id, narration, claim_id, chapter_id, source_marker, source_card, evidence_highlight), '
                'không sửa script.yaml, ledger.yaml, explainer.yaml hay outline.yaml.'
            )
        return '\n'.join(rows)
    latest = rounds[-1]
    style_required = style_a_active(root)
    active_issues = [
        item for item in latest['issues']
        if item['fixable'] and (style_required or item['criterion'] != STYLE_CRITERION)
    ]
    rows = [f"- {item['at']} ({CRITERIA[item['criterion']]}): {item['problem']} "
            f"Hướng sửa: {item['fix']}"
            for item in active_issues]
    if len(latest.get('decisions', [])) > MAX_DECISIONS:
        rows.append('Còn quá 5 điểm khó: tự xử lý các lỗi thuộc thẩm quyền; '
                    'không tự quyết điểm cần bác sĩ. Xếp điểm nặng nhất trước.')
    allowed_scenes = sorted(_allowed_scene_ids(active_issues) | (
        set(_SCENE_ID_RE.findall(guidance_brief)) if guidance_brief else set()
    ))
    if allowed_scenes:
        rows.append(
            f"Cảnh được phép sửa trong storyboard/assets: {', '.join(allowed_scenes)}. "
            'Giữ nguyên tuyệt đối các trường y khoa và xuất xứ '
            '(id, script_line_id, narration, claim_id, chapter_id, source_marker, source_card, evidence_highlight), '
            'không sửa script.yaml, ledger.yaml, explainer.yaml hay outline.yaml.'
        )
    else:
        rows.append(
            'Không có cảnh storyboard nào được phép sửa. '
            'Giữ nguyên tuyệt đối các trường và tài liệu y khoa '
            '(script.yaml, ledger.yaml, explainer.yaml, outline.yaml, license-ledger.yaml).'
        )
    return '\n'.join([f"Người duyệt sản phẩm chấm lần {latest['round']}: {latest['summary']}", *rows])


def style_score(root: Path) -> dict | None:
    """Return the latest PYH style score from Station 12 if present."""
    rounds = _log(root)['rounds']
    if not rounds:
        return None
    latest = rounds[-1]
    scores = latest.get('scores') or {}
    if STYLE_CRITERION not in scores:
        return None
    value = int(scores[STYLE_CRITERION])
    return {
        'key': STYLE_CRITERION,
        'label': CRITERIA[STYLE_CRITERION],
        'score': value,
        'pass_score': PASS_SCORE,
        'passed': value >= PASS_SCORE,
        'round': latest.get('round'),
    }


def review_view(root: Path) -> dict | None:
    """Latest score in display form for the app and the video packet."""
    rounds = _log(root)['rounds']
    if not rounds:
        return None
    latest = rounds[-1]
    return {
        'title': 'Người duyệt sản phẩm',
        'round': latest['round'],
        'passed': latest['passed'],
        'summary': latest.get('overall') or latest['summary'],
        'scores': [
            {'key': key, 'label': label, 'score': latest['scores'][key]}
            for key, label in CRITERIA.items()
            if key in latest['scores']
        ],
        'style_score': style_score(root),
        'issues': [{**item, 'line': item['at'], 'criterion': CRITERIA[item['criterion']],
                    'fix': item['fix'] + ('' if item['fixable'] else ' (cần bác sĩ mở cổng y khoa)')}
                   for item in latest['issues']],
        'pass_score': PASS_SCORE,
    }
