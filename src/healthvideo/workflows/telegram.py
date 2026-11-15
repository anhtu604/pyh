"""Small optional Telegram transport. Diagnostics never include remote error bodies/URLs."""

import json
import logging
import os
import urllib.request
from http.client import HTTPException
from pathlib import Path
from uuid import uuid4


def configured() -> bool:
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    return bool(
        token
        and not (token.startswith('<') and token.endswith('>'))
        and chat_id
        and chat_id.lstrip('-').isdigit()
    )


def request(method: str, payload: dict, *, transport=None, timeout: float = 10) -> dict | None:
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    if not token:
        return None
    try:
        req = urllib.request.Request(
            f'https://api.telegram.org/bot{token}/{method}',
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json'}, method='POST',
        )
        with (transport or urllib.request.urlopen)(req, timeout=timeout) as response:
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


def _split_chunks(text: str, limit: int = 3900) -> list[str]:
    clean = str(text or '').strip()
    if not clean:
        return []
    chunks: list[str] = []
    while len(clean) > limit:
        cut = clean.rfind('\n', 0, limit + 1)
        if cut < limit // 2:
            cut = clean.rfind(' ', 0, limit + 1)
        if cut <= 0:
            cut = limit
        chunks.append(clean[:cut].rstrip())
        clean = clean[cut:].lstrip()
    if clean:
        chunks.append(clean)
    return chunks


def send_text(
    text: str,
    *,
    reply_markup: dict | None = None,
    chat_id: str | None = None,
    transport=None,
    timeout: float = 10,
) -> dict | None:
    """Send plain UTF-8 text via Telegram Bot API, chunked at <= 3900 chars."""
    target_chat = str(chat_id if chat_id is not None else os.environ.get('TELEGRAM_CHAT_ID', '')).strip()
    if not target_chat or not os.environ.get('TELEGRAM_BOT_TOKEN', '').strip():
        return None
    chunks = _split_chunks(text)
    if not chunks:
        return None
    last: dict | None = None
    for idx, chunk in enumerate(chunks):
        payload: dict[str, object] = {'chat_id': target_chat, 'text': chunk}
        if reply_markup is not None and idx == len(chunks) - 1:
            payload['reply_markup'] = reply_markup
        res = request('sendMessage', payload, transport=transport, timeout=timeout)
        if res is None:
            return None
        last = res
    return last


def _encode_multipart(
    fields: dict[str, str],
    file_field: str,
    file_path: Path,
    content_type: str,
) -> tuple[bytes, str]:
    boundary = f'----PYHBoundary{uuid4().hex}'
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f'{value}\r\n'.encode()
        )
    safe_name = file_path.name.replace('"', '_')
    parts.append(
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="{file_field}"; filename="{safe_name}"\r\n'
        f'Content-Type: {content_type}\r\n\r\n'.encode()
    )
    parts.append(file_path.read_bytes())
    parts.append(f'\r\n--{boundary}--\r\n'.encode())
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


def send_file(
    method: str,
    field_name: str,
    file_path: Path,
    *,
    caption: str = '',
    reply_markup: dict | None = None,
    chat_id: str | None = None,
    extra_fields: dict[str, str] | None = None,
    content_type: str = 'application/octet-stream',
    transport=None,
    timeout: float = 120,
) -> dict | None:
    """Upload a local media file via Telegram Bot API multipart/form-data."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    target_chat = str(chat_id if chat_id is not None else os.environ.get('TELEGRAM_CHAT_ID', '')).strip()
    if not token or not target_chat or not file_path.is_file():
        return None
    fields: dict[str, str] = {'chat_id': target_chat}
    clean_caption = str(caption or '').strip()
    if clean_caption:
        fields['caption'] = clean_caption[:1024]
    if reply_markup is not None:
        fields['reply_markup'] = json.dumps(reply_markup, ensure_ascii=False)
    if extra_fields:
        fields.update({k: str(v) for k, v in extra_fields.items()})
    try:
        body, mime = _encode_multipart(fields, field_name, file_path, content_type)
        req = urllib.request.Request(
            f'https://api.telegram.org/bot{token}/{method}',
            data=body,
            headers={'Content-Type': mime},
            method='POST',
        )
        with (transport or urllib.request.urlopen)(req, timeout=timeout) as response:
            data = json.loads(response.read())
        if isinstance(data, dict) and data.get('ok') is True:
            return data
    except (OSError, ValueError, HTTPException):
        logging.getLogger(__name__).warning('Telegram: gửi tệp thất bại (chi tiết đã ẩn).')
        return None
    logging.getLogger(__name__).warning('Telegram: gửi tệp thất bại (chi tiết đã ẩn).')
    return None


def send_video(
    video_path: Path,
    *,
    caption: str = '',
    reply_markup: dict | None = None,
    chat_id: str | None = None,
    transport=None,
    timeout: float = 120,
) -> dict | None:
    """Send an MP4 video streamable inside Telegram."""
    return send_file(
        'sendVideo',
        'video',
        video_path,
        caption=caption,
        reply_markup=reply_markup,
        chat_id=chat_id,
        extra_fields={'supports_streaming': 'true'},
        content_type='video/mp4',
        transport=transport,
        timeout=timeout,
    )


def send_photo(
    photo_path: Path,
    *,
    caption: str = '',
    reply_markup: dict | None = None,
    chat_id: str | None = None,
    transport=None,
    timeout: float = 60,
) -> dict | None:
    """Send a PNG/JPG preview frame or contact sheet to Telegram."""
    ext = photo_path.suffix.lower()
    mime = 'image/jpeg' if ext in {'.jpg', '.jpeg'} else 'image/png'
    return send_file(
        'sendPhoto',
        'photo',
        photo_path,
        caption=caption,
        reply_markup=reply_markup,
        chat_id=chat_id,
        content_type=mime,
        transport=transport,
        timeout=timeout,
    )


def delete_message(
    message_id: int | str,
    *,
    chat_id: str | None = None,
    transport=None,
) -> bool:
    """Best-effort deletion of a Telegram message (e.g., ephemeral PIN entries)."""
    target_chat = str(chat_id if chat_id is not None else os.environ.get('TELEGRAM_CHAT_ID', '')).strip()
    if not target_chat or not os.environ.get('TELEGRAM_BOT_TOKEN', '').strip():
        return False
    try:
        mid = int(message_id)
    except (TypeError, ValueError):
        return False
    return request('deleteMessage', {'chat_id': target_chat, 'message_id': mid}, transport=transport) is not None


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
