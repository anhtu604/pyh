import subprocess
from pathlib import Path

import pytest

from healthvideo import omniroute
from healthvideo import process as process_tools
from healthvideo.agents import argv_for, invoke_with_failover
from healthvideo.company import ModelSlot


def configure(tmp_path):
    (tmp_path / 'profiles').mkdir()
    key = tmp_path / 'key'
    key.write_text('fixture-private-key')
    (tmp_path / 'profiles/omniroute.yaml').write_text(
        f'enabled: true\nbase_url: http://127.0.0.1:20128/v1\nkey_file: {key.as_posix()}\n'
    )


def test_disabled_router_does_not_launch(tmp_path, monkeypatch):
    monkeypatch.setattr(omniroute.subprocess, 'Popen', lambda *a, **k: pytest.fail('launch'))
    omniroute.ensure_ready(tmp_path)


def test_running_router_is_reused(tmp_path, monkeypatch):
    configure(tmp_path)
    monkeypatch.setattr(omniroute, 'healthy', lambda _: True)
    monkeypatch.setattr(omniroute.subprocess, 'Popen', lambda *a, **k: pytest.fail('launch'))
    omniroute.ensure_ready(tmp_path)


def test_start_waits_for_health_without_shell_or_visible_console(tmp_path, monkeypatch):
    configure(tmp_path)
    states = iter([False, False, True])
    monkeypatch.setattr(omniroute, 'healthy', lambda _: next(states))
    monkeypatch.setattr(omniroute.time, 'sleep', lambda _: None)
    monkeypatch.setattr(omniroute, 'prepare_subprocess_argv', lambda args: args)
    calls = []

    class Process:
        def poll(self):
            return None

    def spawn(args, **kwargs):
        calls.append((args, kwargs))
        return Process()

    monkeypatch.setattr(omniroute.subprocess, 'Popen', spawn)
    omniroute.ensure_ready(tmp_path)
    args, kwargs = calls[0]
    assert args == ['omniroute', 'serve', '--port', '20128', '--no-open', '--no-tray']
    assert kwargs['shell'] is False
    assert kwargs['stdin'] == subprocess.DEVNULL


@pytest.mark.parametrize('entry_exists', [True, False])
def test_windows_npm_launcher_uses_native_node_entrypoint(tmp_path, monkeypatch, entry_exists):
    configure(tmp_path)
    npm = tmp_path / 'npm with spaces'
    entry = npm / 'node_modules/omniroute/bin/omniroute.mjs'
    entry.parent.mkdir(parents=True)
    if entry_exists:
        entry.write_text('// fixture')
    shim = npm / 'omniroute.CMD'
    shim.touch()
    node = str(tmp_path / 'node.exe')
    monkeypatch.setattr(process_tools.shutil, 'which',
                        lambda name: {'omniroute': str(shim), 'node': node}.get(name))
    monkeypatch.setattr(process_tools, '_is_windows_batch',
                        lambda name: Path(name).suffix.lower() in {'.cmd', '.bat'})
    states = iter([False, False, True])
    monkeypatch.setattr(omniroute, 'healthy', lambda _: next(states))
    calls = []

    def spawn(args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(omniroute.subprocess, 'Popen', spawn)
    if not entry_exists:
        with pytest.raises(RuntimeError, match='omniroute.mjs'):
            omniroute.ensure_ready(tmp_path)
        assert calls == []
        return
    omniroute.ensure_ready(tmp_path)
    args, kwargs = calls[0]
    assert args == [node, str(entry), 'serve', '--port', '20128', '--no-open', '--no-tray']
    assert kwargs['shell'] is False
    assert kwargs['stdin'] == subprocess.DEVNULL
    if hasattr(subprocess, 'CREATE_NO_WINDOW'):
        assert kwargs['creationflags'] & subprocess.CREATE_NO_WINDOW
    else:
        assert kwargs['start_new_session']


def test_router_uses_tool_capable_codex_and_private_child_key(tmp_path, monkeypatch):
    configure(tmp_path)
    slot = ModelSlot(cli='omniroute', model='codex/gpt-6.1-sol')
    cli, args = argv_for(slot)
    assert cli.name == 'omniroute'
    assert args[0] == 'codex' and args[args.index('-m') + 1] == slot.model
    observed = []
    monkeypatch.setattr(omniroute, 'healthy', lambda _: True)

    def run(argv, **kwargs):
        observed.append(kwargs['env'])
        return subprocess.CompletedProcess(argv, 0, 'fixture-private-key', '')

    result = invoke_with_failover([slot], 'fixture', cwd=tmp_path, log_dir=tmp_path / 'logs',
                                 role='writer', slug='fixture', step='draft', runner=run)
    assert result.ok
    assert observed[0]['PYH_OMNIROUTE_API_KEY'] == 'fixture-private-key'
    assert 'fixture-private-key' not in result.log_path.read_text()


def test_direct_maker_is_excluded_through_router_too(tmp_path):
    direct = ModelSlot(cli='codex', model='gpt-6.1-sol')
    routed = ModelSlot(cli='omniroute', model='codex/gpt-6.1-sol')
    with pytest.raises(ValueError, match='độc lập'):
        invoke_with_failover([routed], '', cwd=tmp_path, log_dir=tmp_path / 'logs',
                             role='product_critic', slug='fixture', step='product_review',
                             exclude_slots=[direct])


def test_router_quota_does_not_rest_direct_cli_account(tmp_path, monkeypatch):
    configure(tmp_path)
    monkeypatch.setattr(omniroute, 'healthy', lambda _: True)
    routed = ModelSlot(cli='omniroute', model='codex/gpt-6.1-sol')
    direct = ModelSlot(cli='codex', model='gpt-6.1-sol')
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1 if len(calls) == 1 else 0,
                                           'rate limit 429' if len(calls) == 1 else 'ok', '')

    result = invoke_with_failover([routed, direct], '', cwd=tmp_path, log_dir=tmp_path / 'logs',
                                 role='writer', slug='fixture', step='draft', runner=run)
    assert result.ok and result.agent == 'codex' and len(calls) == 2


