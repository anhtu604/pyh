"""Local OmniRoute lifecycle and isolated credentials for factory agents."""

import json
import shutil
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from pydantic import BaseModel, ConfigDict

from healthvideo.env import background_popen_kwargs, child_env
from healthvideo.process import UnsafeBatchLauncherError, prepare_subprocess_argv
from healthvideo.storage.files import read_yaml


class RouterConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    enabled: bool = False
    base_url: str = 'http://127.0.0.1:20128/v1'
    key_file: str = '~/.codex/pyh/omniroute-key'


def configuration(root: Path) -> RouterConfig:
    path = root / 'profiles/omniroute.yaml'
    config = RouterConfig.model_validate(read_yaml(path) if path.is_file() else {})
    url = urlsplit(config.base_url)
    if (url.scheme != 'http' or url.hostname not in ('localhost', '127.0.0.1', '::1')
            or url.username or url.password or url.query or url.fragment
            or url.path.rstrip('/') != '/v1'):
        raise ValueError('OmniRoute phải dùng địa chỉ HTTP loopback /v1 trên máy này.')
    return config


def healthy(config: RouterConfig) -> bool:
    origin = config.base_url.rsplit('/v1', 1)[0]
    try:
        with urlopen(origin + '/api/health', timeout=2) as response:
            return response.status == 200 and json.load(response).get('status') == 'ok'
    except (OSError, URLError, ValueError):
        return False


def _server_argv(port: int) -> list[str]:
    arguments = ['serve', '--port', str(port), '--no-open', '--no-tray']
    try:
        return prepare_subprocess_argv(['omniroute', *arguments])
    except UnsafeBatchLauncherError:
        # npm's Windows .cmd shim cannot be executed safely without a shell.
        shim = shutil.which('omniroute')
        entry = (Path(shim).parent / 'node_modules/omniroute/bin/omniroute.mjs'
                 if shim else None)
        if entry is None or not entry.is_file():
            raise RuntimeError('Không tìm thấy omniroute.mjs; cần cài lại OmniRoute.') from None
        return prepare_subprocess_argv(['node', str(entry), *arguments])


def ensure_ready(root: Path, *, timeout: float = 60) -> None:
    config = configuration(root)
    if not config.enabled or healthy(config):
        return
    # Share one launch across dashboard, CLI and repair-worker processes.
    from healthvideo.agents import _quota_lock

    with _quota_lock(root / 'cache/omniroute-start'):
        if healthy(config):
            return
        log = root / 'cache/omniroute.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        port = urlsplit(config.base_url).port or 80
        with log.open('ab') as output:
            process = subprocess.Popen(
                _server_argv(port),
                cwd=root.resolve(), env=child_env(), stdin=subprocess.DEVNULL,
                stdout=output, stderr=output, shell=False, **background_popen_kwargs(),
            )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if healthy(config):
                return
            if process.poll() is not None:
                break
            time.sleep(0.25)
        raise RuntimeError('OmniRoute chưa sẵn sàng; xem cache/omniroute.log rồi khởi động lại xưởng.')


def agent_environment(root: Path) -> tuple[RouterConfig, dict[str, str]]:
    config = configuration(root)
    if not config.enabled:
        raise ValueError('Chưa bật OmniRoute trong profiles/omniroute.yaml.')
    key_path = Path(config.key_file).expanduser()
    if not key_path.is_absolute():
        key_path = root / key_path
    try:
        key = key_path.read_text(encoding='utf-8').strip()
    except OSError:
        raise ValueError('Thiếu khóa riêng của xưởng cho OmniRoute.') from None
    if not key:
        raise ValueError('Khóa OmniRoute đang trống.')
    return config, {'PYH_OMNIROUTE_API_KEY': key}
