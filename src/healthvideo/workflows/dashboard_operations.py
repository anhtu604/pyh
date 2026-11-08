"""Read-only recovery previews and explicit local app operations.

Retry releases the runner's existing hold; it never starts a second worker.
"""

from __future__ import annotations

import importlib
import re
import threading
from datetime import datetime
from pathlib import Path

from healthvideo.agents import RUNNING_MARKER
from healthvideo.domain.asset_manifest import (
    load_asset_manifest,
    validate_asset_manifest,
)
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.storage.queue import add_to_queue, load_queue
from healthvideo.workflows import factory
from healthvideo.workflows.gate_review import reopen_gate
from healthvideo.workflows.review import approval_is_stale, latest_approval
from healthvideo.workflows.runner import next_step

_MUTATION_LOCK = threading.RLock()


def inside(base: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError('Đường dẫn nằm ngoài thư mục cho phép.')
    return resolved


def check_revision_paths(project: Path, revision: Path) -> None:
    """Validate delegated gate I/O before it can follow a nested junction."""
    inside(project, revision)
    for relative in (
        'assets', 'script', 'storyboard', 'evidence', 'topic', 'posts', 'workflow', 'renders',
        'reviews', 'reviews/medical', 'reviews/video', 'reviews/visual',
        'assets/asset-manifest.yaml', 'assets/library.yaml', 'assets/license-ledger.yaml',
        'script/script.yaml', 'script/outline.yaml', 'storyboard/storyboard.yaml',
        'storyboard/clip-plan.yaml', 'evidence/ledger.yaml',
        'reviews/medical-approval.yaml', 'reviews/video-approval.yaml',
        'reviews/imported-contact-sheet.png', 'reviews/imported-contact-sheet.yaml',
    ):
        inside(revision, revision / relative)
    manifest = revision / 'assets/asset-manifest.yaml'
    if manifest.is_file():
        for asset in load_asset_manifest(manifest).assets:
            inside(revision, revision / asset.path)


def project_layout(root: Path, slug: str):
    if not re.fullmatch(r'[a-z0-9-]{3,80}', slug):
        raise LookupError('Slug không hợp lệ.')
    project = inside(root, root / 'projects' / slug)
    if not (project / 'project.yaml').is_file():
        raise LookupError('Không có project này.')
    inside(project, project / 'project.yaml')
    layout = resolve_project_layout(project)
    inside(project, layout.artifact_root)
    return layout


def add_topic(root: Path, body: dict) -> dict:
    values = {key: body.get(key) for key in ('slug', 'title', 'question')}
    for key, value in values.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'Nhập {key}.')
        values[key] = value.strip()
    entry = QueueEntry(**values, doctor_note=body.get('doctor_note'), added=datetime.now().astimezone().date())
    with _MUTATION_LOCK:
        inside(root, root / 'topics/queue.yaml')
        add_to_queue(root, entry)
    return entry.model_dump(mode='json')


def _retry_api():
    try:
        return importlib.import_module('healthvideo.workflows.production_retry')
    except ModuleNotFoundError as exc:
        if exc.name != 'healthvideo.workflows.production_retry':
            raise
        return None


def project_operations(root: Path, slug: str) -> dict:
    layout = project_layout(root, slug)
    rev = layout.artifact_root
    script = rev / 'script/script.yaml'
    lines = read_yaml(inside(rev, script)).get('lines', []) if script.is_file() else []
    cache = inside(layout.project_dir, layout.project_dir / 'cache/tts')
    cached = sum(1 for p in cache.glob('*.wav') if p.is_file() and p.resolve().is_relative_to(cache))
    api = _retry_api()
    retry = api.retry_status(root, layout.project_dir, layout.manifest.state) if api else {
        'allowed': False, 'reason': 'API retry chưa được cài đặt.', 'kind': 'unavailable',
    }
    blocked = inside(root, root / 'topics/logs' / slug / 'blocked.txt')
    board = inside(rev, rev / 'storyboard/storyboard.yaml')
    scenes = read_yaml(board).get('scenes', []) if board.is_file() else []
    return {
        'slug': slug, 'revision': layout.manifest.active_revision,
        'state': layout.manifest.state.value, 'gate': factory.GATES.get(layout.manifest.state),
        'next_step': next_step(layout.manifest.state), 'retry_status': retry,
        'scenes': [{'id': s['id'], 'label': s.get('narration', '')[:100]} for s in scenes if s.get('visual') == 'whiteboard'],
        'blocked': blocked.read_text(encoding='utf-8')[:4000] if blocked.is_file() else '',
        'cache': {'files': cached, 'lines': len(lines), 'verified_hits': None, 'max_requests': len(lines),
                  'note': 'File cache chưa kiểm hash/giọng/provider; số yêu cầu tối đa cho một lượt TTS.'},
    }


