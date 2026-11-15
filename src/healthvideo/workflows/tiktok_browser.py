"""Optional local-browser backend with encrypted sessions and bounded isolated jobs."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from healthvideo.process import is_same_process, run_bounded, terminate_process_tree

SHA = '0bcbbdcff3600fbc09a47b9be107d1d3fd49b260'
SOURCE = 'autotok @ git+https://github.com/makiisthenes/TiktokAutoUploader.git@' + SHA
_LOCK = threading.RLock()
_JOBS = {}


class SessionExpired(ValueError):
    """Safe session failure; no provider details."""


def _environment():
    allowed = {'SYSTEMROOT', 'WINDIR', 'PATH', 'PATHEXT', 'TEMP', 'TMP', 'LOCALAPPDATA',
               'APPDATA', 'USERPROFILE', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'COMSPEC',
               'HOMEDRIVE', 'HOMEPATH', 'LANG', 'LC_ALL'}
    return {k: v for k, v in os.environ.items() if k.upper() in allowed}


def backend_path():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'HealthVideo/tools/autotok'


def _python():
    return backend_path() / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def _chrome():
    candidates = [Path(os.environ.get(key, 'C:/missing')) / 'Google/Chrome/Application/chrome.exe'
                  for key in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA')]
    return next((p for p in candidates if p.is_file()), None)


def _run(argv, *, body=None, timeout=600, cancel=None, env=None):
    def spawned(pid, token):
        if cancel is not None:
            with _LOCK:
                cancel.update(pid=pid, token=token)
                if cancel.get('cancelled') and is_same_process(pid, token):
                    terminate_process_tree(pid)
    try:
        result = run_bounded([str(v) for v in argv],
                             input=None if body is None else json.dumps(body).encode(),
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=timeout, on_spawn=spawned, env=env or _environment())
        if result.returncode or len(result.stdout) > 2_000_000:
            raise ValueError()
        return result.stdout
    except BaseException:  # noqa: BLE001 - subprocess boundary redacts captured output
        raise ValueError('TikTok browser operation interrupted; check profile before retrying') from None


def bridge(body, *, cancel=None):
    chrome = _chrome()
    if not _python().is_file() or not chrome:
        raise ValueError('Install browser backend and local Google Chrome first')
    # Credentials are passed only on stdin, never command arguments or environment.
    env = _environment()
    env.update(AUTOTOK_BROWSER='local', AUTOTOK_BROWSER_PATH=str(chrome))
    raw = _run([_python(), '-I', Path(__file__).with_name('tiktok_browser_bridge.py')],
               body=body, timeout=600, cancel=cancel, env=env)
    try:
        result = json.loads(raw)
        if result.get('code') == 'session_expired':
            raise SessionExpired('TikTok session expired; reconnect')
        if result.get('ok') is not True:
            raise ValueError()
        return result
    except SessionExpired:
        raise
    except (TypeError, ValueError, AttributeError):
        raise ValueError('TikTok browser operation failed; reconnect or check profile before retrying') from None


def browser_status(root):
    from healthvideo.workflows import channel_connections as connections
    with _LOCK:
        job = _JOBS.get(str(Path(root).resolve()), {})
        connected = connections.connection_status(root)['tiktok'].get('connection_method') == 'browser_session'
        pin = backend_path() / 'pin.txt'
        return {'installed': _python().is_file() and pin.is_file() and pin.read_text(encoding='ascii') == SHA,
                'status': job.get('status', 'connected' if connected else 'idle'),
                'message': job.get('message', '')}


def _start(root, action):
    key = str(Path(root).resolve())
    with _LOCK:
        if _JOBS.get(key, {}).get('status') in ('installing', 'logging_in'):
            return browser_status(root)
        job = {'status': 'installing' if action == 'install' else 'logging_in', 'message': ''}
        _JOBS[key] = job

    def run():
        try:
            if action == 'install':
                (backend_path() / 'pin.txt').unlink(missing_ok=True)
                _run([sys.executable, '-m', 'venv', backend_path()], timeout=120, cancel=job)
                _run([_python(), '-m', 'pip', 'install', '--disable-pip-version-check', SOURCE], timeout=600, cancel=job)
                check = ("import importlib.metadata as m,json; import autotok.auth,autotok.uploader; "
                         "assert m.version('autotok')=='2.1.0'; "
                         "assert json.loads(m.distribution('autotok').read_text('direct_url.json'))"
                         "['vcs_info']['commit_id']=='" + SHA + "'")
                _run([_python(), '-I', '-c', check], timeout=30, cancel=job)
                (backend_path() / 'pin.txt').write_text(SHA, encoding='ascii')
                state = 'idle'
            else:
                result = bridge({'action': 'login'}, cancel=job)
                from healthvideo.workflows import channel_connections as connections
                from healthvideo.workflows.tiktok_browser_bridge import verified_uid
                uid = verified_uid(result['session']['cookies'])
                if uid != result.get('uid'):
                    raise ValueError()
                with _LOCK, connections._LOCK:
                    if job.get('cancelled'):
                        return
                    store = connections._store(root)
                    data = store.read()
                    expiry = [float(c['expires']) for c in result['session']['cookies']
                              if c.get('name') in ('sessionid', 'sessionid_ss') and c.get('expires', -1) > 0]
                    data.setdefault('tiktok', {})['browser_session'] = {
                        'account_id': uid, 'session': result['session'], 'last_verified_at': time.time(),
                        'expires_at': min(expiry) if expiry else None}
                    store.write(data)
                state = 'connected'
            with _LOCK:
                if not job.get('cancelled'):
                    job['status'] = state
        except BaseException:  # noqa: BLE001 - SDK boundary never persists raw errors
            with _LOCK:
                if not job.get('cancelled'):
                    job.update(status='failed', message='TikTok browser operation failed; check Chrome or reconnect')

    threading.Thread(target=run, daemon=True).start()
    return browser_status(root)


def install_backend(root):
    return _start(root, 'install')


def begin_login(root):
    if not browser_status(root)['installed']:
        raise ValueError('Install the browser backend first')
    return _start(root, 'login')


def disconnect(root):
    from healthvideo.workflows import channel_connections as connections
    with _LOCK:
        job = _JOBS.pop(str(Path(root).resolve()), {})
        job['cancelled'] = True
        if job.get('pid') and is_same_process(job['pid'], job.get('token')):
            terminate_process_tree(job['pid'])
        with connections._LOCK:
            store = connections._store(root)
            data = store.read()
            data.get('tiktok', {}).pop('browser_session', None)
            store.write(data)
    return browser_status(root)


def invalidate_session(root, account_id):
    from healthvideo.workflows import channel_connections as connections
    with connections._LOCK:
        store = connections._store(root)
        data = store.read()
        session = data.get('tiktok', {}).get('browser_session', {})
        if session.get('account_id') == account_id:
            session['needs_reauth'] = True
            store.write(data)


def upload_snapshot(stream, *, sha256, caption, privacy, authorization):
    with TemporaryDirectory(prefix='healthvideo-approved-') as directory:
        path = Path(directory) / 'approved.mp4'
        with path.open('xb') as target:
            stream.seek(0)
            while chunk := stream.read(8 * 1024 * 1024):
                target.write(chunk)
        result = bridge({'action': 'upload', 'path': str(path), 'sha256': sha256,
                         'caption': caption, 'privacy': privacy,
                         'account_id': authorization['account_id'], 'session': authorization['session']})
        return {k: result[k] for k in ('storage_video_id', 'creation_id') if k in result}
