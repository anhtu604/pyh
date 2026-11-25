"""Import and probe externally produced revisions; never issue approvals or critic scores."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import ValidationError

from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.posts import PostSet
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.script import Script
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)
from healthvideo.storage.revision_lock import revision_lock
from healthvideo.storage.revisions import create_revision
from healthvideo.tts import pronunciation

EXTERNAL = 'workflow/external.yaml'
CLIP_ID = re.compile(r'CL[0-9]{2}')


def is_external(revision: Path) -> bool:
    path = revision / EXTERNAL
    return path.is_file() and read_yaml(path).get('production_mode') == 'external'


def _load(root: Path, relative: str, model):
    try:
        return model.model_validate(read_yaml(root / relative))
    except (OSError, ValueError, TypeError, ValidationError, yaml.YAMLError) as exc:
        raise ValueError(f'{relative}: dữ liệu không hợp lệ: {exc}') from exc


def validate_import(root: Path, *, importing: bool = False) -> tuple[Script, dict, PostSet, dict[str, str]]:
    """Validate schemas and explicit references; never guess missing medical support."""
    if not root.is_dir():
        raise ValueError(f'{root}: thiếu thư mục nhập')
    if (root / 'evidence/unresolved-claims.yaml').is_file():
        raise ValueError('evidence/unresolved-claims.yaml: còn claim thiếu nguồn; cần xử lý trước khi nhập')
    for path in root.rglob('*'):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise ValueError(f'{path}: không nhận liên kết thư mục/tệp')
        if importing and path.is_file() and 'approval' in path.name.lower():
            raise ValueError(f'{path}: không được nhập bản duyệt')
    script = _load(root, 'script/script.yaml', Script)
    if not script.lines or len({line.id for line in script.lines}) != len(script.lines):
        raise ValueError('script/script.yaml.lines: cần dòng lời có id duy nhất')
    for line in script.lines:
        if not line.id.strip() or not line.text.strip():
            raise ValueError(f'script/script.yaml.lines.{line.id}: thiếu id/text')
    try:
        ledger = read_yaml(root / 'evidence/ledger.yaml')
        claims = [EvidenceClaim.model_validate(c) for c in ledger['claims']]
        records = [SourceRecord.model_validate(r) for r in ledger['records']]
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        raise ValueError(f'evidence/ledger.yaml: claims/records không hợp lệ: {exc}') from exc
    claim_ids, source_ids = {c.id for c in claims}, {r.id for r in records}
    if not claims:
        raise ValueError('evidence/ledger.yaml.claims: cần dữ liệu; không tự gán nguồn')
    if len(claim_ids) != len(claims) or len(source_ids) != len(records):
        raise ValueError('evidence/ledger.yaml: trùng id claim hoặc nguồn')
    for claim in claims:
        if not claim.sources:
            raise ValueError(f'evidence/ledger.yaml.claims.{claim.id}.sources: thiếu nguồn')
        missing = set(claim.sources) - source_ids
        if missing:
            raise ValueError(f'evidence/ledger.yaml.claims.{claim.id}.sources: thiếu {sorted(missing)}')
    for record in records:
        if not record.id.strip() or not record.title.strip():
            raise ValueError(f'evidence/ledger.yaml.records.{record.id}: thiếu id/title')
    from healthvideo.evidence.fulltext import validate_support_records

    try:
        validate_support_records(claims, records)
    except ValueError as exc:
        raise ValueError(f'evidence/ledger.yaml.support: {exc}') from exc
    for line in script.lines:
        if line.claim_id and line.claim_id not in claim_ids:
            raise ValueError(f'script/script.yaml.lines.{line.id}.claim_id: thiếu {line.claim_id}')
    from healthvideo.workflows.gate_review import check_revision_posts

    posts = _load(root, 'posts/posts.yaml', PostSet)
    errors = check_revision_posts(root)
    if errors:
        raise ValueError('posts/posts.yaml: ' + '; '.join(errors))
    clips = {}
    for path in sorted((root / 'renders/clips').glob('*.mp4')):
        if not CLIP_ID.fullmatch(path.stem):
            raise ValueError(f'{path}: id clip phải là CLxx')
        clips[path.stem] = f'clips/{path.name}'
    if not 1 <= len(clips) <= 6:
        raise ValueError('renders/clips: cần 1–6 clip CLxx.mp4')
    if set(posts.clip_captions) != set(clips):
        raise ValueError('posts/posts.yaml.clip_captions: phải khớp đủ clip nhập')
    for relative in ('renders/video.mp4', *(f'renders/{p}' for p in clips.values())):
        if not (root / relative).is_file() or not (root / relative).stat().st_size:
            raise ValueError(f'{relative}: thiếu hoặc tệp rỗng')
    if posts.thumbnail is not None:
        for name in ('thumbnail.png', 'thumbnail-background.png', 'license-ledger.yaml'):
            if not (root / 'posts' / name).is_file():
                raise ValueError(f'posts/{name}: thiếu tài sản thumbnail')
    return script, ledger, posts, clips


def import_revision(project_dir: Path, source: Path, *, reason: str,
                    now: datetime | None = None) -> str:
    """Reuse revision creation with a staged replacement and one manifest switch."""
    if not reason.strip():
        raise ValueError('reason: cần lý do nhập bản dựng ngoài')
    source = source.resolve()
    if source.is_relative_to(project_dir.resolve()) or project_dir.resolve().is_relative_to(source):
        raise ValueError('Thư mục nhập phải nằm ngoài project')
    validate_import(source, importing=True)
    with revision_lock(project_dir):
        def prepare(staging: Path) -> None:
            for name in ('topic', 'author', 'evidence', 'explainer', 'script', 'storyboard', 'assets'):
                target = staging / name
                if target.exists():
                    shutil.rmtree(target)
            for name in ('script', 'evidence', 'posts'):
                shutil.copytree(source / name, staging / name)
            (staging / 'renders/clips').mkdir(parents=True)
            shutil.copy2(source / 'renders/video.mp4', staging / 'renders/video.mp4')
            for clip in (source / 'renders/clips').glob('*.mp4'):
                shutil.copy2(clip, staging / 'renders/clips' / clip.name)
            lexicon = source / 'profiles/pronunciation.vi.yaml'
            if not lexicon.is_file():
                lexicon = pronunciation.PRONUNCIATION_PROFILE_PATH
            pronunciation.load_pronunciation_lexicon(lexicon)
            (staging / 'profiles').mkdir()
            shutil.copy2(lexicon, staging / 'profiles/pronunciation.vi.yaml')
            write_yaml_atomic(staging / EXTERNAL, {'production_mode': 'external', 'schema_version': '1.0'})
            validate_import(staging, importing=True)

        def activate(project: ProjectManifestV2) -> ProjectManifestV2:
            # A new revision starts with a fresh draft, not the old revision's approvals.
            draft = project.model_copy(update={'state': WorkflowState.DRAFT_READY,
                                               'side_state': None, 'artifact_hashes': {}})
            return transition_v2(draft, WorkflowState.AWAITING_MEDICAL_REVIEW, TransitionContext(
                active_revision=draft.active_revision, current_input_hash=canonical_json_hash({'external': reason}),
                validated_artifacts=frozenset({'script/script.yaml', 'evidence/ledger.yaml', EXTERNAL}),
                external_import=True,
            ))

        return create_revision(project_dir, reason, now=now or datetime.now().astimezone(),
                               prepare=prepare, activate=activate)


def probe_media(path: Path, *, vertical: bool) -> dict:
    """ffprobe checks the actual imported streams, with the existing 60–180s clip bounds."""
    from healthvideo.domain.clip_plan import CLIP_MAX_FRAMES, CLIP_MIN_FRAMES, FPS

    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                                 '-of', 'json', str(path)], capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f'{path}: không chạy được ffprobe: {exc}') from exc
    if result.returncode:
        raise ValueError(f'{path}: ffprobe không đọc được video: {result.stderr[:300]}')
    try:
        data = json.loads(result.stdout)
        video = next(s for s in data['streams'] if s.get('codec_type') == 'video')
        audio = next(s for s in data['streams'] if s.get('codec_type') == 'audio')
        duration = float(video.get('duration', data['format']['duration']))
        ratio = video['width'] / video['height']
        sar = video.get('sample_aspect_ratio', '1:1')
        if sar not in ('N/A', '0:1'):
            a, b = map(float, sar.split(':'))
            ratio *= a / b
        rotation = float(video.get('tags', {}).get('rotate', 0))
        for side_data in video.get('side_data_list', []):
            if 'rotation' in side_data:
                rotation = float(side_data['rotation'])
        if abs(rotation) % 180 == 90:
            ratio = 1 / ratio
        expected = 9 / 16 if vertical else 16 / 9
        low, high = (CLIP_MIN_FRAMES / FPS, CLIP_MAX_FRAMES / FPS) if vertical else (600, 1500)
        if abs(ratio - expected) > 0.01 or not low <= duration <= high:
            raise ValueError(f'cần tỷ lệ {"9:16" if vertical else "16:9"}, thời lượng {low}–{high}s')
        if int(audio.get('channels', 0)) < 1:
            raise ValueError('thiếu kênh tiếng')
    except (KeyError, ValueError, StopIteration, ZeroDivisionError) as exc:
        raise ValueError(f'{path}: video/tiếng/thời lượng không hợp lệ: {exc}') from exc
    return {'duration_seconds': duration, 'width': video['width'], 'height': video['height'],
            'audio_channels': audio['channels'], 'sha256': sha256_file(path)}


def produce_external(project_dir: Path, *, hold: bool = False, dry_run: bool = False) -> Path:
    from healthvideo.render.run import PRODUCTION_ARTIFACT
    from healthvideo.workflows import product_review
    from healthvideo.workflows.gate_review import (
        hash_reviewed_artifacts,
        medical_reviewed_paths,
    )
    from healthvideo.workflows.produce import (
        _ensure_v2_medical_approval_current,
        submit_video,
    )

    project = ProjectManifestV2.model_validate(read_yaml(project_dir / 'project.yaml'))
    revision = project_dir / 'revisions' / project.active_revision
    if project.state not in {WorkflowState.MEDICALLY_APPROVED, WorkflowState.PRODUCTION_IN_PROGRESS}:
        raise ValueError('Bản dựng ngoài cần duyệt y khoa còn hiệu lực trước sản xuất')
    _ensure_v2_medical_approval_current(revision)
    _, _, _, clips = validate_import(revision)
    metadata = {'video.mp4': probe_media(revision / 'renders/video.mp4', vertical=False)}
    metadata.update({p: probe_media(revision / 'renders' / p, vertical=True) for p in clips.values()})
    if dry_run:
        return revision / 'renders/video.mp4'
    input_hash = canonical_json_hash({'medical': hash_reviewed_artifacts(medical_reviewed_paths(revision)),
                                      'media': metadata})
    manifest = {'schema_version': '1.0', 'production_mode': 'external', 'input_hash': input_hash,
                'clips': clips, 'media': metadata}
    render_path = revision / 'renders/render-manifest.json'
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    # Keep identical bytes on retry: Station 12 binds this manifest.
    if not render_path.is_file() or render_path.read_text(encoding='utf-8') != encoded:
        render_path.write_text(encoded, encoding='utf-8')
    qa = {'status': 'passed', 'input_hash': input_hash,
          'checks': {'readable_streams': True, 'aspect_ratio': True, 'audio': True, 'duration': True},
          'scope': 'Chỉ kiểm kỹ thuật bằng ffprobe; critic và bác sĩ cần kiểm nội dung, nghe tiếng.'}
    (revision / 'reviews').mkdir(exist_ok=True)
    (revision / 'reviews/video-qa.json').write_text(json.dumps(qa, ensure_ascii=False), encoding='utf-8')
    if project.state is WorkflowState.MEDICALLY_APPROVED:
        project = transition_v2(project, WorkflowState.PRODUCTION_IN_PROGRESS, TransitionContext(
            active_revision=project.active_revision, current_input_hash=input_hash,
            validated_artifacts=frozenset({'reviews/medical-approval.yaml'})))
    project = project.model_copy(update={'artifact_hashes': {**project.artifact_hashes,
                                                           PRODUCTION_ARTIFACT: input_hash}})
    write_yaml_atomic(project_dir / 'project.yaml', project.model_dump(mode='json'))
    product_review.hold(revision, input_hash)
    if not hold:
        submit_video(project_dir)  # Still requires both real critic reports.
    return revision / 'renders/video.mp4'


def validate_render(revision: Path) -> None:
    """Bind ffprobe QA to every current MP4, including inventory and approval input."""
    from healthvideo.workflows.gate_review import (
        hash_reviewed_artifacts,
        medical_reviewed_paths,
    )

    _, _, _, clips = validate_import(revision)
    manifest = json.loads((revision / 'renders/render-manifest.json').read_text(encoding='utf-8'))
    qa = json.loads((revision / 'reviews/video-qa.json').read_text(encoding='utf-8'))
    if manifest.get('clips') != clips or manifest.get('production_mode') != 'external':
        raise ValueError('render-manifest.json: danh sách clip/production_mode không khớp')
    metadata = manifest.get('media', {})
    expected = {'video.mp4', *clips.values()}
    if set(metadata) != expected:
        raise ValueError('render-manifest.json.media: thiếu video/clip')
    for relative, item in metadata.items():
        if item.get('sha256') != sha256_file(revision / 'renders' / relative):
            raise ValueError(f'renders/{relative}: byte video đã đổi sau QA')
    input_hash = canonical_json_hash({'medical': hash_reviewed_artifacts(medical_reviewed_paths(revision)),
                                     'media': metadata})
    if manifest.get('input_hash') != input_hash or qa.get('input_hash') != input_hash:
        raise ValueError('video-qa.json: input_hash không khớp lời/nguồn/video hiện hành')
    required = ('readable_streams', 'aspect_ratio', 'audio', 'duration')
    if any(qa.get('checks', {}).get(key) is not True for key in required):
        raise ValueError('video-qa.json: thiếu kiểm kỹ thuật bản dựng ngoài')
