"""Private isolated SDK process. JSON stdin/stdout only; never invoke upstream CLI/store."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import logging
import os
import re
import sys
from pathlib import Path


def verified_uid(cookies):
    values = {str(c.get('value')) for c in cookies
              if c.get('name') == 'uid_tt' and c.get('domain', '').lstrip('.') in ('tiktok.com', 'www.tiktok.com')}
    value = next(iter(values), '')
    if len(values) != 1 or not re.fullmatch(r'(?:[0-9]{1,40}|[0-9a-fA-F]{32,128})', value):
        raise ValueError('Missing stable TikTok identity')
    if value.isdecimal() and len(value) <= 40:
        return value
    return hashlib.sha256(value.encode('ascii')).hexdigest()


def execute(body):
    from autotok.accounts import Account
    from autotok.auth import open_login_session
    from autotok.uploader import Client

    if os.environ.get('AUTOTOK_BROWSER') != 'local' or not Path(os.environ['AUTOTOK_BROWSER_PATH']).is_file():
        raise ValueError('Local Chrome required')
    if body['action'] == 'login':
        cookies, agent = open_login_session(proxy=None, timeout=540)
        uid = verified_uid(cookies)
        session = {'cookies': cookies, 'user_agent': agent}
        if Client(Account('healthvideo', **session), proxy=False).check_session() is not True:
            return {'ok': False, 'code': 'session_expired'}
        return {'ok': True, 'uid': uid, 'session': session}
    session = body['session']
    uid = verified_uid(session['cookies'])
    if uid != body['account_id']:
        raise ValueError('Account mismatch')
    client = Client(Account('healthvideo', **session), proxy=False)
    if client.check_session() is not True:
        return {'ok': False, 'code': 'session_expired'}
    path = Path(body['path'])
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != body['sha256']:
            raise ValueError('Snapshot hash mismatch')
    if body['privacy'] not in ('private', 'public'):
        raise ValueError('Explicit visibility required')
    result = client.upload(path, body['caption'], visibility=body['privacy'],
                           allow_comment=False, allow_duet=False, allow_stitch=False)
    if any(not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', str(value))
           for value in (result.video_id, result.creation_id)):
        raise ValueError('Invalid acceptance identifiers')
    # Storage ID and status_code=0 are acceptance, never independent publication proof.
    return {'ok': True, 'status': 'pending_verification',
            'storage_video_id': str(result.video_id), 'creation_id': str(result.creation_id)}


def main():
    logging.disable(logging.CRITICAL)
    try:
        body = json.loads(sys.stdin.read(2_000_000))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = execute(body)
    except BaseException:  # noqa: BLE001 - SDK errors may contain secrets
        result = {'ok': False, 'message': 'TikTok browser operation failed; reconnect or check profile before retrying'}
    sys.stdout.write(json.dumps(result))


if __name__ == '__main__':
    main()
