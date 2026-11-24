from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from healthvideo.domain.medanim_library import MedAnimAsset
from healthvideo.storage.files import write_yaml_atomic
from healthvideo.visuals.medanim_assets import (
    MAX_ASSET_BYTES,
    copy_used_assets,
    fetch_licensed_asset,
    load_asset_catalog,
    validate_download_url,
)

DATA = b'<svg/>'
URL = 'https://bioart.niaid.nih.gov/api/bioarts/230/files/630883'


def record(**changes):
    return MedAnimAsset.model_validate({
        'id': 'liver', 'file': 'liver.svg',
        'source_page': 'https://bioart.niaid.nih.gov/bioart/230',
        'original_url': URL, 'author': 'NIAID', 'license': 'Public Domain',
        'sha256': sha256(DATA).hexdigest(), **changes,
    })


class Response:
    def __init__(self, status_code, *, content=b'', headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ValueError('HTTP error')

    def iter_bytes(self, chunk_size):
        for start in range(0, len(self.content), chunk_size):
            yield self.content[start:start + chunk_size]


class Client:
    def __init__(self, handler, ips=('93.184.216.34',)):
        self.requests = []
        self.ips = ips
        self.handler = handler

    def resolve_host(self, hostname):
        return self.ips

    def stream(self, method, url, **kwargs):
        self.requests.append(url)
        assert kwargs['follow_redirects'] is False
        assert kwargs['resolved_ips'] == self.ips
        response = self.handler(SimpleNamespace(url=SimpleNamespace(path=urlsplit(url).path)))
        response.url = url
        return response


@pytest.mark.parametrize('source,url', [
    ('https://smart.servier.com/smart_image/liver-overview/',
     'https://smart.servier.com/wp-content/uploads/2016/10/foie_coupe.png'),
    ('https://bioart.niaid.nih.gov/bioart/230', URL),
    ('https://commons.wikimedia.org/wiki/File:201904_hepatic_lobule.svg',
     'https://upload.wikimedia.org/wikipedia/commons/d/dd/201904_hepatic_lobule.svg'),
    ('https://reactome.org/icon-lib/R-ICO-014108', 'https://reactome.org/icon/R-ICO-014108.svg'),
])
def test_catalog_and_download_each_repository(tmp_path, source, url):
    asset = record(source_page=source, original_url=url, license='CC BY 4.0')
    catalog = tmp_path / 'assets.yaml'
    write_yaml_atomic(catalog, {'assets': [asset.model_dump(mode='json')]})
    assert load_asset_catalog(catalog) == (asset,)
    client = Client(lambda req: Response(200, content=DATA))
    dest = tmp_path / 'downloads'
    path = fetch_licensed_asset(asset, dest, client=client)
    assert path == dest / asset.file
    assert path.read_bytes() == DATA
    assert client.requests == [url]


@pytest.mark.parametrize('license', ['', 'CC BY-SA 4.0', 'CC BY-NC 4.0', 'CC BY-ND 4.0', 'CC BY 3.0'])
def test_catalog_rejects_unaccepted_license(tmp_path, license):
    raw = record().model_dump(mode='json')
    raw['license'] = license
    path = tmp_path / 'assets.yaml'
    write_yaml_atomic(path, {'assets': [raw]})
    with pytest.raises(ValueError):
        load_asset_catalog(path)


@pytest.mark.parametrize('field', ['file', 'source_page', 'original_url', 'author', 'license', 'sha256', 'id'])
def test_catalog_requires_provenance(tmp_path, field):
    raw = record().model_dump(mode='json')
    del raw[field]
    path = tmp_path / 'assets.yaml'
    write_yaml_atomic(path, {'assets': [raw]})
    with pytest.raises(ValueError):
        load_asset_catalog(path)


@pytest.mark.parametrize('url', [
    'http://reactome.org/icon/a.svg', 'https://reactome.org.evil.test/a',
    'https://127.0.0.1/a', 'https://[::1]/a', 'https://10.0.0.1/a',
    'https://user@reactome.org/a', 'https://reactome.org:444/a',
    'https://raw.githubusercontent.com/duerrsimon/bioicons/main/a.svg',
    'https://togotv.dbcls.jp/a', 'https://reactome.org./a',
])
def test_url_rejection(url):
    with pytest.raises(ValueError):
        validate_download_url(url)


@pytest.mark.parametrize('location', ['https://evil.test/a', 'https://127.0.0.1/a', 'https://10.0.0.1/a', 'https://[::1]/a'])
def test_redirect_rejected_before_next_request(tmp_path, location):
    client = Client(lambda req: Response(302, headers={'Location': location}))
    with pytest.raises(ValueError):
        fetch_licensed_asset(record(), tmp_path / 'out', client=client)
    assert client.requests == [URL]
    assert not (tmp_path / 'out' / 'liver.svg').exists()


def test_relative_redirect_and_loop_limit(tmp_path):
    client = Client(lambda req: Response(302, headers={'Location': '/next'})
                    if req.url.path != '/next' else Response(200, content=DATA))
    assert fetch_licensed_asset(record(), tmp_path, client=client).read_bytes() == DATA
    loop = Client(lambda req: Response(302, headers={'Location': '/loop'}))
    with pytest.raises(ValueError, match='redirect'):
        fetch_licensed_asset(record(), tmp_path / 'loop', client=loop)
    assert len(loop.requests) <= 6


@pytest.mark.parametrize('ips', [('127.0.0.1',), ('10.0.0.1',), ('::1',), ('169.254.169.254',), ('93.184.216.34', '192.168.1.1'), ()])
def test_private_dns_rejected_without_http(tmp_path, ips):
    client = Client(lambda req: Response(200, content=DATA), ips=ips)
    with pytest.raises(ValueError):
        fetch_licensed_asset(record(), tmp_path, client=client)
    assert not client.requests


@pytest.mark.parametrize('data,headers', [
    (b'wrong', {}), (b'x' * (MAX_ASSET_BYTES + 1), {}),
    (DATA, {'content-length': str(MAX_ASSET_BYTES + 1)}),
], ids=['hash', 'stream-size', 'header-size'])
def test_hash_and_size_failure_preserve_destination(tmp_path, data, headers):
    dest = tmp_path / 'liver.svg'
    dest.write_bytes(b'previous')
    client = Client(lambda req: Response(200, content=data, headers=headers))
    with pytest.raises(ValueError):
        fetch_licensed_asset(record(), tmp_path, client=client)
    assert dest.read_bytes() == b'previous'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['liver.svg']


@pytest.mark.parametrize('path', ['../x.svg', 'nested/../../x.svg', 'C:/x.svg', 'nested/x.svg:stream', 'nested/CON.svg'])
def test_traversal_rejected(path):
    with pytest.raises(ValueError):
        record(file=path)


def test_symlink_source_destination_and_catalog(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    link = tmp_path / 'linked'
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip('symlink creation unavailable')
    client = Client(lambda req: Response(200, content=DATA))
    with pytest.raises(ValueError):
        fetch_licensed_asset(record(), link / 'nested', client=client)
    assert not client.requests
    with pytest.raises(ValueError):
        load_asset_catalog(link / 'assets.yaml')


def test_copy_only_used_assets_rechecks_hash_and_credits(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'liver.svg').write_bytes(DATA)
    unused = record(id='unused', file='unused.svg')
    assets = (record(), unused)
    dest = tmp_path / 'revision'
    assert copy_used_assets(assets, ['liver'], source, dest) == (record(),)
    assert (dest / 'liver.svg').read_bytes() == DATA
    assert not (dest / 'unused.svg').exists()
    (source / 'liver.svg').write_bytes(b'changed')
    with pytest.raises(ValueError, match='SHA-256'):
        copy_used_assets(assets, ['liver'], source, dest)
    assert (dest / 'liver.svg').read_bytes() == DATA
    with pytest.raises(ValueError):
        copy_used_assets(assets, ['missing'], source, dest)


@pytest.mark.parametrize('license', ['Public Domain', 'CC0', 'CC BY 4.0'])
def test_accepted_licenses(tmp_path, license):
    path = tmp_path / 'assets.yaml'
    write_yaml_atomic(path, {'assets': [record(license=license).model_dump(mode='json')]})
    assert load_asset_catalog(path)[0].license == license


def test_redirect_allowed_host_resolving_private_is_blocked(tmp_path):
    client = Client(lambda req: Response(302, headers={'Location': '/private'}))
    calls = []

    def resolve(host):
        calls.append(host)
        return client.ips if len(calls) == 1 else ('127.0.0.1',)

    client.resolve_host = resolve
    with pytest.raises(ValueError, match='IP'):
        fetch_licensed_asset(record(), tmp_path, client=client)
    assert len(client.requests) == 1
    assert len(calls) == 2


def test_repository_cannot_redirect_to_another_repository(tmp_path):
    client = Client(lambda req: Response(302, headers={'Location': 'https://reactome.org/icon/a.svg'}))
    with pytest.raises(ValueError):
        fetch_licensed_asset(record(), tmp_path, client=client)
    assert client.requests == [URL]


def test_download_exact_size_boundary(tmp_path):
    data = b'x' * MAX_ASSET_BYTES
    client = Client(lambda req: Response(200, content=data))
    path = fetch_licensed_asset(record(sha256=sha256(data).hexdigest()), tmp_path, client=client)
    assert path.stat().st_size == MAX_ASSET_BYTES


@pytest.mark.parametrize('operation', ['download', 'copy-source', 'copy-target', 'catalog'])
def test_link_rejection_on_platform_without_symlink_privileges(tmp_path, monkeypatch, operation):

    source = tmp_path / 'source'
    source.mkdir()
    (source / 'liver.svg').write_bytes(DATA)
    dest = tmp_path / 'dest'
    catalog = tmp_path / 'assets.yaml'
    write_yaml_atomic(catalog, {'assets': [record().model_dump(mode='json')]})
    blocked = {'download': dest, 'copy-source': source / 'liver.svg',
               'copy-target': dest / 'liver.svg', 'catalog': catalog}[operation]
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == blocked or original(path))
    client = Client(lambda req: Response(200, content=DATA))
    with pytest.raises(ValueError, match='Symlink'):
        if operation == 'download':
            fetch_licensed_asset(record(), dest, client=client)
        elif operation == 'catalog':
            load_asset_catalog(catalog)
        else:
            copy_used_assets((record(),), ['liver'], source, dest)
    assert not client.requests
    assert not (dest / 'liver.svg').exists()


def test_copy_revalidates_missing_provenance(tmp_path):
    bad = record().model_copy(update={'author': ''})
    with pytest.raises(ValueError):
        copy_used_assets((bad,), ['liver'], tmp_path, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_duplicate_catalog_ids_and_files_rejected(tmp_path):
    path = tmp_path / 'assets.yaml'
    write_yaml_atomic(path, {'assets': [record().model_dump(mode='json')] * 2})
    with pytest.raises(ValueError, match='Duplicate'):
        load_asset_catalog(path)


def test_supported_python_without_is_junction(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.delattr(Path, 'is_junction', raising=False)
    client = Client(lambda req: Response(200, content=DATA))
    assert fetch_licensed_asset(record(), tmp_path, client=client).read_bytes() == DATA


def test_windows_case_collision_in_catalog_and_direct_copy(tmp_path):
    records = (record(), record(id='other', file='LIVER.svg'))
    path = tmp_path / 'assets.yaml'
    write_yaml_atomic(path, {'assets': [r.model_dump(mode='json') for r in records]})
    with pytest.raises(ValueError, match='Duplicate'):
        load_asset_catalog(path)
    with pytest.raises(ValueError, match='Duplicate'):
        copy_used_assets(records, ['liver', 'other'], tmp_path, tmp_path / 'out')
