import json
from datetime import timedelta

import pytest

from healthvideo.workflows import channel_publishing as pub
from tests.workflows import test_channel_publishing
from tests.workflows.test_package import NOW

approved = test_channel_publishing.approved

def _enable(root, monkeypatch):
    from healthvideo.workflows import auto_publish as auto
    monkeypatch.setattr(auto, '_now', lambda: NOW - timedelta(days=1))
    auto.save_settings(root, {'youtube_enabled': True, 'youtube_privacy': 'public'})
    return auto


def test_default_off_does_not_publish(approved, monkeypatch):
    from healthvideo.workflows import auto_publish as auto
    root, slug, _ = approved
    monkeypatch.setattr(pub, '_request', lambda *a, **k: pytest.fail('network'))
    auto.on_packaged(root, slug)
    assert auto.overview(root)['items'] == []
    assert auto.load_settings(root)['youtube_enabled'] is False


def test_public_once_across_repeated_hook(approved, monkeypatch):
    root, slug, project = approved
    auto = _enable(root, monkeypatch)
    before = (project / 'project.yaml').read_bytes()
    calls = []
    def request(method, url, **kwargs):
        calls.append((method, kwargs))
        return (200, {'Location': 'https://www.googleapis.com/upload/session'}, {}) if method == 'POST' else (200, {}, {'id': 'yt1'})
    monkeypatch.setattr(pub, '_request', request)
    auto.on_packaged(root, slug)
    import importlib
    importlib.reload(auto)
    auto.on_packaged(root, slug)
    assert len(calls) == 2
    assert calls[0][1]['body']['status']['privacyStatus'] == 'public'
    assert auto.overview(root)['items'][0]['youtube']['status'] == 'posted'
    assert (project / 'project.yaml').read_bytes() == before


@pytest.mark.parametrize('changed', ['hash', 'approval', 'video_approval', 'stale', 'state', 'old', 'account'])
def test_invalid_or_old_package_never_posts(approved, monkeypatch, changed):
    root, slug, project = approved
    auto = _enable(root, monkeypatch)
    rev = project / 'revisions/001'
    if changed == 'hash':
        (rev / 'publish/video.mp4').write_bytes(b'changed')
    elif changed == 'approval':
        (rev / 'reviews/medical-approval.yaml').unlink()
    elif changed == 'video_approval':
        (rev / 'reviews/video-approval.yaml').unlink()
    elif changed == 'stale':
        script = rev / 'script/script.yaml'
        script.write_text(script.read_text(encoding='utf-8').replace('title:', 'title: changed #'), encoding='utf-8')
    elif changed == 'state':
        from healthvideo.storage.files import read_yaml, write_yaml_atomic
        data = read_yaml(project / 'project.yaml')
        data['state'] = 'video_approved'
        write_yaml_atomic(project / 'project.yaml', data)
    elif changed == 'old':
        monkeypatch.setattr(auto, '_now', lambda: NOW + timedelta(days=1))
        auto.save_settings(root, {'youtube_enabled': False, 'youtube_privacy': 'public'})
        auto.save_settings(root, {'youtube_enabled': True, 'youtube_privacy': 'public'})
    else:
        pub._connections().connection_status = lambda root: {'youtube': {'account_id': 'changed'}}
    monkeypatch.setattr(pub, '_request', lambda *a, **k: pytest.fail('network'))
    auto.on_packaged(root, slug)
    assert not list((root / 'topics/channel-publications').glob('*.json'))


def test_uncertain_network_never_retries_or_changes_project(approved, monkeypatch):
    root, slug, project = approved
    auto = _enable(root, monkeypatch)
    before = {p: p.read_bytes() for p in project.rglob('*') if p.is_file()}
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise OSError('secret')
    monkeypatch.setattr(pub, '_request', fail)
    auto.on_packaged(root, slug)
    auto.on_packaged(root, slug)
    item = auto.overview(root)['items'][0]
    auto.retry_youtube(root, item['id'])
    assert len(calls) == 1
    assert item['youtube']['status'] == 'needs_reconciliation'
    assert 'secret' not in json.dumps(item)
    assert all(p.read_bytes() == content for p, content in before.items())


