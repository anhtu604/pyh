"""Local raster library with explicit provenance and revision-safe binding."""

from __future__ import annotations

import hashlib
import io
import itertools
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from healthvideo.domain.asset_manifest import AssetManifest, AssetRecord
from healthvideo.domain.license_ledger import (
    LicenseEntry,
    LicenseLedger,
    validate_license_ledger,
)
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.workflows.dashboard_operations import (
    _MUTATION_LOCK,
    check_revision_paths,
    inside,
    project_layout,
)

RASTER = {'.png', '.jpg', '.jpeg', '.webp'}
MAX_IMAGE_BYTES = 30_000_000
MAX_PIXELS = 24_000_000


def _revision(project: Path):
    inside(project, project / 'project.yaml')
    layout = resolve_project_layout(project)
    check_revision_paths(project, layout.artifact_root)
    return layout


def _index(rev: Path) -> list[dict]:
    path = inside(rev, rev / 'assets/library.yaml')
    items = read_yaml(path).get('items', []) if path.is_file() else []
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise ValueError('Chỉ mục thư viện không hợp lệ.')
    return items


def _local(rev: Path, relative: str) -> Path:
    if not isinstance(relative, str) or '\\' in relative or ':' in relative or '..' in Path(relative).parts:
        raise ValueError('Đường dẫn ảnh không hợp lệ.')
    path = inside(rev, rev / relative)
    if not relative.startswith(('assets/', 'renders/', 'posts/', 'reviews/visual/', 'reviews/imported-contact-sheet')):
        raise ValueError('Ảnh nằm ngoài thư mục cho phép.')
    return path


def _test_path(path: Path) -> bool:
    parts = path.resolve().parts
    return any(a.casefold() == 'cache' and b.casefold() == 'factory-test' for a, b in itertools.pairwise(parts))


def _decode(source: Path) -> Image.Image:
    if source.suffix.lower() not in RASTER or source.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError('Chỉ nhận ảnh PNG/JPEG/WebP tối đa 30 MB; không nhận SVG.')
    try:
        with Image.open(source) as image:
            if image.format not in {'PNG', 'JPEG', 'WEBP'} or image.width * image.height > MAX_PIXELS:
                raise ValueError('Định dạng hoặc kích thước ảnh không được hỗ trợ.')
            image.load()
            return ImageOps.exif_transpose(image).convert('RGBA')
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError('Không giải mã được ảnh raster.') from exc


