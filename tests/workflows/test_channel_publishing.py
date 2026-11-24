import json
from types import SimpleNamespace

import pytest

from healthvideo.workflows import channel_publishing as pub
from healthvideo.workflows.package import package_project
from tests.workflows.test_package import _v2_video_approved_project


@pytest.fixture
def approved(tmp_path, monkeypatch):
    project = _v2_video_approved_project(tmp_path / 'projects')
    from healthvideo.storage.files import read_yaml
    actual_slug = read_yaml(project / 'project.yaml')['slug']
    target = project.with_name(actual_slug)
    if target != project:
        project.rename(target)
        project = target
    package_project(project)
    root = project.parent.parent
    fake = SimpleNamespace(connection_status=lambda root: {'accounts': {'youtube': {'account_id': 'acct', 'connected': True}}},
                           authorized_account=lambda *a, **k: {'account_id': 'acct', 'access_token': 'token'},
                           access_token=lambda *a, **k: 'token', store_publication_secret=lambda *a: None)
    monkeypatch.setattr(pub, '_connections', lambda: fake)
    return root, project.name, project


def _publish(root, slug, **kwargs):
    if kwargs.get('confirmed') is True:
        preview, _ = pub._validated(root, slug, kwargs['platform'], kwargs.get('clip_id'), kwargs.get('title_index', 0))
        kwargs.setdefault('expected_revision', preview['revision'])
        kwargs.setdefault('expected_sha256', preview['sha256'])
    return pub.publish_approved(root, slug, **kwargs)


def test_preview_and_tampered_package(approved):
    root, slug, project = approved
    result = pub.publication_preview(root, slug, 'youtube')
    assert result['gates_current']
    asset = next(project.glob('revisions/*/publish/video.mp4'))
    asset.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='hash'):
        pub.publication_preview(root, slug, 'youtube')


@pytest.mark.parametrize('slug,clip', [('../bad', None), ('valid-slug', '../clip'), ('valid-slug', 'C:evil')])
def test_traversal(tmp_path, slug, clip):
    with pytest.raises((ValueError, LookupError)):
        pub.publication_preview(tmp_path, slug, 'youtube', clip)


def test_stale_gate(approved):
    root, slug, project = approved
    script = next(project.glob('revisions/*/script/script.yaml'))
    script.write_text(script.read_text(encoding='utf-8').replace('title:', 'title: changed #'), encoding='utf-8')
    with pytest.raises(ValueError):
        pub.publication_preview(root, slug, 'youtube')


def test_missing_gate(approved):
    root, slug, project = approved
    next(project.glob('revisions/*/reviews/medical-approval.yaml')).unlink()
    with pytest.raises(FileNotFoundError):
        pub.publication_preview(root, slug, 'youtube')


def test_uncertain_intent_prevents_retry(approved, monkeypatch):
    root, slug, _ = approved
    calls = []
    def request(*args, **kwargs):
        calls.append(args)
        raise OSError('secret bearer endpoint')
    monkeypatch.setattr(pub, '_request', request)
    first = _publish(root, slug, platform='youtube', confirmed=True, expected_account_id='acct', privacy='private')
    second = _publish(root, slug, platform='youtube', confirmed=True, expected_account_id='acct', privacy='private')
    assert first == second
    assert first['status'] == 'needs_reconciliation'
    assert 'secret' not in json.dumps(first)
    assert len(calls) == 1


def test_runtime_failure_never_persists_provider_secrets(approved, monkeypatch):
    root, slug, _ = approved
    def fail(*args, **kwargs):
        raise RuntimeError('Bearer secret-token https://provider/secret-session')
    monkeypatch.setattr(pub, '_request', fail)
    receipt = _publish(root, slug, platform='youtube', confirmed=True,
        expected_account_id='acct', privacy='public')
    assert receipt['status'] == 'needs_reconciliation'
    assert 'secret-token' not in json.dumps(receipt)


def test_youtube_success_and_explicit_privacy(approved, monkeypatch):
    root, slug, _ = approved
    with pytest.raises(ValueError, match='visibility'):
        _publish(root, slug, platform='youtube', confirmed=True, expected_account_id='acct')
    replies = iter([(200, {'Location': 'https://www.googleapis.com/upload/session'}, {}), (200, {}, {'id': 'video123'})])
    monkeypatch.setattr(pub, '_request', lambda *a, **k: next(replies))
    result = _publish(root, slug, platform='youtube', confirmed=True, expected_account_id='acct', privacy='private')
    assert result['status'] == 'posted'
    assert result['video_id'] == 'video123'
    assert 'session' not in json.dumps(result)


