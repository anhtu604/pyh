"""Small optional Telegram transport. Diagnostics never include remote error bodies/URLs."""

import json
import logging
import os
import urllib.request
from http.client import HTTPException


def configured() -> bool:
    return bool(os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
                and os.environ.get('TELEGRAM_CHAT_ID', '').strip())


def request(method: str, payload: dict, *, transport=None) -> dict | None:
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    if not token:
        return None
    try:
        req = urllib.request.Request(
            f'https://api.telegram.org/bot{token}/{method}',
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json'}, method='POST',
        )
        with (transport or urllib.request.urlopen)(req, timeout=10) as response:
            data = json.loads(response.read())
        if isinstance(data, dict) and data.get('ok') is True:
            return data
    except (OSError, ValueError, HTTPException):
        # Even exception strings, class names and Telegram descriptions may contain the URL/token.
        logging.getLogger(__name__).warning('Telegram: yêu cầu thất bại (chi tiết đã ẩn).')
        return None
    logging.getLogger(__name__).warning('Telegram: yêu cầu thất bại (chi tiết đã ẩn).')
    return None


def event_label(event: str) -> str:
    # Allowlist events: blocked diagnostics may contain claims, script excerpts or secrets.
    return {'medical': 'medical', 'video': 'video', 'đã đóng gói': 'đã đóng gói',
            'tin thử': 'tin thử'}.get(event, 'bị chặn')


def send(title: str, event: str, *, transport=None) -> bool:
    if not configured():
        return False
    return request('sendMessage', {
        'chat_id': os.environ['TELEGRAM_CHAT_ID'],
        'text': f'{title}\n{event_label(event)}\nChạy: healthvideo duyet',
    }, transport=transport) is not None


def setup(*, echo=print, transport=None) -> None:
    echo('1. Mở Telegram, nhắn @BotFather: /newbot và làm theo hướng dẫn để tạo bot.')
    echo('2. Lấy token, giữ kín và điền TELEGRAM_BOT_TOKEN vào .env.')
    echo('3. Mở bot vừa tạo và nhắn một tin (ví dụ /start).')
    echo('4. Gọi getUpdates để lấy chat_id. Chạy lại healthvideo notify-setup sau khi có token trong .env.')
    data = request('getUpdates', {}, transport=transport)
    ids = set()
    if data:
        for update in data.get('result', []):
            for key in ('message', 'edited_message', 'channel_post', 'my_chat_member'):
                chat_id = update.get(key, {}).get('chat', {}).get('id')
                if isinstance(chat_id, int):
                    ids.add(chat_id)
        for chat_id in sorted(ids):
            echo(f'chat_id: {chat_id}')
        if not ids:
            echo('Chưa tìm thấy chat_id; hãy nhắn bot rồi thử lại (kiểm tra bot không dùng webhook).')
    echo('5. Tự điền hai dòng vào .env; lệnh này không ghi file:')
    echo('TELEGRAM_BOT_TOKEN=<token từ BotFather>\nTELEGRAM_CHAT_ID=<chat_id>')
