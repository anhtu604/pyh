import json
import logging

from typer.testing import CliRunner

from healthvideo import cli
from healthvideo.workflows import factory


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps({'ok': True, 'result': [{'message': {'chat': {'id': 123}}}]}).encode()


def test_notify_sends_telegram_when_configured(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'private-token')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', '123')
    calls = []
    monkeypatch.setattr(factory, 'notify_windows', lambda *args: calls.append(args))
    def transport(request, *, timeout):
        assert timeout == 10
        assert request.method == 'POST'
        payload = json.loads(request.data)
        assert payload == {'chat_id': '123', 'text': 'Topic\nmedical\nChạy: healthvideo duyet'}
        calls.append(payload)
        return Response()
    assert factory.notify('Topic', 'medical', transport=transport)
    assert len(calls) == 2


def test_notify_telegram_failure_does_not_raise_or_leak_token(monkeypatch, caplog):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'private-token')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', '123')
    monkeypatch.setattr(factory, 'notify_windows', lambda *args: None)
    def transport(request, **kwargs):
        assert 'secret claim' not in json.loads(request.data)['text']
        raise OSError(request.full_url)
    with caplog.at_level(logging.WARNING):
        assert not factory.notify('Topic', 'bị chặn: secret claim', transport=transport)
    assert 'private-token' not in caplog.text
    assert 'secret claim' not in caplog.text
    assert 'Telegram' in caplog.text


def test_child_env_strips_tokens(monkeypatch):
    for name in ('TELEGRAM_CHAT_ID', 'TELEGRAM_BOT_TOKEN', 'MY_TOKEN', 'SECRET_KEY', 'myPin'):
        monkeypatch.setenv(name, 'hidden')
        present = name in factory.child_env()
        assert not present


def test_notify_setup_prints_chat_id(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'private-token')
    from healthvideo.workflows import telegram
    monkeypatch.setattr(telegram.urllib.request, 'urlopen', lambda *args, **kw: Response())
    result = CliRunner().invoke(cli.app, ['notify-setup'])
    assert result.exit_code == 0, result.output
    assert '123' in result.output
    assert 'BotFather' in result.output
    assert 'private-token' not in result.output
    assert not (tmp_path / '.env').exists()


def test_agent_invocation_strips_credentials(monkeypatch, tmp_path):
    from healthvideo.agents import CODEX, invoke
    monkeypatch.setenv('TELEGRAM_CHAT_ID', '123')
    monkeypatch.setenv('OTHER_SECRET', 'secret')
    def runner(argv, **kwargs):
        keys = set(kwargs['env'])
        assert 'TELEGRAM_CHAT_ID' not in keys
        assert 'OTHER_SECRET' not in keys
        return type('Done', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
    assert invoke(CODEX, 'test', cwd=tmp_path, log_dir=tmp_path / 'logs', runner=runner).ok


def test_doctor_telegram_optional(monkeypatch):
    from healthvideo.workflows.doctor import _telegram_check
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
    assert not _telegram_check().ok
    assert _telegram_check().required == 'optional'
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'private-token')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', '123')
    assert _telegram_check().ok
