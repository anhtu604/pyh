from types import SimpleNamespace

import pytest

from healthvideo.workflows import channel_connections as connections
from healthvideo.workflows import channel_publishing as publishing
from healthvideo.workflows import tiktok_browser
from healthvideo.workflows.dashboard_operations import get_route, post_route


def test_routes_connection_callback_and_loopback(tmp_path, monkeypatch):
    server = SimpleNamespace(root=tmp_path, server_address=('127.0.0.1', 4321))
    monkeypatch.setattr(connections, 'connection_status', lambda root: {'youtube': {'connected': False}})
    assert get_route(server, ['api', 'channel', 'connections'], {})['youtube']['connected'] is False
    monkeypatch.setattr(connections, 'begin_connection', lambda root, platform, redirect_uri: {'redirect_uri': redirect_uri})
    assert post_route(server, ['api', 'channel', 'connect'], {'platform': 'youtube'})['redirect_uri'] == 'http://127.0.0.1:4321/api/channel/oauth/youtube/callback'
    monkeypatch.setattr(connections, 'complete_connection', lambda root, platform, params: {'state': params['state']})
    assert get_route(server, ['api', 'channel', 'oauth', 'youtube', 'callback'], {'state': ['safe'], 'code': ['secret']}) == {'state': 'safe'}
    with pytest.raises(ValueError, match='Duplicate'):
        get_route(server, ['api', 'channel', 'oauth', 'youtube', 'callback'], {'state': ['a', 'b']})


def test_publication_requires_consent_and_approved_fields(tmp_path, monkeypatch):
    server = SimpleNamespace(root=tmp_path)
    body = {'platform': 'tiktok', 'slug': 'valid-slug', 'clip_id': 'CL01', 'privacy': 'SELF_ONLY'}
    monkeypatch.setattr(publishing, 'publish_approved', lambda *a, **k: {'status': 'pending'})
    with pytest.raises(ValueError, match='consent'):
        post_route(server, ['api', 'channel', 'publish'], body)
    with pytest.raises(ValueError, match='music'):
        post_route(server, ['api', 'channel', 'publish'], {**body, 'confirmed': True})
    result = post_route(server, ['api', 'channel', 'publish'], {**body, 'confirmed': True, 'music_usage_confirmed': True, 'noncommercial_confirmed': True})
    assert result['status'] == 'pending'
    with pytest.raises(ValueError, match='approved'):
        post_route(server, ['api', 'channel', 'publish-preview'], {'title': 'arbitrary'})


def test_tiktok_browser_post_routes_dispatch_and_validate(tmp_path, monkeypatch):
    server = SimpleNamespace(root=tmp_path)
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(tiktok_browser, 'install_backend', lambda root: calls.append(('install', root)) or {'status': 'installing'})
    monkeypatch.setattr(tiktok_browser, 'begin_login', lambda root: calls.append(('login', root)) or {'status': 'logging_in'})
    monkeypatch.setattr(tiktok_browser, 'disconnect', lambda root: calls.append(('disconnect', root)) or {'status': 'idle'})

    assert post_route(server, ['api', 'channel', 'browser-install'], {'platform': 'tiktok'}) == {'status': 'installing'}
    assert post_route(server, ['api', 'channel', 'browser-login'], {'platform': 'tiktok'}) == {'status': 'logging_in'}
    assert post_route(server, ['api', 'channel', 'browser-disconnect'], {'platform': 'tiktok'}) == {'status': 'idle'}
    assert calls == [('install', tmp_path), ('login', tmp_path), ('disconnect', tmp_path)]

    with pytest.raises(ValueError, match='TikTok browser'):
        post_route(server, ['api', 'channel', 'browser-login'], {'platform': 'youtube'})
    with pytest.raises(ValueError, match='TikTok browser'):
        post_route(server, ['api', 'channel', 'browser-login'], {'platform': 'tiktok', 'session': 'unexpected'})


@pytest.mark.parametrize(('action', 'operation'), [
    ('browser-install', 'install_backend'),
    ('browser-login', 'begin_login'),
    ('browser-disconnect', 'disconnect'),
])
def test_browser_actions_reach_tiktok_backend(tmp_path, monkeypatch, action, operation):
    server = SimpleNamespace(root=tmp_path)
    monkeypatch.setattr(tiktok_browser, operation, lambda root: {'root': root})
    path = ['api', 'channel', action]
    assert post_route(server, path, {'platform': 'tiktok'}) == {'root': tmp_path}
    with pytest.raises(ValueError, match='Only TikTok'):
        post_route(server, path, {'platform': 'youtube'})
