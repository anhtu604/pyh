"""Two-way Telegram Bot bridge for PYH's Leader Coordinator (chat.py)."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

import yaml

from healthvideo import process
from healthvideo.agents import invoke_with_failover
from healthvideo.domain.project_v2 import ProjectManifestV2
from healthvideo.env import (
    background_popen_kwargs,
    background_python,
    child_env,
    hide_child_consoles,
    load_dotenv,
)
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import (
    channel_analytics,
    chat,
    dashboard,
    decision_card,
    factory,
    researcher,
    telegram,
)

logger = logging.getLogger(__name__)

_CB_MAX_BYTES = 64
_CB_HISTORY_LIMIT = 200
_MAX_TELEGRAM_VIDEO_BYTES = 48 * 1024 * 1024
_PIN_LIMITER = dashboard.PinLimiter()

_PIN_RE = re.compile(
    r"(?i)(?:\bpin\b|m[aã]\s*pin|m[aậ]t\s*kh[aẩ]u|mat\s*khau|[đd][oổ]i\s*pin|nh[aậ]p\s*pin|set[-_\s]?pin)"
)
_GATE_APPROVE_RE = re.compile(
    r"(?i)(?:duy[eệ]t\s*(?:c[oổ]ng|y\s*khoa|video|k[iị]ch\s*b[aả]n)|"
    r"duyet\s*(?:cong|y\s*khoa|video|kich\s*ban)|"
    r"approve\s*(?:medical|video|gate)|"
    r"m[oở]\s*c[oổ]ng\s*(?:y\s*khoa|video)|mo\s*cong|"
    r"v[uư][oợ]t\s*c[oổ]ng|vuot\s*cong|b[oỏ]\s*qua\s*c[oổ]ng)"
)

COMMANDS: list[dict[str, str]] = [
    {"command": "start", "description": "Bắt đầu & hướng dẫn kết nối Trưởng nhóm Điều phối"},
    {"command": "status", "description": "Tổng quan xưởng, agent đang chạy & cổng chờ duyệt"},
    {"command": "duyet", "description": "Xem gói duyệt & duyệt/từ chối cổng Y khoa, Video bằng PIN"},
    {"command": "video", "description": "Xem video hoàn chỉnh trên Telegram (/video [slug])"},
    {"command": "clips", "description": "Xem các clip Shorts 9:16 (/clips [slug])"},
    {"command": "frames", "description": "Xem ảnh storyboard / contact sheet (/frames [slug])"},
    {"command": "script", "description": "Xem tóm tắt kịch bản & bằng chứng (/script [slug])"},
    {"command": "inbox", "description": "Chủ đề chờ chọn (Tier A/B) & đưa vào hàng đợi"},
    {"command": "projects", "description": "Danh sách project & chọn ngữ cảnh trò chuyện"},
    {"command": "project", "description": "Chuyển ngữ cảnh sang một project (/project <slug>)"},
    {"command": "chung", "description": "Chuyển ngữ cảnh về Toàn xưởng"},
    {"command": "sync", "description": "Đồng bộ Google Sheet chủ đề & hiệu quả kênh"},
    {"command": "channel", "description": "Tóm tắt số liệu hiệu quả kênh YouTube"},
    {"command": "xuong_start", "description": "Bật xưởng sản xuất tự động chạy nền"},
    {"command": "xuong_stop", "description": "Dừng xưởng chạy nền"},
    {"command": "huy", "description": "Hủy thao tác nhập PIN / từ chối đang chờ"},
    {"command": "help", "description": "Xem danh sách lệnh & cách giao việc cho Leader"},
]


class TelegramBotAlreadyRunning(RuntimeError):
    """Raised when a Telegram bot polling daemon already holds the lock."""


def lock_path(root: Path) -> Path:
    return root / "topics" / ".telegram-bot.lock"


def state_path(root: Path) -> Path:
    return root / "cache" / "telegram" / "bot-state.yaml"


def _ensure_env_loaded(root: Path) -> None:
    if not telegram.configured():
        env_file = root / ".env"
        if env_file.is_file():
            load_dotenv(env_file)


def running_pid(root: Path) -> int | None:
    try:
        data = json.loads(lock_path(root).read_text(encoding="utf-8"))
        pid = int(data["pid"])
        token = factory._process_token(pid)
        return pid if token and token == data.get("process_token") else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


class TelegramBotLock:
    """Single-instance kernel lock for the Telegram long-polling daemon."""

    def __init__(self, root: Path):
        self.root = root
        self.stream = None

    def __enter__(self) -> Self:
        path = lock_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("a+b")
        try:
            if sys.platform == "win32":
                import msvcrt

                self.stream.seek(65536)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.stream.close()
            raise TelegramBotAlreadyRunning(
                f"Telegram bot đang chạy (PID {running_pid(self.root) or 'đang khởi động'})."
            ) from error
        self.stream.seek(0)
        self.stream.truncate()
        self.stream.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "started_at": datetime.now(UTC).isoformat(),
                    "process_token": factory._process_token(os.getpid()),
                }
            ).encode("utf-8")
        )
        self.stream.flush()
        return self

    def __exit__(self, *args: object) -> None:
        if self.stream is None:
            return
        self.stream.seek(0)
        self.stream.truncate()
        self.stream.flush()
        if sys.platform == "win32":
            import msvcrt

            self.stream.seek(65536)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        self.stream.close()


def _default_state() -> dict[str, Any]:
    return {
        "offset": None,
        "active_slug": None,
        "commands_registered": False,
        "started_at": None,
        "last_poll_at": None,
        "last_update_id": None,
        "last_error": None,
        "callbacks": {},
        "review_sessions": {},
        "pending_gate_input": None,
    }


def load_state(root: Path) -> dict[str, Any]:
    path = state_path(root)
    base = _default_state()
    if not path.is_file():
        return base
    try:
        raw = read_yaml(path)
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        return base
    if not isinstance(raw, dict):
        return base
    merged = {**base, **raw}
    if not isinstance(merged.get("callbacks"), dict):
        merged["callbacks"] = {}
    return merged


def save_state(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    clean = dict(state)
    callbacks = dict(clean.get("callbacks") or {})
    if len(callbacks) > _CB_HISTORY_LIMIT:
        keys = list(callbacks.keys())[-_CB_HISTORY_LIMIT:]
        callbacks = {k: callbacks[k] for k in keys}
    clean["callbacks"] = callbacks
    write_yaml_atomic(state_path(root), clean)
    return clean


def bot_status(root: Path) -> dict[str, Any]:
    _ensure_env_loaded(root)
    pid = running_pid(root)
    state = load_state(root)
    return {
        "configured": telegram.configured(),
        "running": pid is not None,
        "pid": pid,
        "active_slug": state.get("active_slug"),
        "last_poll_at": state.get("last_poll_at"),
        "last_update_id": state.get("last_update_id"),
        "last_error": state.get("last_error"),
    }


def start_background(root: Path, *, poll_timeout: int = 25) -> int:
    hide_child_consoles()
    _ensure_env_loaded(root)
    if not telegram.configured():
        raise ValueError("Chưa cấu hình TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID trong .env.")
    existing = running_pid(root)
    if existing:
        return existing
    env = child_env()
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        val = os.environ.get(key, "").strip()
        if val:
            env[key] = val
    import_paths = [str(Path(__file__).resolve().parents[2])]
    import_paths.extend(str(Path(p).resolve()) for p in env.get("PYTHONPATH", "").split(os.pathsep) if p)
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(import_paths))
    proc = subprocess.Popen(
        [
            background_python(),
            "-c",
            "from healthvideo.cli import app; app()",
            "telegram",
            "run",
            "--root",
            str(root.resolve()),
            "--poll-timeout",
            str(poll_timeout),
        ],
        cwd=root.resolve(),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        **background_popen_kwargs(),
    )
    for _ in range(100):
        pid = running_pid(root)
        if pid:
            return pid
        if proc.poll() is not None:
            raise RuntimeError("Không khởi động được Telegram bot; kiểm tra cấu hình .env hoặc mạng.")
        time.sleep(0.05)
    raise RuntimeError(f"Telegram bot PID {proc.pid} chưa sẵn sàng.")


def stop_background(root: Path) -> int | None:
    pid = running_pid(root)
    if not pid:
        return None
    if not process.terminate_process_tree(pid):
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)
    return pid


def ensure_background(root: Path) -> int | None:
    """Start the Telegram Leader bot in background when configured; never block callers on errors."""
    _ensure_env_loaded(root)
    if not telegram.configured():
        return None
    existing = running_pid(root)
    if existing:
        return existing
    try:
        return start_background(root)
    except (OSError, RuntimeError, ValueError, TelegramBotAlreadyRunning):
        return None


def _allowed_chat_id() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def _is_pin_or_gate_request(text: str) -> bool:
    return bool(_PIN_RE.search(text) or _GATE_APPROVE_RE.search(text))


def _pin_refusal_text() -> str:
    return (
        "⛔ Bảo mật cổng duyệt: Khung chat thường KHÔNG nhận mã PIN trực tiếp.\n"
        "Để xem video/kịch bản và duyệt hoặc từ chối cổng bằng PIN (tin nhắn PIN sẽ tự xóa ngay), anh hãy bấm /duyet"
    )


def _cb_token(state: dict[str, Any], prefix: str, entry: dict[str, Any], *, direct_value: str | None = None) -> str:
    if direct_value is not None:
        raw = f"{prefix}:{direct_value}"
        if len(raw.encode("utf-8")) <= _CB_MAX_BYTES:
            state.setdefault("callbacks", {})[raw] = entry
            return raw
    digest_seed = json.dumps({"p": prefix, **entry}, ensure_ascii=False, sort_keys=True)
    token = hashlib.sha1(digest_seed.encode("utf-8")).hexdigest()[:12]
    key = f"{prefix}:{token}"
    state.setdefault("callbacks", {})[key] = entry
    return key


def _resolve_callback(state: dict[str, Any], data: str) -> dict[str, Any] | None:
    saved = (state.get("callbacks") or {}).get(data)
    if isinstance(saved, dict):
        return saved
    if ":" not in data:
        return None
    prefix, rest = data.split(":", 1)
    if prefix in {"cfm", "dis"} and rest:
        return {"kind": prefix, "slug": state.get("active_slug"), "msg_id": rest}
    if prefix == "prm" and rest:
        return {"kind": "prm", "inbox_slug": rest}
    if prefix in {"prj", "vid", "clp", "scr", "duy", "frm"} and rest:
        return {"kind": prefix, "slug": rest}
    if prefix == "act" and rest:
        return {"kind": "act", "action": rest}
    return None


def _inline_markup(rows: list[list[tuple[str, str]]]) -> dict[str, Any] | None:
    keyboard = [
        [{"text": label, "callback_data": data} for label, data in row if len(data.encode("utf-8")) <= _CB_MAX_BYTES]
        for row in rows
        if row
    ]
    keyboard = [row for row in keyboard if row]
    return {"inline_keyboard": keyboard} if keyboard else None


def prime_offset_if_needed(
    root: Path,
    state: dict[str, Any],
    *,
    req: Callable[..., dict | None] = telegram.request,
) -> dict[str, Any]:
    if state.get("offset") is not None:
        return state
    data = req("getUpdates", {"timeout": 0, "limit": 100})
    updates = data.get("result", []) if isinstance(data, dict) else []
    max_id = max((int(item["update_id"]) for item in updates if isinstance(item, dict) and "update_id" in item), default=-1)
    state["offset"] = max_id + 1
    save_state(root, state)
    return state


def register_commands(*, req: Callable[..., dict | None] = telegram.request) -> bool:
    res = req("setMyCommands", {"commands": COMMANDS})
    return bool(isinstance(res, dict) and res.get("ok") is True)


@contextlib.contextmanager
def _typing_indicator(
    chat_id: str,
    *,
    req: Callable[..., dict | None] = telegram.request,
    interval: float = 4.0,
    enabled: bool = True,
):
    if not enabled or not chat_id:
        yield
        return
    stop = threading.Event()

    def _beat() -> None:
        while not stop.is_set():
            with contextlib.suppress(Exception):
                req("sendChatAction", {"chat_id": chat_id, "action": "typing"})
            if stop.wait(interval):
                break

    thread = threading.Thread(target=_beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1.0)


def _resolve_scope(root: Path, text: str, active_slug: str | None) -> tuple[str | None, str]:
    known = {path.name for path, _ in factory.projects(root)}
    cleaned = text
    chosen = active_slug
    for match in re.finditer(r"(?:^|\s)#([a-z0-9][a-z0-9-]*)", text):
        tag = match.group(1)
        if tag == "chung":
            chosen = None
            cleaned = (cleaned[: match.start()] + " " + cleaned[match.end() :]).strip()
            break
        if tag in known:
            chosen = tag
            cleaned = (cleaned[: match.start()] + " " + cleaned[match.end() :]).strip()
            break
    return chosen, cleaned


def _format_exec_results(exec_results: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in exec_results:
        if not isinstance(item, dict):
            continue
        if item.get("role") and item.get("step"):
            status_lbl = item.get("status") or ("lỗi" if item.get("error") else "xong")
            line = f"- {item['role']} · {item['step']}: {status_lbl}"
            if item.get("error"):
                line += f" ({item['error']})"
            lines.append(line)
            continue
        action = str(item.get("action") or "")
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        if action == "sync_sheet_topics":
            lines.append(
                f"- Đồng bộ Sheet chủ đề: +{result.get('synced_count', 0)} mục "
                f"(Tổng {result.get('total', 0)} · Tier A: {result.get('tier_a', 0)})"
            )
            if result.get("errors"):
                lines.append(f"  Cảnh báo: {'; '.join(str(e) for e in result['errors'][:3])}")
        elif action == "discover_topics":
            lines.append(f"- Researcher tìm thêm: {len(result.get('added') or [])} chủ đề mới vào inbox")
        elif action == "analyze_channel":
            ins = result.get("insights") if isinstance(result.get("insights"), dict) else {}
            summary = str(ins.get("summary") or "").strip()
            lines.append(f"- Phân tích kênh (+{result.get('added_topics', 0)} gợi ý): {summary[:240]}")
        elif action == "promote_inbox_topic":
            entry = result.get("entry") if isinstance(result.get("entry"), dict) else {}
            lines.append(f"- Đã đưa vào hàng đợi sản xuất: {entry.get('slug') or item.get('action')}")
        elif action == "cancel_job":
            lines.append(f"- Đã dừng tác vụ: {result.get('job_id') or 'đang chạy'}")
        elif action == "retry_project":
            lines.append(f"- Đã đưa project vào chế độ chạy lại: {result.get('slug') or ''}")
        elif action:
            lines.append(f"- {action}: đã xong")
    return lines


def _coordinator_reply_message(
    root: Path,
    state: dict[str, Any],
    scope_slug: str | None,
    msg: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    scope_label = scope_slug or "Toàn xưởng"
    if msg.get("status") == "failed" or msg.get("error"):
        return f"⚠️ [{scope_label}] {msg.get('error') or 'Điều phối viên gặp lỗi.'}", None

    parts = [f"👔 Trưởng nhóm Điều phối [{scope_label}]\n{msg.get('text', '')}"]
    exec_results = msg.get("execution_results") or []
    if exec_results:
        rendered = _format_exec_results(exec_results)
        if rendered:
            parts.append("Kết quả thực thi:\n" + "\n".join(rendered))

    rows: list[list[tuple[str, str]]] = []
    action = msg.get("action")
    msg_id = str(msg.get("id") or "")
    if msg.get("status") == "pending" and action and action != "none" and action != "ask":
        brief = str(msg.get("brief") or action).strip()
        parts.append(f"Đề xuất chờ anh xác nhận: {brief}")
        cfm = _cb_token(
            state,
            "cfm",
            {"kind": "cfm", "slug": scope_slug, "msg_id": msg_id},
            direct_value=msg_id,
        )
        dis = _cb_token(
            state,
            "dis",
            {"kind": "dis", "slug": scope_slug, "msg_id": msg_id},
            direct_value=msg_id,
        )
        rows.append([("✅ Xác nhận thực hiện", cfm), ("❌ Bỏ qua", dis)])

    options: list[str] = []
    for opt in msg.get("options") or []:
        lbl = opt.get("label") if isinstance(opt, dict) else opt
        clean_lbl = str(lbl or "").strip()
        if clean_lbl:
            options.append(clean_lbl)
    opt_row: list[tuple[str, str]] = []
    for opt in options[:6]:
        cb = _cb_token(state, "opt", {"kind": "opt", "slug": scope_slug, "text": opt})
        opt_row.append((opt[:32], cb))
        if len(opt_row) == 2:
            rows.append(opt_row)
            opt_row = []
    if opt_row:
        rows.append(opt_row)

    save_state(root, state)
    return "\n\n".join(parts), _inline_markup(rows)


def prepare_telegram_video(
    root: Path,
    project_dir: Path,
    video_path: Path,
    *,
    runner: Callable[..., Any] = process.run_bounded,
) -> Path:
    """Return video_path if <= 48 MB, otherwise transcode a cached 720p faststart MP4."""
    if video_path.stat().st_size <= _MAX_TELEGRAM_VIDEO_BYTES:
        return video_path
    preview_dir = root / "cache" / "telegram" / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    mtime_ns = video_path.stat().st_mtime_ns
    preview_path = preview_dir / f"{project_dir.name}-{video_path.stem}-{mtime_ns}.mp4"
    if preview_path.is_file() and preview_path.stat().st_size > 0:
        return preview_path
    tmp_path = preview_dir / f".{preview_path.name}.tmp.mp4"
    tmp_path.unlink(missing_ok=True)
    runner(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            "scale=-2:720",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-b:v",
            "1200k",
            "-maxrate",
            "1500k",
            "-bufsize",
            "3000k",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-movflags",
            "+faststart",
            str(tmp_path),
        ],
        timeout=300,
        capture_output=True,
        check=True,
    )
    os.replace(tmp_path, preview_path)
    return preview_path


def _target_project_slug(root: Path, state: dict[str, Any], arg: str = "") -> str | None:
    clean = arg.strip().lstrip("#")
    if clean:
        return clean
    if state.get("active_slug"):
        return str(state["active_slug"])
    items = list(factory.projects(root))
    if len(items) == 1:
        return items[0][0].name
    return None


def _load_project(root: Path, slug: str | None) -> tuple[Path, ProjectManifestV2, Path] | None:
    if not slug:
        return None
    project_dir = root / "projects" / slug
    manifest_file = project_dir / "project.yaml"
    if not manifest_file.is_file():
        return None
    project = ProjectManifestV2.model_validate(read_yaml(manifest_file))
    rev = project_dir / "revisions" / project.active_revision
    return project_dir, project, rev


def _project_action_buttons(
    state: dict[str, Any],
    slug: str,
    project: ProjectManifestV2,
    rev: Path,
    *,
    include_duyet: bool = True,
) -> list[list[tuple[str, str]]]:
    rows: list[list[tuple[str, str]]] = []
    media_row: list[tuple[str, str]] = []
    if (rev / "renders/clips").is_dir() and any((rev / "renders/clips").glob("*.mp4")):
        media_row.append(("📱 Xem Shorts", _cb_token(state, "clp", {"kind": "clp", "slug": slug}, direct_value=slug)))
    if (rev / "renders/review-frames").is_dir() and any((rev / "renders/review-frames").glob("*/sheet-*.png")):
        media_row.append(("🖼️ Bảng ảnh cảnh", _cb_token(state, "frm", {"kind": "frm", "slug": slug}, direct_value=slug)))
    media_row.append(("📜 Kịch bản & Nguồn", _cb_token(state, "scr", {"kind": "scr", "slug": slug}, direct_value=slug)))
    if media_row:
        rows.append(media_row[:3])
    if include_duyet and (gate := factory.gate_for_project(rev.parent.parent, project)) is not None:
        duy_cb = _cb_token(state, "duy", {"kind": "duy", "slug": slug}, direct_value=slug)
        rows.append([(f"🪪 Mở thẻ duyệt ({gate})", duy_cb)])
    return rows


def _send_project_video(
    root: Path,
    state: dict[str, Any],
    slug: str | None,
    chat_id: str,
    *,
    send_fn: Callable[..., dict | None],
    send_video_fn: Callable[..., dict | None] = telegram.send_video,
    send_photo_fn: Callable[..., dict | None] = telegram.send_photo,
    runner: Callable[..., Any] = process.run_bounded,
) -> None:
    if not slug:
        _send_projects(root, state, chat_id, send_fn)
        return
    loaded = _load_project(root, slug)
    if loaded is None:
        send_fn(f"❌ Không tìm thấy project `{slug}`.", chat_id=chat_id)
        return
    project_dir, project, rev = loaded
    video_path = rev / "renders" / "video.mp4"
    rows = _project_action_buttons(state, slug, project, rev)
    save_state(root, state)

    if not video_path.is_file():
        sheets = sorted((rev / "renders/review-frames").glob("*/sheet-*.png")) if (rev / "renders/review-frames").is_dir() else []
        if sheets:
            send_photo_fn(
                sheets[0],
                caption=f"🖼️ [{slug}] Chưa có video.mp4 (trạng thái: {project.state.value}). Gửi trước bảng ảnh storyboard.",
                reply_markup=_inline_markup(rows),
                chat_id=chat_id,
            )
            return
        send_fn(
            f"ℹ️ [{slug}] Chưa có file `renders/video.mp4` (trạng thái hiện tại: `{project.state.value}`).",
            reply_markup=_inline_markup(rows),
            chat_id=chat_id,
        )
        return

    try:
        ready_path = prepare_telegram_video(root, project_dir, video_path, runner=runner)
    except (OSError, ValueError, RuntimeError) as exc:
        send_fn(f"⚠️ Không chuẩn bị được video preview cho `{slug}`: {exc}", chat_id=chat_id)
        return

    title = factory.project_title(project_dir, project)
    scenes = dashboard.timeline(project_dir)
    caption_lines = [
        f"🎬 {title} (`{slug}` · rev {project.active_revision})",
        f"Trạng thái: {project.state.value}",
    ]
    if scenes:
        markers = [f"{s['scene']} ({int(s['start_s'])}s)" for s in scenes[:10] if s.get("scene")]
        if markers:
            caption_lines.append("Cảnh: " + ", ".join(markers))
    res = send_video_fn(
        ready_path,
        caption="\n".join(caption_lines),
        reply_markup=_inline_markup(rows),
        chat_id=chat_id,
    )
    if res is None:
        send_fn(f"⚠️ Không gửi được video `{ready_path.name}` lên Telegram.", chat_id=chat_id)


def _send_project_clips(
    root: Path,
    state: dict[str, Any],
    slug: str | None,
    chat_id: str,
    *,
    send_fn: Callable[..., dict | None],
    send_video_fn: Callable[..., dict | None] = telegram.send_video,
    runner: Callable[..., Any] = process.run_bounded,
) -> None:
    if not slug:
        _send_projects(root, state, chat_id, send_fn)
        return
    loaded = _load_project(root, slug)
    if loaded is None:
        send_fn(f"❌ Không tìm thấy project `{slug}`.", chat_id=chat_id)
        return
    project_dir, project, rev = loaded
    clips = sorted((rev / "renders/clips").glob("*.mp4")) if (rev / "renders/clips").is_dir() else []
    if not clips:
        send_fn(f"📱 [{slug}] Chưa có Shorts clip trong `renders/clips/`.", chat_id=chat_id)
        return
    for idx, clip in enumerate(clips[:5], start=1):
        ready = prepare_telegram_video(root, project_dir, clip, runner=runner)
        markup = (
            _inline_markup(_project_action_buttons(state, slug, project, rev))
            if idx == min(len(clips), 5)
            else None
        )
        send_video_fn(ready, caption=f"📱 [{slug}] Clip {idx}/{len(clips)}: {clip.name}", reply_markup=markup, chat_id=chat_id)
    save_state(root, state)


def _send_project_frames(
    root: Path,
    state: dict[str, Any],
    slug: str | None,
    chat_id: str,
    *,
    send_fn: Callable[..., dict | None],
    send_photo_fn: Callable[..., dict | None] = telegram.send_photo,
) -> None:
    if not slug:
        _send_projects(root, state, chat_id, send_fn)
        return
    loaded = _load_project(root, slug)
    if loaded is None:
        send_fn(f"❌ Không tìm thấy project `{slug}`.", chat_id=chat_id)
        return
    _, project, rev = loaded
    sheets = sorted((rev / "renders/review-frames").glob("*/sheet-*.png")) if (rev / "renders/review-frames").is_dir() else []
    if not sheets:
        send_fn(f"🖼️ [{slug}] Chưa có bảng ảnh storyboard trong `renders/review-frames/`.", chat_id=chat_id)
        return
    for idx, sheet in enumerate(sheets[:4], start=1):
        markup = (
            _inline_markup(_project_action_buttons(state, slug, project, rev))
            if idx == min(len(sheets), 4)
            else None
        )
        send_photo_fn(sheet, caption=f"🖼️ [{slug}] {sheet.parent.name}/{sheet.name}", reply_markup=markup, chat_id=chat_id)
    save_state(root, state)


def _send_project_script(
    root: Path,
    state: dict[str, Any],
    slug: str | None,
    chat_id: str,
    *,
    send_fn: Callable[..., dict | None],
) -> None:
    if not slug:
        _send_projects(root, state, chat_id, send_fn)
        return
    loaded = _load_project(root, slug)
    if loaded is None:
        send_fn(f"❌ Không tìm thấy project `{slug}`.", chat_id=chat_id)
        return
    project_dir, project, rev = loaded
    title = factory.project_title(project_dir, project)
    script_data = read_yaml(rev / "script/script.yaml") if (rev / "script/script.yaml").is_file() else {}
    ledger_data = read_yaml(rev / "evidence/ledger.yaml") if (rev / "evidence/ledger.yaml").is_file() else {}
    posts_data = read_yaml(rev / "posts/posts.yaml") if (rev / "posts/posts.yaml").is_file() else {}

    claims = ledger_data.get("claims", []) if isinstance(ledger_data, dict) else []
    records = ledger_data.get("records", []) if isinstance(ledger_data, dict) else []
    script_lines = script_data.get("lines", []) if isinstance(script_data, dict) else []
    lines_out = [
        f"📜 Kịch bản & Bằng chứng: {title} (`{slug}` · rev {project.active_revision})",
        f"Trạng thái: {project.state.value} · Claims: {len(claims)} · Nguồn: {len(records)} · Câu thoại: {len(script_lines)}",
    ]
    if claims:
        lines_out.append("\n🧪 Claim chính:")
        for c in claims[:5]:
            lines_out.append(f"- [{c.get('id', '?')}] {str(c.get('text_public') or '').strip()}")
    if script_lines:
        lines_out.append("\n🎙️ Kịch bản:")
        for line in script_lines[:18]:
            cid = f" ({line['claim_id']})" if line.get("claim_id") else ""
            lines_out.append(f"{line.get('id', '?')}{cid}: {str(line.get('text') or '').strip()}")
        if len(script_lines) > 18:
            lines_out.append(f"... (còn {len(script_lines) - 18} câu nữa)")
    if isinstance(posts_data, dict) and posts_data.get("title"):
        lines_out.append(f"\n📝 Tiêu đề bài đăng: {posts_data['title']}")

    rows: list[list[tuple[str, str]]] = []
    if (rev / "renders/video.mp4").is_file():
        rows.append([("🎬 Xem video", _cb_token(state, "vid", {"kind": "vid", "slug": slug}, direct_value=slug))])
    if (gate := factory.gate_for_project(project_dir, project)) is not None:
        rows.append([(f"🪪 Mở thẻ duyệt ({gate})", _cb_token(state, "duy", {"kind": "duy", "slug": slug}, direct_value=slug))])
    save_state(root, state)
    send_fn("\n".join(lines_out), reply_markup=_inline_markup(rows), chat_id=chat_id)


def _init_review_session(
    state: dict[str, Any],
    slug: str,
    revision: str,
    card: dict[str, Any] | None,
) -> dict[str, Any]:
    sessions = state.setdefault("review_sessions", {})
    existing = sessions.get(slug) if isinstance(sessions.get(slug), dict) else None
    if existing and existing.get("revision") == revision:
        choices = dict(existing.get("choices") or {})
        other = str(existing.get("other") or "")
    else:
        choices = {}
        other = ""
    valid_choices: dict[str, str] = {}
    for item in (card or {}).get("decisions", []):
        did = item["id"]
        valid_ids = [opt["id"] for opt in item["options"]]
        if choices.get(did) in valid_ids:
            valid_choices[did] = choices[did]
        else:
            default = item.get("selected") or next((o["id"] for o in item["options"] if o.get("keep")), item["options"][0]["id"])
            valid_choices[did] = default
    session = {"revision": revision, "choices": valid_choices, "other": other}
    sessions[slug] = session
    return session


def _send_gate_review(
    root: Path,
    state: dict[str, Any],
    slug: str | None,
    chat_id: str,
    *,
    send_fn: Callable[..., dict | None],
) -> None:
    if not slug:
        pending = [
            (p.name, proj, gate)
            for p, proj in factory.projects(root)
            if (gate := factory.gate_for_project(p, proj)) is not None
        ]
        if not pending:
            send_fn("✅ Hiện không có project nào đang chờ bác sĩ duyệt cổng.", chat_id=chat_id)
            return
        if len(pending) > 1:
            lines = [f"🪪 Có {len(pending)} project đang chờ duyệt cổng:"]
            rows: list[list[tuple[str, str]]] = []
            for s, proj, gate in pending[:8]:
                lines.append(f"- `{s}` · cổng `{gate}` (rev {proj.active_revision})")
                cb = _cb_token(state, "duy", {"kind": "duy", "slug": s}, direct_value=s)
                rows.append([(f"🪪 Duyệt {s[:22]} ({gate})", cb)])
            save_state(root, state)
            send_fn("\n".join(lines), reply_markup=_inline_markup(rows), chat_id=chat_id)
            return
        slug = pending[0][0]

    loaded = _load_project(root, slug)
    if loaded is None:
        send_fn(f"❌ Không tìm thấy project `{slug}`.", chat_id=chat_id)
        return
    project_dir, project, rev = loaded
    gate = factory.gate_for_project(project_dir, project)
    if gate is None:
        if project.state in factory.GATES:
            send_fn(
                f"⚠️ Project `{slug}` ở trạng thái `{project.state.value}` nhưng chưa đạt kiểm duyệt tự động (Trạm 07/12) cho dữ liệu hiện hành.",
                chat_id=chat_id,
            )
        else:
            send_fn(f"ℹ️ Project `{slug}` hiện ở trạng thái `{project.state.value}`, không ở cổng duyệt.", chat_id=chat_id)
        return
    title = factory.project_title(project_dir, project)
    card = decision_card.card(project_dir)
    session = _init_review_session(state, slug, project.active_revision, card)
    lines = [
        f"🪪 Gói duyệt cổng `{gate}` · {title} (`{slug}` · rev {project.active_revision})",
    ]
    if gate == "medical":
        ledger = read_yaml(rev / "evidence/ledger.yaml") if (rev / "evidence/ledger.yaml").is_file() else {}
        script = read_yaml(rev / "script/script.yaml") if (rev / "script/script.yaml").is_file() else {}
        claims = ledger.get("claims", []) if isinstance(ledger, dict) else []
        records = ledger.get("records", []) if isinstance(ledger, dict) else []
        s_lines = script.get("lines", []) if isinstance(script, dict) else []
        lines.append(f"Claims: {len(claims)} · Nguồn: {len(records)} · Câu thoại: {len(s_lines)}")
        if s_lines:
            lines.append("Mở đầu: " + str(s_lines[0].get("text") or "").strip()[:180])
    else:
        qa = read_yaml(rev / "reviews/video-qa.json") if (rev / "reviews/video-qa.json").is_file() else {}
        posts = read_yaml(rev / "posts/posts.yaml") if (rev / "posts/posts.yaml").is_file() else {}
        scenes = dashboard.timeline(project_dir)
        dur = f"{scenes[-1]['end_s']:.1f}s" if scenes else "chưa rõ"
        qa_status = qa.get("status", "chưa có QA") if isinstance(qa, dict) else "chưa có QA"
        lines.append(f"Thời lượng: {dur} · QA: {qa_status}")
        if isinstance(posts, dict) and posts.get("title"):
            lines.append(f"Tiêu đề đăng: {posts['title']}")

    if card and card.get("checked"):
        lines.append("Agent kiểm: " + "; ".join(str(x) for x in card["checked"][:4]))
    if card and card.get("followup"):
        lines.append(f"✨ {card['followup']}")

    rows: list[list[tuple[str, str]]] = []
    decisions = (card or {}).get("decisions", [])
    all_keep = not session.get("other")
    for item in decisions:
        selected_id = session["choices"].get(item["id"])
        lines.append(f"\n❓ {item['id']} ({item['where']}): {item['question']}")
        lines.append(f"   Lý do khó: {item['why_hard']}")
        opt_row: list[tuple[str, str]] = []
        for opt in item["options"]:
            picked = opt["id"] == selected_id
            if picked and not opt.get("keep"):
                all_keep = False
            mark = "✓ " if picked else ""
            lines.append(f"   {mark}{opt['id']}: {opt['label']} — {opt['effect']}")
            cb = _cb_token(
                state,
                "dopt",
                {"kind": "dopt", "slug": slug, "decision_id": item["id"], "option_id": opt["id"]},
            )
            opt_row.append((f"{mark}{item['id']}·{opt['id']}: {opt['label'][:20]}", cb))
        rows.append(opt_row)

    if all_keep:
        mode = "card" if decisions else "approve"
        gact_approve = _cb_token(state, "gact", {"kind": "gact", "slug": slug, "revision": project.active_revision, "mode": mode})
        approve_row = [("✅ Duyệt cổng (PIN)", gact_approve)]
        if gate == "video":
            gact_pron = _cb_token(
                state,
                "gact",
                {"kind": "gact", "slug": slug, "revision": project.active_revision, "mode": "approve_pronunciation"},
            )
            approve_row.append(("🔊 Duyệt + Phát âm (PIN)", gact_pron))
        rows.append(approve_row)
    else:
        gact_fix = _cb_token(state, "gact", {"kind": "gact", "slug": slug, "revision": project.active_revision, "mode": "card"})
        rows.append([("🛠️ Gửi sửa theo thẻ (PIN)", gact_fix)])

    r1_lbl = "↩️ Sửa kịch bản (PIN)" if gate == "medical" else "↩️ Dựng lại video (PIN)"
    r2_lbl = "🔬 Tìm thêm nguồn (PIN)" if gate == "medical" else "📝 Sửa lại kịch bản (PIN)"
    rows.append(
        [
            (r1_lbl, _cb_token(state, "gact", {"kind": "gact", "slug": slug, "revision": project.active_revision, "mode": "reject_1"})),
            (r2_lbl, _cb_token(state, "gact", {"kind": "gact", "slug": slug, "revision": project.active_revision, "mode": "reject_2"})),
        ]
    )

    media_row: list[tuple[str, str]] = []
    if (rev / "renders/video.mp4").is_file():
        media_row.append(("🎬 Xem video", _cb_token(state, "vid", {"kind": "vid", "slug": slug}, direct_value=slug)))
    media_row.append(("📜 Xem kịch bản", _cb_token(state, "scr", {"kind": "scr", "slug": slug}, direct_value=slug)))
    rows.append(media_row)

    save_state(root, state)
    send_fn("\n".join(lines), reply_markup=_inline_markup(rows), chat_id=chat_id)


def _execute_gate_decision(
    root: Path,
    state: dict[str, Any],
    pending: dict[str, Any],
    *,
    pin: str,
    chat_id: str,
    send_fn: Callable[..., dict | None],
) -> None:
    slug = str(pending.get("slug") or "")
    mode = str(pending.get("mode") or "")
    loaded = _load_project(root, slug)
    if loaded is None:
        state["pending_gate_input"] = None
        save_state(root, state)
        send_fn(f"❌ Không tìm thấy project `{slug}`.", chat_id=chat_id)
        return
    project_dir, _, _ = loaded
    session = (state.get("review_sessions") or {}).get(slug) or {}
    body: dict[str, Any] = {
        "revision": pending.get("revision"),
        "pin": pin,
    }
    if mode in {"approve", "approve_pronunciation"}:
        body["action"] = mode
    elif mode == "card":
        body["action"] = "card"
        body["choices"] = dict(session.get("choices") or {})
        body["other"] = str(session.get("other") or "")
    elif mode in {"reject_1", "reject_2"}:
        body["action"] = "reject"
        body["reason"] = str(pending.get("reason") or "")
        body["resume"] = 1 if mode == "reject_1" else 2
    else:
        state["pending_gate_input"] = None
        save_state(root, state)
        send_fn("⚠️ Hành động duyệt không hợp lệ.", chat_id=chat_id)
        return

    try:
        message = dashboard.decide(root, project_dir, body, limiter=_PIN_LIMITER)
    except PermissionError as exc:
        if "khóa" in str(exc):
            state["pending_gate_input"] = None
            save_state(root, state)
        send_fn(f"❌ {exc}\nGõ /huy nếu muốn hủy.", chat_id=chat_id)
        return
    except (OSError, ValueError, RuntimeError, LookupError) as exc:
        state["pending_gate_input"] = None
        save_state(root, state)
        send_fn(f"⚠️ Không thể xử lý duyệt cổng `{slug}`: {exc}", chat_id=chat_id)
        return

    state["pending_gate_input"] = None
    (state.get("review_sessions") or {}).pop(slug, None)
    save_state(root, state)
    send_fn(f"✅ [{slug}] {message}", chat_id=chat_id)


def _send_status(root: Path, state: dict[str, Any], chat_id: str, send_fn: Callable[..., dict | None]) -> None:
    f_pid = factory.running_pid(root)
    b_pid = running_pid(root)
    summary = researcher.inbox_summary(root)
    ch = channel_analytics.channel_overview_payload(root)
    items = list(factory.projects(root))
    gates = [p.name for p, proj in items if factory.gate_for_project(p, proj) is not None]
    scope_lbl = state.get("active_slug") or "Toàn xưởng"
    lines = [
        "📊 Trạng thái Xưởng PYH",
        f"- Xưởng sản xuất: {'Đang chạy (PID ' + str(f_pid) + ')' if f_pid else 'Đang tắt'}",
        f"- Bot Leader Telegram: {'Đang chạy (PID ' + str(b_pid) + ')' if b_pid else 'Đang chạy phiên này'}",
        f"- Ngữ cảnh chat: {scope_lbl}",
        f"- Dự án: {len(items)} · Chờ bác sĩ duyệt cổng: {len(gates)}" + (f" ({', '.join(gates[:4])})" if gates else ""),
        f"- Hộp chủ đề: {summary['total']} (Tier A chờ: {summary['tier_a']}, Tier B: {summary['tier_b']})",
        f"- Kênh YouTube: {ch.get('videos_count', 0)} video · {ch.get('total_views', 0)} lượt xem",
    ]
    rows: list[list[tuple[str, str]]] = [
        [
            ("▶️ Bật xưởng" if not f_pid else "⏹️ Dừng xưởng", "act:xuong_start" if not f_pid else "act:xuong_stop"),
            ("🔄 Đồng bộ Sheet", "act:sync"),
        ],
        [("📥 Hộp chủ đề", "act:inbox"), ("📁 Danh sách project", "act:projects")],
    ]
    if gates:
        rows.append([("🪪 Duyệt cổng chờ (" + str(len(gates)) + ")", "act:duyet")])
    send_fn("\n".join(lines), reply_markup=_inline_markup(rows), chat_id=chat_id)


def _send_inbox(root: Path, state: dict[str, Any], chat_id: str, send_fn: Callable[..., dict | None]) -> None:
    items = [
        it
        for it in researcher.load_inbox(root)
        if it.get("status", "inbox") == "inbox" and not it.get("queued") and not it.get("in_project")
    ]
    if not items:
        rows = [[("🔄 Đồng bộ Sheet chủ đề", "act:sync"), ("📊 Trạng thái", "act:status")]]
        send_fn("📥 Hộp chủ đề hiện trống. Bấm đồng bộ Google Sheet hoặc nhắn Leader tìm chủ đề mới.", reply_markup=_inline_markup(rows), chat_id=chat_id)
        return
    top = items[:6]
    lines = [f"📥 Hộp chủ đề chờ duyệt ({len(items)} chủ đề sẵn sàng):"]
    rows: list[list[tuple[str, str]]] = []
    for idx, it in enumerate(top, start=1):
        lines.append(f"{idx}. [Tier {it.get('tier', '?')} · {it.get('rubric_total', 0)}đ] {it.get('title', it['slug'])} (`{it['slug']}`)")
        cb = _cb_token(state, "prm", {"kind": "prm", "inbox_slug": it["slug"]}, direct_value=it["slug"])
        rows.append([(f"➕ Xếp hàng #{idx}: {it['slug'][:20]}", cb)])
    save_state(root, state)
    send_fn("\n".join(lines), reply_markup=_inline_markup(rows), chat_id=chat_id)


def _send_projects(root: Path, state: dict[str, Any], chat_id: str, send_fn: Callable[..., dict | None]) -> None:
    items = list(factory.projects(root))
    if not items:
        send_fn("📁 Chưa có project nào trong thư mục projects/.", chat_id=chat_id)
        return
    active = state.get("active_slug")
    lines = [f"📁 Danh sách project ({len(items)}) — Ngữ cảnh hiện tại: {active or 'Toàn xưởng'}:"]
    rows: list[list[tuple[str, str]]] = []
    for path, proj in items[:8]:
        gate = factory.gate_for_project(path, proj)
        gate_note = f" [CHỜ DUYỆT CỔNG: {gate}]" if gate else ""
        mark = "👉 " if active == path.name else ""
        lines.append(f"{mark}- {path.name} · {proj.state.value} (rev {proj.active_revision}){gate_note}")
        cb = _cb_token(state, "prj", {"kind": "prj", "slug": path.name}, direct_value=path.name)
        btn_row: list[tuple[str, str]] = [(f"💬 {path.name[:16]}", cb)]
        rev_dir = path / "revisions" / proj.active_revision
        if (rev_dir / "renders/video.mp4").is_file():
            vid_cb = _cb_token(state, "vid", {"kind": "vid", "slug": path.name}, direct_value=path.name)
            btn_row.append(("🎬 Video", vid_cb))
        if gate:
            duy_cb = _cb_token(state, "duy", {"kind": "duy", "slug": path.name}, direct_value=path.name)
            btn_row.append((f"🪪 Duyệt ({gate})", duy_cb))
        rows.append(btn_row)
    rows.append([("🌐 Về Toàn xưởng (#chung)", "act:chung")])
    save_state(root, state)
    send_fn("\n".join(lines), reply_markup=_inline_markup(rows), chat_id=chat_id)


def _send_channel(root: Path, chat_id: str, send_fn: Callable[..., dict | None]) -> None:
    ch = channel_analytics.channel_overview_payload(root)
    if not ch.get("connected") and ch.get("videos_count", 0) == 0:
        send_fn("📺 Chưa có số liệu kênh YouTube. Bấm /sync để đồng bộ từ Google Sheet.", chat_id=chat_id)
        return
    lines = [
        f"📺 Hiệu quả kênh YouTube ({ch.get('videos_count', 0)} video)",
        f"- Tổng lượt xem: {ch.get('total_views', 0)}",
    ]
    if ch.get("avg_ctr_pct") is not None:
        lines.append(f"- CTR trung bình: {ch['avg_ctr_pct']}%")
    if ch.get("avg_retention_30s_pct") is not None:
        lines.append(f"- Giữ chân 30s đầu: {ch['avg_retention_30s_pct']}%")
    ins = ch.get("insights")
    if isinstance(ins, dict) and ins.get("summary"):
        lines.append(f"- Nhận xét gần nhất: {ins['summary']}")
    send_fn("\n".join(lines), chat_id=chat_id)


def _help_text(active_slug: str | None) -> str:
    return (
        "🩺 Xin chào bác sĩ! Bot đã nối thẳng với Trưởng nhóm Điều phối (Leader PYH).\n"
        f"Ngữ cảnh chat hiện tại: {active_slug or 'Toàn xưởng'}\n\n"
        "Cách dùng:\n"
        "- Nhắn tự nhiên để giao việc, hỏi tiến độ, nhờ Researcher tìm chủ đề hoặc sửa kịch bản/hình.\n"
        "- Gắn `#<slug>` (vd: `#gout-cap Hãy đổi cảnh S02`) để nói riêng về 1 video mà không cần đổi ngữ cảnh.\n"
        "- Xem sản phẩm & duyệt cổng ngay trên Telegram: /duyet, /video, /clips, /frames, /script, /huy\n"
        "- Quản lý xưởng: /status, /inbox, /projects, /project <slug>, /chung, /sync, /channel, /xuong_start, /xuong_stop\n"
        "- Bảo mật PIN: Khi /duyet yêu cầu nhập mã PIN, tin nhắn PIN của anh sẽ được bot tự xóa ngay lập tức sau khi xác thực."
    )


def _handle_command(
    root: Path,
    state: dict[str, Any],
    cmd: str,
    arg: str,
    chat_id: str,
    *,
    send_fn: Callable[..., dict | None],
    send_video_fn: Callable[..., dict | None] = telegram.send_video,
    send_photo_fn: Callable[..., dict | None] = telegram.send_photo,
    runner: Callable[..., Any] = process.run_bounded,
) -> None:
    if cmd in {"start", "help"}:
        rows = [
            [("📊 Trạng thái", "act:status"), ("🪪 Duyệt cổng", "act:duyet")],
            [("📥 Hộp chủ đề", "act:inbox"), ("📁 Projects", "act:projects")],
            [("🔄 Đồng bộ Sheet", "act:sync")],
        ]
        send_fn(_help_text(state.get("active_slug")), reply_markup=_inline_markup(rows), chat_id=chat_id)
    elif cmd == "status":
        _send_status(root, state, chat_id, send_fn)
    elif cmd == "duyet":
        slug = arg.strip().lstrip("#") or state.get("active_slug")
        _send_gate_review(root, state, slug, chat_id, send_fn=send_fn)
    elif cmd == "video":
        slug = _target_project_slug(root, state, arg)
        _send_project_video(
            root,
            state,
            slug,
            chat_id,
            send_fn=send_fn,
            send_video_fn=send_video_fn,
            send_photo_fn=send_photo_fn,
            runner=runner,
        )
    elif cmd == "clips":
        slug = _target_project_slug(root, state, arg)
        _send_project_clips(root, state, slug, chat_id, send_fn=send_fn, send_video_fn=send_video_fn, runner=runner)
    elif cmd == "frames":
        slug = _target_project_slug(root, state, arg)
        _send_project_frames(root, state, slug, chat_id, send_fn=send_fn, send_photo_fn=send_photo_fn)
    elif cmd == "script":
        slug = _target_project_slug(root, state, arg)
        _send_project_script(root, state, slug, chat_id, send_fn=send_fn)
    elif cmd == "inbox":
        _send_inbox(root, state, chat_id, send_fn)
    elif cmd == "projects":
        _send_projects(root, state, chat_id, send_fn)
    elif cmd == "chung":
        state["active_slug"] = None
        save_state(root, state)
        send_fn("🌐 Đã chuyển ngữ cảnh chat về Toàn xưởng.", chat_id=chat_id)
    elif cmd == "project":
        slug = arg.strip().lstrip("#")
        if not slug:
            _send_projects(root, state, chat_id, send_fn)
            return
        if not (root / "projects" / slug / "project.yaml").is_file():
            send_fn(f"❌ Không tìm thấy project `{slug}`.", chat_id=chat_id)
            return
        state["active_slug"] = slug
        save_state(root, state)
        send_fn(f"💬 Đã chuyển ngữ cảnh chat sang project: {slug}", chat_id=chat_id)
    elif cmd == "sync":
        try:
            res = researcher.sync_reference_sheet(root)
            msg = (
                f"🔄 Đã đồng bộ Google Sheet chủ đề: +{res.get('synced_count', 0)} mục "
                f"(Tổng {res.get('total', 0)} · Tier A: {res.get('tier_a', 0)})."
            )
            if res.get("errors"):
                msg += f"\nCảnh báo: {'; '.join(str(e) for e in res['errors'][:3])}"
        except (OSError, ValueError, RuntimeError) as exc:
            msg = f"❌ Đồng bộ chủ đề lỗi: {exc}"
        try:
            ch_res = channel_analytics.sync_channel_sheet(root)
            msg += f"\n📺 Đồng bộ số liệu kênh: +{ch_res.get('synced_count', 0)} video."
        except (OSError, ValueError, RuntimeError):
            pass
        send_fn(msg, chat_id=chat_id)
    elif cmd == "channel":
        _send_channel(root, chat_id, send_fn)
    elif cmd == "xuong_start":
        try:
            pid = factory.start_background(root)
            send_fn(f"▶️ Xưởng sản xuất đang chạy nền (PID {pid}).", chat_id=chat_id)
        except (OSError, RuntimeError, ValueError, factory.FactoryAlreadyRunning) as exc:
            send_fn(f"⚠️ Không bật được xưởng: {exc}", chat_id=chat_id)
    elif cmd == "xuong_stop":
        pid = factory.stop_background(root)
        send_fn(f"⏹️ Đã gửi lệnh dừng xưởng (PID {pid})." if pid else "ℹ️ Xưởng hiện không chạy.", chat_id=chat_id)
    else:
        send_fn(f"❓ Lệnh `/{cmd}` chưa hỗ trợ. Gõ /help để xem hướng dẫn.", chat_id=chat_id)


def _run_chat_turn(
    root: Path,
    state: dict[str, Any],
    scope_slug: str | None,
    prompt_text: str,
    chat_id: str,
    *,
    req: Callable[..., dict | None],
    send_fn: Callable[..., dict | None],
    invoke: Callable[..., Any],
    typing: bool = True,
) -> None:
    if _is_pin_or_gate_request(prompt_text):
        send_fn(_pin_refusal_text(), chat_id=chat_id)
        return
    ctx = {"slug": scope_slug} if scope_slug else {}
    posted = chat.post(root, scope_slug, prompt_text, ctx, source="telegram", start_worker=False)
    with _typing_indicator(chat_id, req=req, enabled=typing):
        result_row = chat.run_coordinator(root, posted["id"], invoke=invoke)
    text_out, markup = _coordinator_reply_message(root, state, scope_slug, result_row)
    send_fn(text_out, reply_markup=markup, chat_id=chat_id)


def _handle_callback(
    root: Path,
    state: dict[str, Any],
    callback_query: dict[str, Any],
    chat_id: str,
    *,
    req: Callable[..., dict | None],
    send_fn: Callable[..., dict | None],
    send_video_fn: Callable[..., dict | None] = telegram.send_video,
    send_photo_fn: Callable[..., dict | None] = telegram.send_photo,
    runner: Callable[..., Any] = process.run_bounded,
    invoke: Callable[..., Any],
    typing: bool,
) -> None:
    cb_id = str(callback_query.get("id") or "")
    data = str(callback_query.get("data") or "")
    resolved = _resolve_callback(state, data)
    answer_text = "Đã xử lý"

    if resolved is None:
        answer_text = "Nút này đã hết hạn, vui lòng gửi lại yêu cầu."
        with contextlib.suppress(Exception):
            req("answerCallbackQuery", {"callback_query_id": cb_id, "text": answer_text})
        return

    kind = resolved.get("kind")
    with contextlib.suppress(Exception):
        req("answerCallbackQuery", {"callback_query_id": cb_id, "text": answer_text})

    if kind == "cfm":
        slug = resolved.get("slug")
        msg_id = str(resolved.get("msg_id") or "")
        try:
            res = chat.confirm(root, slug, msg_id)
            if res.get("status") == "queued":
                send_fn(f"◷ [{slug or 'Toàn xưởng'}] Đã xếp hàng chờ bước hiện tại xong trước khi sửa.", chat_id=chat_id)
            elif res.get("status") == "failed":
                send_fn(f"⚠️ Lỗi khi xác nhận: {res.get('error') or 'Không rõ'}", chat_id=chat_id)
            else:
                lines = [f"✅ [{slug or 'Toàn xưởng'}] Đã xác nhận thực hiện đề xuất."]
                lines.extend(_format_exec_results(res.get("execution_results") or []))
                send_fn("\n".join(lines), chat_id=chat_id)
        except (LookupError, ValueError, OSError) as exc:
            send_fn(f"⚠️ Không xác nhận được: {exc}", chat_id=chat_id)
    elif kind == "dis":
        slug = resolved.get("slug")
        msg_id = str(resolved.get("msg_id") or "")
        try:
            chat.dismiss(root, slug, msg_id)
            send_fn("❌ Đã bỏ qua đề xuất trên.", chat_id=chat_id)
        except (LookupError, ValueError, OSError) as exc:
            send_fn(f"⚠️ {exc}", chat_id=chat_id)
    elif kind == "opt":
        scope_slug = resolved.get("slug")
        chosen_text = str(resolved.get("text") or "").strip()
        if chosen_text:
            _run_chat_turn(root, state, scope_slug, chosen_text, chat_id, req=req, send_fn=send_fn, invoke=invoke, typing=typing)
    elif kind == "prm":
        inbox_slug = str(resolved.get("inbox_slug") or "")
        try:
            res = researcher.promote_inbox_topic(root, inbox_slug)
            entry = res.get("entry") or {}
            send_fn(f"➕ Đã đưa chủ đề `{entry.get('slug', inbox_slug)}` vào hàng đợi sản xuất (`topics/queue.yaml`).", chat_id=chat_id)
        except (OSError, ValueError, LookupError, FileNotFoundError) as exc:
            send_fn(f"⚠️ Không xếp hàng được `{inbox_slug}`: {exc}", chat_id=chat_id)
    elif kind == "prj":
        slug = str(resolved.get("slug") or "")
        if slug and (root / "projects" / slug / "project.yaml").is_file():
            state["active_slug"] = slug
            save_state(root, state)
            send_fn(f"💬 Đã chuyển ngữ cảnh chat sang project: {slug}", chat_id=chat_id)
        else:
            send_fn(f"❌ Không tìm thấy project `{slug}`.", chat_id=chat_id)
    elif kind == "vid":
        _send_project_video(
            root,
            state,
            str(resolved.get("slug") or ""),
            chat_id,
            send_fn=send_fn,
            send_video_fn=send_video_fn,
            send_photo_fn=send_photo_fn,
            runner=runner,
        )
    elif kind == "clp":
        _send_project_clips(
            root,
            state,
            str(resolved.get("slug") or ""),
            chat_id,
            send_fn=send_fn,
            send_video_fn=send_video_fn,
            runner=runner,
        )
    elif kind == "frm":
        _send_project_frames(
            root,
            state,
            str(resolved.get("slug") or ""),
            chat_id,
            send_fn=send_fn,
            send_photo_fn=send_photo_fn,
        )
    elif kind == "scr":
        _send_project_script(root, state, str(resolved.get("slug") or ""), chat_id, send_fn=send_fn)
    elif kind == "duy":
        _send_gate_review(root, state, str(resolved.get("slug") or ""), chat_id, send_fn=send_fn)
    elif kind == "dopt":
        slug = str(resolved.get("slug") or "")
        decision_id = str(resolved.get("decision_id") or "")
        option_id = str(resolved.get("option_id") or "")
        if slug and decision_id and option_id:
            session = state.setdefault("review_sessions", {}).setdefault(slug, {"revision": None, "choices": {}, "other": ""})
            session.setdefault("choices", {})[decision_id] = option_id
            save_state(root, state)
            _send_gate_review(root, state, slug, chat_id, send_fn=send_fn)
    elif kind == "gact":
        slug = str(resolved.get("slug") or "")
        revision = str(resolved.get("revision") or "")
        mode = str(resolved.get("mode") or "")
        if mode in {"reject_1", "reject_2"}:
            state["pending_gate_input"] = {
                "step": "await_reason",
                "slug": slug,
                "revision": revision,
                "mode": mode,
                "expires_at": time.time() + 300,
            }
            save_state(root, state)
            send_fn(
                f"📝 [{slug}] Anh hãy nhắn lý do từ chối (xưởng sẽ sửa đúng theo nội dung này), hoặc gõ /huy để hủy.",
                chat_id=chat_id,
            )
        elif mode in {"approve", "approve_pronunciation", "card"}:
            state["pending_gate_input"] = {
                "step": "await_pin",
                "slug": slug,
                "revision": revision,
                "mode": mode,
                "reason": "",
                "expires_at": time.time() + 180,
            }
            save_state(root, state)
            send_fn(
                f"🔐 [{slug}] Vui lòng nhập mã PIN duyệt cổng (tin nhắn chứa PIN sẽ được tự xóa ngay), hoặc gõ /huy để hủy.",
                chat_id=chat_id,
            )
    elif kind == "act":
        act = str(resolved.get("action") or "")
        if act == "duyet":
            _send_gate_review(root, state, None, chat_id, send_fn=send_fn)
        elif act in {"status", "inbox", "projects", "chung", "sync", "xuong_start", "xuong_stop"}:
            _handle_command(
                root,
                state,
                act,
                "",
                chat_id,
                send_fn=send_fn,
                send_video_fn=send_video_fn,
                send_photo_fn=send_photo_fn,
                runner=runner,
            )


def handle_update(
    root: Path,
    state: dict[str, Any],
    update: dict[str, Any],
    *,
    req: Callable[..., dict | None] = telegram.request,
    send_fn: Callable[..., dict | None] = telegram.send_text,
    send_video_fn: Callable[..., dict | None] = telegram.send_video,
    send_photo_fn: Callable[..., dict | None] = telegram.send_photo,
    delete_fn: Callable[..., bool] = telegram.delete_message,
    runner: Callable[..., Any] = process.run_bounded,
    invoke: Callable[..., Any] = invoke_with_failover,
    typing: bool = True,
) -> bool:
    allowed = _allowed_chat_id()
    if not allowed:
        return False

    cb = update.get("callback_query")
    if isinstance(cb, dict):
        cb_msg = cb.get("message") if isinstance(cb.get("message"), dict) else {}
        cb_chat = cb_msg.get("chat") if isinstance(cb_msg.get("chat"), dict) else {}
        chat_id = str(cb_chat.get("id") or "")
        if chat_id != allowed:
            return False
        _handle_callback(
            root,
            state,
            cb,
            chat_id,
            req=req,
            send_fn=send_fn,
            send_video_fn=send_video_fn,
            send_photo_fn=send_photo_fn,
            runner=runner,
            invoke=invoke,
            typing=typing,
        )
        return True

    message = update.get("message")
    if not isinstance(message, dict):
        return False
    chat_info = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    chat_id = str(chat_info.get("id") or "")
    if chat_id != allowed:
        return False

    raw_text = str(message.get("text") or "").strip()
    if not raw_text:
        send_fn("Hiện bot hỗ trợ tin nhắn văn bản và nút bấm.", chat_id=chat_id)
        return True

    if re.match(r"^/huy(?:@[a-zA-Z0-9_]+)?(?:\s|$)", raw_text, re.IGNORECASE):
        state["pending_gate_input"] = None
        save_state(root, state)
        send_fn("✅ Đã hủy thao tác duyệt cổng đang chờ.", chat_id=chat_id)
        return True

    pending = state.get("pending_gate_input")
    if isinstance(pending, dict):
        if time.time() > float(pending.get("expires_at") or 0):
            if pending.get("step") == "await_pin" and message.get("message_id") is not None:
                with contextlib.suppress(Exception):
                    delete_fn(message["message_id"], chat_id=chat_id)
            state["pending_gate_input"] = None
            save_state(root, state)
            send_fn("⌛ Phiên duyệt cổng đã hết hạn; vui lòng gõ /duyet để mở lại.", chat_id=chat_id)
            return True
        if pending.get("step") == "await_reason" and not raw_text.startswith("/"):
            pending["reason"] = raw_text
            pending["step"] = "await_pin"
            pending["expires_at"] = time.time() + 180
            save_state(root, state)
            send_fn(
                f"🔐 [{pending.get('slug', '')}] Đã ghi nhận lý do. Nhập mã PIN để xác nhận từ chối (tin PIN sẽ tự xóa ngay), hoặc gõ /huy.",
                chat_id=chat_id,
            )
            return True
        if pending.get("step") == "await_pin" and not raw_text.startswith("/"):
            if message.get("message_id") is not None:
                with contextlib.suppress(Exception):
                    delete_fn(message["message_id"], chat_id=chat_id)
            _execute_gate_decision(root, state, pending, pin=raw_text, chat_id=chat_id, send_fn=send_fn)
            return True

    if _is_pin_or_gate_request(raw_text):
        if _PIN_RE.search(raw_text) and message.get("message_id") is not None:
            with contextlib.suppress(Exception):
                delete_fn(message["message_id"], chat_id=chat_id)
        send_fn(_pin_refusal_text(), chat_id=chat_id)
        return True

    cmd_match = re.match(r"^/([a-zA-Z0-9_]+)(?:@[a-zA-Z0-9_]+)?(?:\s+(.*))?$", raw_text, re.DOTALL)
    if cmd_match:
        cmd = cmd_match.group(1).lower()
        arg = (cmd_match.group(2) or "").strip()
        _handle_command(
            root,
            state,
            cmd,
            arg,
            chat_id,
            send_fn=send_fn,
            send_video_fn=send_video_fn,
            send_photo_fn=send_photo_fn,
            runner=runner,
        )
        return True

    target_slug, clean_text = _resolve_scope(root, raw_text, state.get("active_slug"))
    if not clean_text:
        state["active_slug"] = target_slug
        save_state(root, state)
        send_fn(f"💬 Đã chuyển ngữ cảnh chat sang: {target_slug or 'Toàn xưởng'}", chat_id=chat_id)
        return True

    _run_chat_turn(
        root,
        state,
        target_slug,
        clean_text,
        chat_id,
        req=req,
        send_fn=send_fn,
        invoke=invoke,
        typing=typing,
    )
    return True


def poll_once(
    root: Path,
    state: dict[str, Any],
    *,
    poll_timeout: int = 25,
    req: Callable[..., dict | None] = telegram.request,
    send_fn: Callable[..., dict | None] = telegram.send_text,
    send_video_fn: Callable[..., dict | None] = telegram.send_video,
    send_photo_fn: Callable[..., dict | None] = telegram.send_photo,
    delete_fn: Callable[..., bool] = telegram.delete_message,
    invoke: Callable[..., Any] = invoke_with_failover,
    typing: bool = True,
) -> tuple[dict[str, Any], bool]:
    payload: dict[str, Any] = {
        "timeout": max(0, int(poll_timeout)),
        "allowed_updates": ["message", "callback_query"],
    }
    if state.get("offset") is not None:
        payload["offset"] = int(state["offset"])

    data = req("getUpdates", payload, timeout=max(10, int(poll_timeout) + 10))
    now_iso = datetime.now(UTC).isoformat(timespec="seconds")
    state["last_poll_at"] = now_iso
    if not isinstance(data, dict) or data.get("ok") is not True:
        state["last_error"] = "getUpdates không phản hồi"
        save_state(root, state)
        return state, False

    state["last_error"] = None
    updates = data.get("result") if isinstance(data.get("result"), list) else []
    for upd in updates:
        if not isinstance(upd, dict) or "update_id" not in upd:
            continue
        upd_id = int(upd["update_id"])
        try:
            handle_update(
                root,
                state,
                upd,
                req=req,
                send_fn=send_fn,
                send_video_fn=send_video_fn,
                send_photo_fn=send_photo_fn,
                delete_fn=delete_fn,
                invoke=invoke,
                typing=typing,
            )
        except (OSError, ValueError, RuntimeError, LookupError) as exc:
            logger.warning("Lỗi xử lý Telegram update %s: %s", upd_id, exc)
            state["last_error"] = str(exc)
        state["last_update_id"] = upd_id
        state["offset"] = upd_id + 1
    save_state(root, state)
    return state, True


def run_bot(
    root: Path,
    *,
    poll_timeout: int = 25,
    max_polls: int | None = None,
    echo: Callable[[str], object] = print,
    req: Callable[..., dict | None] = telegram.request,
    send_fn: Callable[..., dict | None] = telegram.send_text,
    invoke: Callable[..., Any] = invoke_with_failover,
) -> None:
    hide_child_consoles()
    _ensure_env_loaded(root)
    if not telegram.configured():
        raise ValueError("Chưa cấu hình TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID trong .env.")

    stop_event = threading.Event()
    if threading.current_thread() is threading.main_thread():
        def _stop_handler(*_args: object) -> None:
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(ValueError, OSError):
                signal.signal(sig, _stop_handler)

    with TelegramBotLock(root):
        state = load_state(root)
        state["started_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        state["last_error"] = None
        save_state(root, state)
        prime_offset_if_needed(root, state, req=req)
        if register_commands(req=req):
            state["commands_registered"] = True
            save_state(root, state)
        echo(f"Telegram bot Leader đang chạy (PID {os.getpid()}).")
        polls = 0
        backoff = 2.0
        while not stop_event.is_set():
            if max_polls is not None and polls >= max_polls:
                break
            polls += 1
            state, ok = poll_once(
                root,
                state,
                poll_timeout=poll_timeout,
                req=req,
                send_fn=send_fn,
                invoke=invoke,
            )
            if ok:
                backoff = 2.0
            else:
                if max_polls is not None and polls >= max_polls:
                    break
                stop_event.wait(backoff)
                backoff = min(backoff * 2.0, 30.0)