def _editable(root: Path, slug: str, expected_revision: str):
    layout = project_layout(root, slug)
    if expected_revision != layout.manifest.active_revision:
        raise ValueError('Revision đã thay đổi; tải lại trước khi thao tác.')
    marker = inside(root, root / 'topics/logs' / slug / RUNNING_MARKER)
    # A blocked project is skipped by the factory loop, so it can be fixed while the factory runs.
    blocked = inside(root, root / 'topics/logs' / slug / 'blocked.txt').is_file()
    if marker.exists() or (factory.running_pid(root) is not None and not blocked):
        raise ValueError('Hãy dừng xưởng và chờ agent kết thúc trước khi thao tác.')
    check_revision_paths(layout.project_dir, layout.artifact_root)
    inside(root, root / 'profiles/doctor-feedback.yaml')
    return layout


def retry_project(root: Path, slug: str, *, expected_revision: str) -> dict:
    with _MUTATION_LOCK:
        layout = _editable(root, slug, expected_revision)
        if next_step(layout.manifest.state) is None:
            raise ValueError('Project không có bước có thể thử lại; giữ nguyên cổng duyệt.')
        # Validate local inputs before releasing the hold. No provider calls here.
        rev = layout.artifact_root
        for relative, model in (('script/script.yaml', Script), ('storyboard/storyboard.yaml', Storyboard)):
            path = inside(rev, rev / relative)
            if path.is_file():
                model.model_validate(read_yaml(path))
        manifest = inside(rev, rev / 'assets/asset-manifest.yaml')
        if manifest.is_file():
            validate_asset_manifest(rev, load_asset_manifest(manifest))
        approval = latest_approval(layout.project_dir, GateKind.MEDICAL)
        if approval is not None and approval_is_stale(layout.project_dir, layout.manifest, GateKind.MEDICAL):
            raise ValueError('Tệp đã duyệt y khoa đã đổi; bác sĩ phải mở lại cổng y khoa.')
        if next_step(layout.manifest.state) == 'produce':
            from healthvideo.workflows.produce import (
                _ensure_v2_medical_approval_current,
            )

            _ensure_v2_medical_approval_current(rev)
        api = _retry_api()
        if api is None:
            raise ValueError('API retry chưa sẵn sàng; chưa thay đổi trạng thái.')
        inside(root, root / 'topics/logs' / slug / 'production-retry.yaml')
        retry = api.retry_status(root, layout.project_dir, layout.manifest.state)
        if retry.get('kind') == 'validation' and not retry.get('allowed'):
            raise ValueError(retry.get('reason') or 'Sửa đầu vào trước khi thử lại.')
        api.clear_retry(root, slug)
        return project_operations(root, slug)


def reopen_project(root: Path, slug: str, *, expected_revision: str, reviewer: str,
                   reason: str, changed: list[str], limiter, pin: str = '') -> dict:
    from healthvideo.workflows.dashboard import pin_path, reviewer_name, verify_pin

    reviewer = reviewer_name() or reviewer
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError('Nhập tên bác sĩ xác nhận mở lại.')
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('Nhập lý do mở lại.')
    if not isinstance(changed, list) or not all(isinstance(p, str) for p in changed):
        raise ValueError('Danh sách tệp thay đổi không hợp lệ.')
    with _MUTATION_LOCK:
        layout = _editable(root, slug, expected_revision)
        pin_file = pin_path()
        if not pin_file.is_file():
            raise ValueError('Chưa đặt PIN; chạy healthvideo review set-pin một lần.')
        limiter.check(pin, lambda value: verify_pin(value, path=pin_file))
        record = reopen_gate(layout.project_dir, GateKind.MEDICAL, reviewer=reviewer.strip(),
                             reason=reason.strip(), changed=changed, resume_state=WorkflowState.DRAFT_READY,
                             now=datetime.now().astimezone())
        return record.model_dump(mode='json')