def test_tiktok_task_requires_fresh_preview_and_per_post_consent(tmp_path, monkeypatch):
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.storage.files import read_yaml, write_yaml_atomic
    from healthvideo.workflows.dashboard_operations import post_route
    from healthvideo.workflows.gate_review import approve_gate
    from healthvideo.workflows.package import package_project
    from tests.helpers import write_critic_review_fixture
    from tests.workflows.test_package import _v2_awaiting_video_review_project

    project = _v2_awaiting_video_review_project(tmp_path / 'projects')
    slug = read_yaml(project / 'project.yaml')['slug']
    project.rename(project.with_name(slug))
    project = project.with_name(slug)
    rev = project / 'revisions/001'
    posts = read_yaml(rev / 'posts/posts.yaml')
    posts['clip_captions'] = {'CL01': {'tiktok': 'Approved caption', 'shorts': 'Shorts', 'reels': 'Reels'}}
    write_yaml_atomic(rev / 'posts/posts.yaml', posts)
    (rev / 'renders/clips').mkdir(exist_ok=True)
    (rev / 'renders/clips/CL01.mp4').write_bytes(b'clip')
    manifest = json.loads((rev / 'renders/render-manifest.json').read_text(encoding='utf-8'))
    manifest['clips'] = {'CL01': 'clips/CL01.mp4'}
    (rev / 'renders/render-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    write_critic_review_fixture(project, product=True)
    approve_gate(project, GateKind.VIDEO, reviewer='Doctor', now=NOW)
    package_project(project)
    from types import SimpleNamespace
    fake = SimpleNamespace(connection_status=lambda root: {p: {'account_id': 'acct'} for p in ('youtube', 'tiktok')},
        authorized_account=lambda root, platform, **kw: {'account_id': 'acct', 'access_token': 'secret',
            'connection_method': 'browser_session' if platform == 'tiktok' else 'oauth'},
        store_publication_secret=lambda *args: None)
    monkeypatch.setattr(pub, '_connections', lambda: fake)
    auto = _enable(tmp_path, monkeypatch)
    monkeypatch.setattr(pub, '_request', lambda method, *a, **k: (200, {'Location': 'https://www.googleapis.com/upload/s'}, {}) if method == 'POST' else (200, {}, {'id': 'yt'}))
    from healthvideo.workflows import tiktok_browser
    uploads = []
    monkeypatch.setattr(tiktok_browser, 'upload_snapshot', lambda *a, **kw: uploads.append(kw) or {'video_id': 'tt'})
    auto.on_packaged(tmp_path, slug)
    item = auto.overview(tmp_path)['items'][0]
    assert item['tiktok'][0]['caption'] == 'Approved caption'
    assert not uploads
    server = SimpleNamespace(root=tmp_path)
    body = {'platform': 'tiktok', 'slug': slug, 'clip_id': 'CL01', 'title_index': 0}
    preview = post_route(server, ['api', 'channel', 'publish-preview'], body)
    assert preview['privacy_options'] == ['private', 'public']
    body.update(privacy='public', expected_account_id='acct', expected_revision=preview['revision'],
        expected_sha256=preview['sha256'], confirmed=True, noncommercial_confirmed=True)
    with pytest.raises(ValueError, match='music'):
        post_route(server, ['api', 'channel', 'publish'], body)
    assert not uploads
    body['music_usage_confirmed'] = True
    result = post_route(server, ['api', 'channel', 'publish'], body)
    assert result['status'] == 'pending_verification'
    assert len(uploads) == 1
    assert auto.overview(tmp_path)['items'][0]['tiktok'][0]['receipt']['status'] == 'pending_verification'
    post_route(server, ['api', 'channel', 'publish'], body)
    assert len(uploads) == 1


def test_settings_invalid_input_fails_closed(tmp_path):
    from healthvideo.workflows import auto_publish as auto
    for body in ({'youtube_enabled': 'true', 'youtube_privacy': 'public'},
                 {'youtube_enabled': True, 'youtube_privacy': 'invalid'},
                 {'youtube_enabled': True, 'youtube_privacy': 'public', 'account': 'injected'}):
        with pytest.raises(ValueError):
            auto.save_settings(tmp_path, body)
    assert auto.load_settings(tmp_path)['youtube_enabled'] is False