def test_concurrent_lock_suppresses(tmp_path):
    path = pub._receipt_path(tmp_path, 'a' * 64)
    with pub._lock(path), pytest.raises(ValueError, match='progress'), pub._lock(path):
        pass


def test_provider_error_sanitized(monkeypatch):
    from urllib.error import HTTPError
    monkeypatch.setattr(pub, 'urlopen', lambda *a, **k: (_ for _ in ()).throw(HTTPError('secret', 403, 'quota', {}, None)))
    with pytest.raises(RuntimeError, match='HTTP 403'):
        pub._request('POST', 'https://example.com')


def test_tiktok_init_and_upload_are_pending(tmp_path, monkeypatch):
    asset = tmp_path / 'clip.mp4'
    asset.write_bytes(b'approved')
    preview = {'platform': 'tiktok', 'slug': 'valid-slug', 'revision': 'r001', 'clip_id': 'CL01',
               'sha256': pub.sha256_file(asset), 'account': {'id': 'a', 'name': 'A'},
               'title': 'approved', 'caption': 'approved caption'}
    fake = SimpleNamespace(authorized_account=lambda *a, **k: {'account_id': 'a', 'access_token': 'token'},
                           access_token=lambda *a, **k: 'token', store_publication_secret=lambda *a: None)
    monkeypatch.setattr(pub, '_connections', lambda: fake)
    monkeypatch.setattr(pub, '_validated', lambda *a: (preview, asset))
    monkeypatch.setattr(pub, '_account', lambda *a: preview['account'])
    monkeypatch.setattr(pub, '_duration', lambda *a: 20)
    calls = []
    def tt(endpoint, token, body):
        calls.append(endpoint)
        if endpoint == 'creator_info/query':
            return {'privacy_level_options': ['SELF_ONLY'], 'max_video_post_duration_sec': 60}
        if endpoint == 'video/init':
            return {'publish_id': 'publish123', 'upload_url': 'https://open.tiktokapis.com/upload'}
        return {'status': 'PROCESSING_UPLOAD'}
    monkeypatch.setattr(pub, '_tt', tt)
    monkeypatch.setattr(pub, '_request', lambda *a, **k: (201, {}, {}))
    result = _publish(tmp_path, 'valid-slug', platform='tiktok', confirmed=True, expected_account_id='a', music_usage_confirmed=True, noncommercial_confirmed=True, clip_id='CL01', privacy='SELF_ONLY')
    assert result['status'] == 'pending'
    assert result['publish_id'] == 'publish123'
    monkeypatch.setattr(pub, '_tt', lambda *a: {'status': 'PUBLISH_COMPLETE'})
    assert pub.publication_status(tmp_path, result['receipt_id'])['status'] == 'posted'
    monkeypatch.setattr(pub, '_account', lambda *a: {'id': 'changed'})
    with pytest.raises(ValueError, match='account changed'):
        pub.publication_status(tmp_path, result['receipt_id'])


def test_core_cannot_bypass_consent(tmp_path):
    with pytest.raises(ValueError, match='consent'):
        _publish(tmp_path, 'valid-slug', platform='youtube', privacy='private')
    with pytest.raises(ValueError, match='music'):
        pub.publish_approved(tmp_path, 'valid-slug', platform='tiktok', confirmed=True, privacy='SELF_ONLY')


def test_preview_account_must_match(approved):
    root, slug, _ = approved
    with pytest.raises(ValueError, match='Account changed'):
        _publish(root, slug, platform='youtube', confirmed=True, privacy='private', expected_account_id='other')


def test_snapshot_refuses_bytes_changed_after_validation(tmp_path):
    asset = tmp_path / 'video.mp4'
    asset.write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed'):
        pub._snapshot(asset, '0' * 64)


def test_youtube_reconciliation_never_restarts_upload(approved, monkeypatch):
    root, slug, _ = approved
    fake = pub._connections()
    fake.load_publication_secret = lambda *a: 'https://www.googleapis.com/upload/session'
    replies = iter([(200, {'Location': 'https://www.googleapis.com/upload/session'}, {})])
    def uncertain(method, url, **kwargs):
        if method == 'POST':
            return next(replies)
        raise OSError('network')
    monkeypatch.setattr(pub, '_request', uncertain)
    receipt = _publish(root, slug, platform='youtube', privacy='private', confirmed=True, expected_account_id='acct')
    assert receipt['status'] == 'needs_reconciliation'
    calls = []
    def probe(method, url, **kwargs):
        calls.append((method, kwargs))
        return 200, {}, {'id': 'confirmed-video'}
    monkeypatch.setattr(pub, '_request', probe)
    final = pub.publication_status(root, receipt['receipt_id'])
    assert final['status'] == 'posted'
    assert calls[0][0] == 'PUT'
    assert calls[0][1]['body'] == b''