def test_missing_router_key_falls_back_to_direct(tmp_path):
    configure(tmp_path)
    (tmp_path / 'key').unlink()
    slots = [ModelSlot(cli='omniroute', model='codex/gpt-6.1-sol'),
             ModelSlot(cli='codex', model='gpt-6.1-sol')]

    def run(argv, **kwargs):
        assert 'PYH_OMNIROUTE_API_KEY' not in kwargs['env']
        return subprocess.CompletedProcess(argv, 0, 'ok', '')

    result = invoke_with_failover(slots, '', cwd=tmp_path, log_dir=tmp_path / 'logs',
                                 role='writer', slug='fixture', step='draft', runner=run)
    assert result.ok and result.agent == 'codex'


def test_nonlocal_router_cannot_receive_key(tmp_path):
    configure(tmp_path)
    path = tmp_path / 'profiles/omniroute.yaml'
    path.write_text(path.read_text().replace('127.0.0.1', 'example.com'))
    with pytest.raises(ValueError, match='loopback'):
        omniroute.agent_environment(tmp_path)


def test_factory_background_ensures_router_even_when_factory_is_running(tmp_path, monkeypatch):
    from healthvideo.workflows import factory

    calls = []
    monkeypatch.setattr(omniroute, 'ensure_ready', lambda root: calls.append(root))
    monkeypatch.setattr(factory, 'running_pid', lambda root: 123)
    assert factory.start_background(tmp_path) == 123
    assert calls == [tmp_path]


def test_automatic_model_selection_is_rejected_for_critic_independence():
    with pytest.raises(ValueError, match='provider/model'):
        ModelSlot(cli='omniroute', model='auto/best-coding')


@pytest.mark.parametrize('provider', ['ds-web', 'deepseek-web'])
def test_deepseek_web_router_aliases_have_one_model_identity(provider):
    slot = ModelSlot(cli='omniroute', model=f'{provider}/deepseek-chat')
    assert slot.model_identity == ('deepseek-web', 'deepseek-chat')


@pytest.mark.parametrize('maker_provider,critic_provider', [
    ('ds-web', 'deepseek-web'), ('deepseek-web', 'ds-web'),
])
def test_deepseek_web_alias_cannot_grade_same_maker_model(
    tmp_path, maker_provider, critic_provider,
):
    maker = ModelSlot(cli='omniroute', model=f'{maker_provider}/deepseek-chat')
    critic = ModelSlot(cli='omniroute', model=f'{critic_provider}/deepseek-chat')

    def run(*args, **kwargs):
        pytest.fail('Same-model critic must be excluded before invoking the runner')

    with pytest.raises(ValueError, match='độc lập'):
        invoke_with_failover([critic], '', cwd=tmp_path, log_dir=tmp_path / 'logs',
                             role='product_critic', slug='fixture', step='product_review',
                             exclude_slots=[maker], runner=run)


@pytest.mark.parametrize('model', ['unsupported-provider/deepseek-chat', 'ds-web/', 'deepseek-web/'])
def test_unverified_router_provider_or_empty_model_remains_rejected(model):
    with pytest.raises(ValueError, match='provider/model'):
        ModelSlot(cli='omniroute', model=model)


def test_company_rejects_same_maker_model_through_different_transport(tmp_path):
    import yaml

    from healthvideo.company import COMPANY_PATH, load_company

    data = yaml.safe_load(COMPANY_PATH.read_text(encoding='utf-8'))
    first = data['roles']['writer']['models'][0]
    data['roles']['script_critic']['models'] = [{'cli': 'omniroute', 'model': f"{first['cli']}/{first['model']}"}]
    path = tmp_path / 'company.yaml'
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    with pytest.raises(ValueError, match='cùng model'):
        load_company(path)