def get_route(server, parts: list[str], query: dict) -> dict | bytes | None:
    from healthvideo.workflows import asset_library as library

    if parts == ['api', 'chat']:
        from healthvideo.workflows import chat

        return {'messages': chat.load(server.root, query.get('slug', [None])[0] or None)[-100:]}
    if parts == ['api', 'topics']:
        return {'entries': [e.model_dump(mode='json') for e in load_queue(server.root)]}
    if len(parts) == 4 and parts[:2] == ['api', 'project'] and parts[3] == 'operations':
        return project_operations(server.root, parts[2])
    if parts == ['api', 'library']:
        return {'items': library.list_assets(server.root, slug=query.get('slug', [None])[0] or None,
                                            kind=query.get('kind', [None])[0] or None,
                                            query=query.get('query', [''])[0])}
    if len(parts) == 4 and parts[0] == 'media' and parts[2] == 'library':
        item, _ = library.resolve_asset(server.root, parts[3])
        if item['slug'] != parts[1]:
            raise LookupError('Ảnh không thuộc project này.')
        return library.preview_asset(server.root, parts[3])
    return None


def post_route(server, parts: list[str], body: dict) -> dict | None:
    if parts in (['api', 'chat'], ['api', 'chat', 'confirm']):
        from healthvideo.workflows import chat

        allowed = {'slug', 'id'} if parts[-1] == 'confirm' else {'slug', 'text', 'context'}
        if set(body) - allowed:
            raise ValueError('Trường chat không hợp lệ; không nhận PIN.')
        if parts[-1] == 'confirm':
            return chat.confirm(server.root, body.get('slug') or None, body.get('id'))
        return chat.post(server.root, body.get('slug') or None, body.get('text'), body.get('context', {}))
    if len(parts) == 3 and parts[:2] == ['api', 'library']:
        return _library_post(server, parts[2], body)
    if parts == ['api', 'topics', 'add']:
        return add_topic(server.root, body)
    if len(parts) == 4 and parts[:2] == ['api', 'project']:
        if parts[3] == 'retry':
            return retry_project(server.root, parts[2], expected_revision=body.get('expected_revision'))
        if parts[3] == 'reopen':
            if body.get('confirmed') is not True:
                raise ValueError('Bác sĩ cần xác nhận mở lại trên app.')
            return reopen_project(server.root, parts[2], expected_revision=body.get('expected_revision'),
                                  reviewer=body.get('reviewer'), reason=body.get('reason'), changed=body.get('changed'),
                                  limiter=server.limiter, pin=str(body.get('pin', '')))
    return None


def _library_post(server, action: str, body: dict) -> dict:
    from healthvideo.workflows import asset_library as library

    allowed = {
        'select': {'slug', 'expected_revision'},
        'import': {'slug', 'expected_revision', 'selection_id', 'origin', 'prompt', 'license', 'source_url'},
        'bind': {'slug', 'expected_revision', 'asset_id', 'scene_id'},
        'open': {'id', 'folder'},
    }
    if action not in allowed:
        raise LookupError('Không có thao tác thư viện này.')
    if set(body) - allowed[action]:
            raise ValueError('Chỉ nhận ID lựa chọn; không nhận đường dẫn từ trình duyệt.')
    if action == 'open':
        from healthvideo.workflows.dashboard import _open_path

        _, path = library.resolve_asset(server.root, body.get('id'))
        if not body.get('folder') and path.suffix.lower() == '.svg':
            raise ValueError('SVG chỉ xem thẻ an toàn hoặc mở thư mục.')
        _open_path(path.parent if body.get('folder') else path)
        return {'opened': True}
    layout = project_layout(server.root, body.get('slug', ''))
    if body.get('expected_revision') != layout.manifest.active_revision:
        raise ValueError('Revision đã thay đổi; tải lại.')
    if not hasattr(server, 'image_selections'):
        server.image_selections = library.ImageSelections()
    if action == 'select':
        return server.image_selections.select(layout.project_dir)
    if action == 'import':
        source = server.image_selections.consume(layout.project_dir, body.get('selection_id'))
        return library.import_image(layout.project_dir, source, origin=body.get('origin'), prompt=body.get('prompt'),
                                    license=body.get('license'), source_url=body.get('source_url'),
                                    now=datetime.now().astimezone())
    with _MUTATION_LOCK:
        _editable(server.root, body['slug'], body.get('expected_revision'))
        library.bind_image(layout.project_dir, body.get('asset_id'), body.get('scene_id'),
                           expected_revision=body.get('expected_revision'))
    return {'bound': True}