def test_account_changes_during_atomic_authorization(approved, monkeypatch):
    root, slug, _ = approved
    pub._connections().authorized_account = lambda *a, **k: {'account_id': 'different', 'access_token': 'token'}
    with pytest.raises(ValueError, match='account changed'):
        _publish(root, slug, platform='youtube', privacy='private', confirmed=True, expected_account_id='acct')
    assert not list((root / 'topics').rglob('*.json'))


def test_approved_youtube_clip_caption_tags_and_gate_bytes(tmp_path, monkeypatch):
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.storage.files import read_yaml, write_yaml_atomic
    from healthvideo.workflows.gate_review import approve_gate
    from tests.workflows.test_package import NOW, _v2_awaiting_video_review_project

    project = _v2_awaiting_video_review_project(tmp_path / 'projects')
    slug = read_yaml(project / 'project.yaml')['slug']
    target = project.with_name(slug)
    project.rename(target)
    project = target
    rev = project / 'revisions/001'
    posts = read_yaml(rev / 'posts/posts.yaml')
    posts['clip_captions'] = {'CL01': {'tiktok': 'Approved TikTok caption',
                                      'shorts': 'Approved Shorts caption', 'reels': 'Approved Reels caption'}}
    posts['youtube_tags'] = ['approved-tag']
    write_yaml_atomic(rev / 'posts/posts.yaml', posts)
    clip = rev / 'renders/clips/CL01.mp4'
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b'approved-clip-bytes')
    from tests.helpers import write_critic_review_fixture

    manifest_path = rev / 'renders/render-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['clips'] = {'CL01': 'clips/CL01.mp4'}
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    write_critic_review_fixture(project, product=True)
    approve_gate(project, GateKind.VIDEO, reviewer='Doctor', now=NOW)
    package_project(project)
    fake = SimpleNamespace(connection_status=lambda root: {'youtube': {'account_id': 'acct', 'connected': True}},
                           authorized_account=lambda *a, **k: {'account_id': 'acct', 'access_token': 'token'},
                           store_publication_secret=lambda *a: None)
    monkeypatch.setattr(pub, '_connections', lambda: fake)
    preview = pub.publication_preview(tmp_path, slug, 'youtube', clip_id='CL01', title_index=1)
    assert preview['caption'] == 'Approved Shorts caption'
    assert preview['title'] == posts['youtube_titles'][1]
    assert preview['tags'] == ['approved-tag']
    requests = []
    def request(method, url, **kwargs):
        requests.append((method, kwargs))
        return (200, {'Location': 'https://www.googleapis.com/upload/session'}, {}) if method == 'POST' else (200, {}, {'id': 'short123'})
    monkeypatch.setattr(pub, '_request', request)
    result = _publish(tmp_path, slug, platform='youtube', clip_id='CL01', title_index=1,
                                  confirmed=True, expected_account_id='acct', privacy='private')
    assert result['status'] == 'posted'
    assert requests[0][1]['body']['snippet'] == {'title': posts['youtube_titles'][1],
        'description': 'Approved Shorts caption', 'tags': ['approved-tag']}
    assert requests[1][1]['body'] == b'approved-clip-bytes'
    clip.write_bytes(b'tampered-original')
    with pytest.raises(ValueError, match='video approval'):
        pub.publication_preview(tmp_path, slug, 'youtube', clip_id='CL01')


@pytest.mark.parametrize('field,value', [('expected_revision', 'other-revision'), ('expected_sha256', '0' * 64)])
def test_core_binds_exact_preview_artifact(approved, monkeypatch, field, value):
    root, slug, _ = approved
    monkeypatch.setattr(pub, '_request', lambda *a, **k: pytest.fail('No provider call permitted'))
    with pytest.raises(ValueError, match='changed since preview'):
        _publish(root, slug, platform='youtube', confirmed=True, privacy='private',
                 expected_account_id='acct', **{field: value})


