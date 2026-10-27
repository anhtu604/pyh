from datetime import UTC, datetime

import pytest
from PIL import Image

from healthvideo.domain.gate_review import GateKind
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic
from healthvideo.workflows import asset_library as lib
from healthvideo.workflows.gate_review import (
    approve_gate,
    medical_reviewed_paths,
    video_reviewed_paths,
)
from tests.helpers import create_v2_project_fixture


@pytest.fixture
def image_project(tmp_path):
    project = create_v2_project_fixture(tmp_path / 'projects')
    image = tmp_path / 'chosen.png'
    Image.new('RGB', (40, 30), 'blue').save(image)
    return tmp_path, project, image


def imported(project, image, **kw):
    return lib.import_image(project, image, origin='Muse AI', prompt='Offline blue fixture',
                            license='Fixture permission', source_url='https://example.test/fixture',
                            now=datetime.now(UTC), **kw)


def test_import_decode_hash_and_duplicate_provenance(image_project):
    root, project, image = image_project
    item = imported(project, image)
    assert (item['width'], item['height']) == (40, 30)
    path = project / 'revisions/001' / item['path']
    assert sha256_file(path) == item['sha256']
    duplicate = lib.import_image(project, image, origin='Other', prompt='Other', license='Other',
                                 source_url='https://example.test/other', now=datetime.now(UTC))
    assert duplicate == item
    assert lib.list_assets(root, slug=project.name, query='blue')[0]['prompt'] == item['prompt']
    assert not lib.list_assets(root, kind='thumbnail', query='blue')


@pytest.mark.parametrize('filename,content', [('evil.svg', b'<svg><script/></svg>'),
                                            ('fake.png', b'not an image')])
def test_reject_svg_and_invalid_raster(image_project, filename, content):
    _, project, image = image_project
    source = image.with_name(filename)
    source.write_bytes(content)
    with pytest.raises(ValueError):
        imported(project, source)
    assert not (project / 'revisions/001/assets/library.yaml').exists()


@pytest.mark.parametrize('field', ['origin', 'prompt', 'license', 'source_url'])
def test_missing_provenance_rejected(image_project, field):
    _, project, image = image_project
    args = {'origin': 'Muse', 'prompt': 'Fixture', 'license': 'Permission', 'source_url': 'https://example.test', 'now': datetime.now(UTC)}
    args[field] = ' '
    with pytest.raises(ValueError):
        lib.import_image(project, image, **args)


def test_listing_types_and_safe_svg_preview(image_project):
    root, project, image = image_project
    rev = project / 'revisions/001'
    for rel in ('assets/illustrations/candidate-01.png', 'renders/review-frames/long/sheet-01.png', 'renders/thumbnail.png'):
        p = rev / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(image.read_bytes())
    items = lib.list_assets(root)
    assert {'flux', 'svg', 'contact_sheet', 'thumbnail'} <= {a['kind'] for a in items}
    svg = next(a for a in items if a['kind'] == 'svg')
    preview = lib.preview_asset(root, svg['id'])
    assert preview.startswith(b'\x89PNG')
    assert b'<svg' not in preview


def test_bind_manifest_license_hash_and_gate_guard(image_project):
    _root, project, image = image_project
    item = imported(project, image)
    rev = project / 'revisions/001'
    with pytest.raises(ValueError, match='Revision'):
        lib.bind_image(project, item['id'], 'SC01', expected_revision='002')
    storyboard = read_yaml(rev / 'storyboard/storyboard.yaml')
    scene = next(s for s in storyboard['scenes'] if s['visual'] == 'whiteboard')
    lib.bind_image(project, item['id'], scene['id'], expected_revision='001')
    assets = read_yaml(rev / 'assets/asset-manifest.yaml')['assets']
    record = next(a for a in assets if a['path'] == item['path'])
    assert record['kind'] == 'background' and record['semantic'] is False
    assert record['storyboard_role'] == 'whiteboard'
    assert read_yaml(rev / 'assets/license-ledger.yaml')['entries'][-1]['sha256'] == item['sha256']
    # Existing medical gate hashes the license ledger; imported bytes must also be covered.
    paths = {**medical_reviewed_paths(rev), **video_reviewed_paths(rev)}
    assert (rev / item['path']) in paths.values()
    manifest = read_yaml(project / 'project.yaml')
    manifest['state'] = 'awaiting_medical_review'
    write_yaml_atomic(project / 'project.yaml', manifest)
    approve_gate(project, GateKind.MEDICAL, reviewer='Fixture doctor', now=datetime.now(UTC))
    before = (rev / 'storyboard/storyboard.yaml').read_bytes()
    with pytest.raises(ValueError, match='mở lại'):
        lib.bind_image(project, item['id'], scene['id'], expected_revision='001')
    assert (rev / 'storyboard/storyboard.yaml').read_bytes() == before