def import_image(project_dir: Path, source: Path, *, origin: str, prompt: str,
                 license: str, source_url: str, now: datetime) -> dict:
    for value in (origin, prompt, license, source_url):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Cần đủ nguồn, prompt, giấy phép và URL nguồn.')
    parsed = urlsplit(source_url)
    if parsed.scheme not in {'https', 'http'} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('URL nguồn phải là HTTP(S), không chứa thông tin đăng nhập.')
    if _test_path(source) and not _test_path(project_dir):
        raise ValueError('Không nhập ảnh TEST vào production.')
    image = _decode(source)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    data = buffer.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    with _MUTATION_LOCK:
        layout = _revision(project_dir)
        rev = layout.artifact_root
        items = _index(rev)
        prior = next((i for i in items if i.get('sha256') == digest), None)
        if prior:
            path = _local(rev, prior['path'])
            if not path.is_file() or sha256_file(path) != digest:
                raise ValueError('Ảnh đã nhập bị thay đổi; cần khôi phục.')
            return prior
        relative = f'assets/imported/{digest}.png'
        target = _local(rev, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and sha256_file(target) != digest:
            raise ValueError('File nhập hiện có không khớp hash.')
        if not target.exists():
            target.write_bytes(data)
        item = {'id': secrets.token_urlsafe(24), 'path': relative, 'sha256': digest,
                    'origin': origin.strip(), 'prompt': prompt.strip(), 'license': license.strip(),
                    'source_url': source_url.strip(), 'imported_at': now.isoformat(),
                    'width': image.width, 'height': image.height, 'revision': layout.manifest.active_revision,
                    'scope': 'test' if _test_path(project_dir) else 'production', 'used_in': []}
        write_yaml_atomic(rev / 'assets/library.yaml', {'version': 1, 'items': [*items, item]})
        return item


def _opaque(slug: str, revision: str, relative: str) -> str:
    return hashlib.sha256(f'{slug}/{revision}/{relative}'.encode()).hexdigest()


def list_assets(root: Path, *, slug: str | None = None, kind: str | None = None,
                query: str = '') -> list[dict]:
    projects = [project_layout(root, slug)] if slug else []
    if slug is None:
        for manifest in sorted((root / 'projects').glob('*/project.yaml')):
            try:
                projects.append(project_layout(root, manifest.parent.name))
            except (ValueError, LookupError, OSError):
                continue
    result = []
    for layout in projects:
        rev = layout.artifact_root
        index = {i.get('path'): i for i in _index(rev)}
        manifest_path = inside(rev, rev / 'assets/asset-manifest.yaml')
        records = {a['path']: a for a in read_yaml(manifest_path).get('assets', [])} if manifest_path.is_file() else {}
        board_path = inside(rev, rev / 'storyboard/storyboard.yaml')
        board = read_yaml(board_path) if board_path.is_file() else {}
        for directory in ('assets', 'renders', 'posts', 'reviews'):
            base = inside(rev, rev / directory)
            for path in sorted(base.rglob('*')) if base.is_dir() else []:
                if not path.is_file() or path.suffix.lower() not in RASTER | {'.svg'}:
                    continue
                try:
                    relative = path.relative_to(rev).as_posix()
                    _local(rev, relative)
                except ValueError:
                    continue
                if any(a['slug'] == layout.project_dir.name and a['path'] == relative for a in result):
                    continue
                asset_kind = ('imported' if relative.startswith('assets/imported/') else
                              'svg' if path.suffix.lower() == '.svg' else
                              'thumbnail' if 'thumbnail' in path.name.lower() else
                              'contact_sheet' if 'sheet' in path.name.lower() or '/review-frames/' in relative else
                              'flux' if 'illustrations/' in relative or 'candidate' in relative else 'image')
                metadata = index.get(relative, {})
                record = records.get(relative, {})
                prompt = metadata.get('prompt') or record.get('prompt') or ''
                if kind and asset_kind != kind or query.casefold() not in f'{prompt} {path.name}'.casefold():
                    continue
                width = height = None
                if path.suffix.lower() in RASTER:
                    try:
                        with Image.open(path) as im:
                            width, height = im.size
                    except (OSError, Image.DecompressionBombError):
                        continue
                result.append({**metadata, 'id': _opaque(layout.project_dir.name, layout.manifest.active_revision, relative),
                               'asset_id': metadata.get('id'), 'slug': layout.project_dir.name,
                               'revision': layout.manifest.active_revision, 'path': relative,
                               'name': path.name, 'kind': asset_kind, 'prompt': prompt,
                               'width': width, 'height': height,
                               'origin': metadata.get('origin') or record.get('source', ''),
                               'license': metadata.get('license') or record.get('license', ''),
                               'created_at': metadata.get('imported_at') or datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(),
                               'used_in': [s['id'] for s in board.get('scenes', []) if any(r.get('path') == relative for r in s.get('visual_assets', []))]})
    return result


def resolve_asset(root: Path, asset_id: str) -> tuple[dict, Path]:
    if not isinstance(asset_id, str) or len(asset_id) != 64:
        raise LookupError('ID ảnh không hợp lệ.')
    item = next((a for a in list_assets(root) if a['id'] == asset_id), None)
    if item is None:
        raise LookupError('Không có ảnh này.')
    layout = project_layout(root, item['slug'])
    return item, _local(layout.artifact_root, item['path'])


def preview_asset(root: Path, asset_id: str) -> bytes:
    item, path = resolve_asset(root, asset_id)
    if item['kind'] == 'svg':
        # Never execute or embed SVG from disk; render an inert file card.
        image = Image.new('RGB', (360, 220), '#121b30')
        ImageDraw.Draw(image).text((20, 80), 'SVG · ' + path.name[:38], fill='white')
    else:
        image = _decode(path)
        image.thumbnail((720, 480))
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


def bind_image(project_dir: Path, asset_id: str, scene_id: str, *, expected_revision: str) -> None:
    with _MUTATION_LOCK:
        layout = _revision(project_dir)
        if layout.manifest.active_revision != expected_revision:
            raise ValueError('Revision đã thay đổi; tải lại.')
        rev = layout.artifact_root
        if layout.manifest.state not in {WorkflowState.DRAFT_READY, WorkflowState.EVIDENCE_READY,
                                         WorkflowState.NEEDS_MEDICAL_REVISION} or (rev / 'reviews/medical-approval.yaml').exists():
            raise ValueError('Bác sĩ phải mở lại cổng y khoa trước khi gắn ảnh.')
        items = _index(rev)
        item = next((i for i in items if i.get('id') == asset_id), None)
        if item is None or item.get('revision') != expected_revision:
            raise ValueError('Ảnh không thuộc revision này.')
        if item.get('scope') == 'test' and not _test_path(project_dir):
            raise ValueError('Không gắn ảnh TEST vào production.')
        if not all(str(item.get(k, '')).strip() for k in ('origin', 'prompt', 'license', 'source_url')):
            raise ValueError('Ảnh thiếu provenance/giấy phép.')
        path = _local(rev, item['path'])
        if not path.is_file() or sha256_file(path) != item['sha256']:
            raise ValueError('Hash ảnh đã thay đổi.')
        board_path = inside(rev, rev / 'storyboard/storyboard.yaml')
        board = read_yaml(board_path)
        scene = next((s for s in board.get('scenes', []) if s['id'] == scene_id), None)
        if scene is None or scene.get('visual') != 'whiteboard':
            raise ValueError('Chỉ gắn ảnh trang trí vào cảnh whiteboard có sẵn.')
        refs = scene.get('visual_assets', [])
        replaced = {r['path'] for r in refs if r['path'].startswith('assets/imported/')}
        scene['visual_assets'] = [r for r in refs if r['path'] not in replaced]
        scene['visual_assets'].append({'path': item['path'], 'role': 'whiteboard'})
        used_paths = {r['path'] for s in board['scenes'] for r in s.get('visual_assets', [])}
        unused = replaced - used_paths
        Storyboard.model_validate(board)
        manifest_path = inside(rev, rev / 'assets/asset-manifest.yaml')
        manifest = AssetManifest.model_validate(read_yaml(manifest_path))
        record = AssetRecord(path=item['path'], kind='background', semantic=False,
                             sha256=item['sha256'], source=item['source_url'], license=item['license'],
                             creator=item['origin'], revision=expected_revision, rights_required=True,
                             storyboard_role='whiteboard')
        existing = next((a for a in manifest.assets if a.path == record.path), None)
        if existing is not None and existing != record:
            raise ValueError('Asset đã đăng ký khác provenance; không ghi đè.')
        retained = tuple(a for a in manifest.assets if a.path not in unused)
        manifest = AssetManifest(assets=retained if existing else (*retained, record))
        rights_path = inside(rev, rev / 'assets/license-ledger.yaml')
        ledger = LicenseLedger.model_validate(read_yaml(rights_path)) if rights_path.is_file() else LicenseLedger()
        ledger = LicenseLedger(entries=tuple(e for e in ledger.entries if e.path not in unused))
        if not any(e.path == item['path'] for e in ledger.entries):
            entry = LicenseEntry(path=record.path, source=record.source, creator=record.creator,
                                 license=record.license, revision=record.revision, sha256=record.sha256,
                                 rights_basis=f"{item['license']} · {item['source_url']}")
            ledger = LicenseLedger(entries=(*ledger.entries, entry))
        validate_license_ledger(manifest, ledger, expected_revision)
        # All validation precedes writes; a crash leaves unreferenced assets, never an approval.
        write_yaml_atomic(manifest_path, manifest.model_dump(mode='json'))
        write_yaml_atomic(rights_path, ledger.model_dump(mode='json'))
        write_yaml_atomic(board_path, board)
        for imported in items:
            imported['used_in'] = sorted(s['id'] for s in board['scenes']
                                         if any(r['path'] == imported['path'] for r in s.get('visual_assets', [])))
        write_yaml_atomic(rev / 'assets/library.yaml', {'version': 1, 'items': items})
        from healthvideo.workflows.review_frames import imported_contact_sheet

        imported_contact_sheet(rev)


def choose_image() -> Path | None:
    """The server's native picker is the only HTTP import source authority."""
    from tkinter import Tk, filedialog

    window = Tk()
    window.withdraw()
    try:
        name = filedialog.askopenfilename(parent=window, title='Chọn ảnh minh họa',
                                         filetypes=[('Ảnh raster', '*.png *.jpg *.jpeg *.webp')])
        return Path(name) if name else None
    finally:
        window.destroy()


class ImageSelections:
    def __init__(self):
        self._items = {}
        self._lock = threading.Lock()

    def select(self, project: Path, *, picker=None) -> dict:
        layout = _revision(project)
        source = (picker or choose_image)()
        if source is None:
            return {'cancelled': True}
        source = Path(source).resolve()
        _decode(source)
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._items = {k: v for k, v in self._items.items() if v[0] > time.monotonic()}
            self._items[token] = (time.monotonic() + 300, project.resolve(), layout.manifest.active_revision,
                                  source, sha256_file(source))
        return {'selection_id': token, 'name': source.name, 'revision': layout.manifest.active_revision}

    def consume(self, project: Path, selection_id: str) -> Path:
        if not isinstance(selection_id, str):
            raise TypeError('Cần ID chọn file.')
        with self._lock:
            record = self._items.pop(selection_id, None)
        if record is None:
            raise ValueError('ID chọn file không hợp lệ hoặc đã dùng.')
        expiry, owner, revision, source, digest = record
        if expiry <= time.monotonic() or owner != project.resolve() or revision != _revision(project).manifest.active_revision:
            raise ValueError('Lựa chọn đã hết hạn hoặc khác project/revision.')
        if sha256_file(source) != digest:
            raise ValueError('File đã đổi sau khi chọn; chọn lại.')
        return source