@pytest.fixture
def approved_thumbnail(tmp_path, monkeypatch):
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.render import thumbnail
    from healthvideo.storage.files import read_yaml
    from healthvideo.workflows.gate_review import approve_gate
    from tests.render.test_thumbnail import add_thumbnail, runner
    from tests.workflows.test_package import NOW, _v2_awaiting_video_review_project

    project = _v2_awaiting_video_review_project(tmp_path / 'projects')
    slug = read_yaml(project / 'project.yaml')['slug']
    target = project.with_name(slug)
    if target != project:
        project.rename(target)
    project = target
    rev = project / 'revisions/001'
    add_thumbnail(rev)
    thumbnail.render_thumbnail(rev, runner=runner)
    approve_gate(project, GateKind.VIDEO, reviewer='Doctor', now=NOW)
    package_project(project)
    fake = SimpleNamespace(connection_status=lambda root: {'youtube': {'account_id': 'acct', 'connected': True}},
                           authorized_account=lambda *a, **k: {'account_id': 'acct', 'access_token': 'token'},
                           store_publication_secret=lambda *a: None)
    monkeypatch.setattr(pub, '_connections', lambda: fake)
    return tmp_path, slug, rev


def test_thumbnail_failure_preserves_video_and_retry_only_thumbnail(approved_thumbnail, monkeypatch):
    root, slug, rev = approved_thumbnail
    calls = []
    fail = True
    def request(method, url, **kwargs):
        calls.append(url)
        if 'thumbnails/set' in url:
            receipt = json.loads(next((root / 'topics/channel-publications').glob('*.json')).read_text())
            assert receipt['status'] == 'posted' and receipt['video_id'] == 'video123'
            assert kwargs['body'] == (rev / 'publish/thumbnail.png').read_bytes()
            if fail:
                raise OSError('SECRET')
            return 200, {}, {'items': [{}]}
        if method == 'POST':
            return 200, {'Location': 'https://www.googleapis.com/upload/session'}, {}
        return 200, {}, {'id': 'video123'}
    monkeypatch.setattr(pub, '_request', request)
    first = _publish(root, slug, platform='youtube', confirmed=True, privacy='private', expected_account_id='acct')
    assert first['status'] == 'posted' and first['thumbnail_status'] == 'failed'
    assert 'SECRET' not in json.dumps(first)
    second = _publish(root, slug, platform='youtube', confirmed=True, privacy='private', expected_account_id='acct')
    assert second == first and len(calls) == 3
    fail = False
    third = pub.publication_status(root, first['receipt_id'])
    assert third['thumbnail_status'] == 'uploaded'
    assert len(calls) == 4 and sum('videos?' in url for url in calls) == 1


def test_thumbnail_manifest_tampering_cannot_authorize_new_image(approved_thumbnail):
    root, slug, rev = approved_thumbnail
    thumb = rev / 'publish/thumbnail.png'
    thumb.write_bytes(b'new image')
    manifest_path = rev / 'publish/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['payload_sha256']['thumbnail.png'] = pub.sha256_file(thumb)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='approved|approval'):
        pub.publication_preview(root, slug, 'youtube')


def test_browser_acceptance_remains_pending_and_never_resends(tmp_path, monkeypatch):
    from healthvideo.workflows import tiktok_browser
    asset = tmp_path / 'clip.mp4'
    asset.write_bytes(b'approved')
    preview = {'platform': 'tiktok', 'slug': 'valid-slug', 'revision': '001', 'clip_id': 'CL01',
               'sha256': pub.sha256_file(asset), 'account': {'id': '123', 'name': 'TikTok · UID 123'},
               'title': 'approved', 'caption': 'approved caption'}
    fake = SimpleNamespace(authorized_account=lambda *a, **k: {
        'account_id': '123', 'connection_method': 'browser_session', 'session': {'cookies': 'SECRET'}})
    monkeypatch.setattr(pub, '_connections', lambda: fake)
    monkeypatch.setattr(pub, '_validated', lambda *a: (preview, asset))
    monkeypatch.setattr(pub, '_account', lambda *a: preview['account'])
    monkeypatch.setattr(pub, '_tt', lambda *a: pytest.fail('No official OAuth calls'))
    calls = []
    def upload(stream, **kwargs):
        calls.append(kwargs)
        assert stream.read() == b'approved'
        return {'storage_video_id': 'storage123'}
    monkeypatch.setattr(tiktok_browser, 'upload_snapshot', upload)
    options = {'platform': 'tiktok', 'clip_id': 'CL01', 'confirmed': True, 'privacy': 'public',
               'expected_account_id': '123', 'music_usage_confirmed': True, 'noncommercial_confirmed': True}
    result = _publish(tmp_path, 'valid-slug', **options)
    assert result['status'] == 'pending_verification' and 'SECRET' not in json.dumps(result)
    assert pub.publication_status(tmp_path, result['receipt_id']) == result
    assert _publish(tmp_path, 'valid-slug', **options) == result
    assert len(calls) == 1