def test_picker_id_one_use_and_project_revision_bound(image_project):
    _, project, image = image_project
    selections = lib.ImageSelections()
    token = selections.select(project, picker=lambda: image)
    assert str(image) not in str(token)
    with pytest.raises(ValueError):
        selections.consume(project, '../chosen.png')
    assert selections.consume(project, token['selection_id']) == image
    with pytest.raises(ValueError):
        selections.consume(project, token['selection_id'])


@pytest.mark.parametrize('change', ['bytes', 'revision', 'project', 'expiry'])
def test_selection_rejects_changed_context(image_project, monkeypatch, change):
    root, project, image = image_project
    monkeypatch.setattr(lib.time, 'monotonic', lambda: 1000)
    selections = lib.ImageSelections()
    token = selections.select(project, picker=lambda: image)['selection_id']
    target = project
    if change == 'bytes':
        Image.new('RGB', (40, 30), 'red').save(image)
    elif change == 'revision':
        data = read_yaml(project / 'project.yaml')
        data['active_revision'] = '002'
        (project / 'revisions/002').mkdir()
        write_yaml_atomic(project / 'project.yaml', data)
    elif change == 'project':
        target = create_v2_project_fixture(root / 'other/projects')
    else:
        monkeypatch.setattr(lib.time, 'monotonic', lambda: 1401)
    with pytest.raises(ValueError):
        selections.consume(target, token)


def test_test_image_cannot_enter_production(image_project):
    root, project, image = image_project
    source = root / 'cache/factory-test/assets/sample.png'
    source.parent.mkdir(parents=True)
    source.write_bytes(image.read_bytes())
    with pytest.raises(ValueError, match='TEST'):
        imported(project, source)


def test_tampered_index_path_never_read_or_bound(image_project):
    root, project, image = image_project
    item = imported(project, image)
    path = project / 'revisions/001/assets/library.yaml'
    data = read_yaml(path)
    data['items'][0]['path'] = '../../../../chosen.png'
    write_yaml_atomic(path, data)
    with pytest.raises(ValueError):
        lib.bind_image(project, item['id'], 'SC01', expected_revision='001')
    assert all(a['path'] != '../../../../chosen.png' for a in lib.list_assets(root))


@pytest.mark.parametrize('shared', [False, True])
def test_rebind_replaces_import_and_cleans_unused_records(image_project, shared):
    _, project, image = image_project
    first = imported(project, image)
    rev = project / 'revisions/001'
    board_path = rev / 'storyboard/storyboard.yaml'
    board = read_yaml(board_path)
    scene = next(s for s in board['scenes'] if s['visual'] == 'whiteboard')
    original = [{'path': read_yaml(rev / 'assets/asset-manifest.yaml')['assets'][0]['path'], 'role': 'whiteboard'}]
    scene['visual_assets'] = original.copy()
    write_yaml_atomic(board_path, board)
    lib.bind_image(project, first['id'], scene['id'], expected_revision='001')
    other = None
    if shared:
        board = read_yaml(board_path)
        other = next(s for s in board['scenes'] if s['id'] != scene['id'])
        other['visual_assets'] = [{'path': first['path'], 'role': 'whiteboard'}]
        write_yaml_atomic(board_path, board)
    Image.new('RGB', (40, 30), 'red').save(image)
    second = imported(project, image)
    lib.bind_image(project, second['id'], scene['id'], expected_revision='001')
    updated = next(s for s in read_yaml(board_path)['scenes'] if s['id'] == scene['id'])
    assert updated['visual_assets'] == [*original, {'path': second['path'], 'role': 'whiteboard'}]
    for file, key in [('asset-manifest.yaml', 'assets'), ('license-ledger.yaml', 'entries')]:
        records = read_yaml(rev / 'assets' / file)[key]
        assert (first['path'] in {r['path'] for r in records}) is shared
        assert second['path'] in {r['path'] for r in records}
    items = read_yaml(rev / 'assets/library.yaml')['items']
    assert next(i for i in items if i['id'] == first['id'])['used_in'] == ([other['id']] if shared else [])
    before = {p: p.read_bytes() for p in (board_path, rev / 'assets/asset-manifest.yaml', rev / 'assets/license-ledger.yaml')}
    lib.bind_image(project, second['id'], scene['id'], expected_revision='001')
    assert {p: p.read_bytes() for p in before} == before
