"""Local factory service and desktop integration; never approves or publishes."""

import json
import logging
import os
import signal
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from healthvideo.domain.gate_review import GateKind, GateRejectionRecord
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.env import child_env
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.queue import load_queue
from healthvideo.storage.revisions import create_revision
from healthvideo.workflows.gate_review import resume_gate
from healthvideo.workflows.package import package_project
from healthvideo.workflows.production_retry import clear_retry
from healthvideo.workflows.runner import RunDeps, run_queue, waiting_until

GATES = {
    WorkflowState.AWAITING_MEDICAL_REVIEW: 'medical',
    WorkflowState.AWAITING_VIDEO_REVIEW: 'video',
}


def projects(root: Path):
    """Yield queue projects first, followed by other local projects, once each."""
    paths = [root / 'projects' / entry.slug for entry in load_queue(root)]
    paths.extend(path.parent for path in sorted((root / 'projects').glob('*/project.yaml')))
    for path in dict.fromkeys(paths):
        if not (path / 'project.yaml').is_file():
            continue
        try:
            project = ProjectManifestV2.model_validate(read_yaml(path / 'project.yaml'))
        except ValueError as error:  # one stale project must not stop the whole factory
            print(f'Bỏ qua {path.name}: project.yaml không hợp lệ ({type(error).__name__})', file=sys.stderr)
            continue
        yield path, project


def notify(title: str, event: str, *, transport=None) -> bool:
    from healthvideo.workflows.telegram import event_label, send

    try:
        notify_windows(title, event_label(event))
    except (OSError, subprocess.SubprocessError):
        logging.getLogger(__name__).warning('Windows notification failed (details hidden).')
    return send(title, event, transport=transport)


def project_title(path: Path, project: ProjectManifestV2) -> str:
    card = path / 'revisions' / project.active_revision / 'topic/card.yaml'
    return str(read_yaml(card).get('title', project.slug)) if card.exists() else project.slug


def open_packet(path: Path) -> None:
    if sys.platform == 'win32':
        os.startfile(str(path.resolve()))
    else:
        webbrowser.open(path.resolve().as_uri())


def write_review_packet(root: Path, project_dir: Path, project: ProjectManifestV2) -> Path:
    """Render the current gate's review packet into cache/review and return its path."""
    from html import escape

    from healthvideo.storage.files import write_text_atomic
    from healthvideo.workflows.review_html import (
        render_medical_packet,
        render_video_packet,
    )

    gate = GateKind(GATES[project.state])
    revision = project_dir / 'revisions' / project.active_revision
    render = render_medical_packet if gate is GateKind.MEDICAL else render_video_packet
    html = render(revision)
    base = (revision / 'reviews').resolve().as_uri() + '/'
    html = html.replace('<head>', f'<head><base href="{escape(base, quote=True)}">', 1)
    packet = root / 'cache/review' / f'{project_dir.name}-{gate.value}.html'
    write_text_atomic(packet, html)
    return packet


def notify_windows(title: str, gate: str, *, runner=None, platform=None) -> None:
    """Use static PowerShell code and JSON stdin, so titles cannot execute code."""
    message = f'{gate}\nChạy: healthvideo duyet'
    if (platform or sys.platform) != 'win32':
        print(f'{title}: {message}')
        return
    script = """
 [Console]::InputEncoding = [System.Text.Encoding]::UTF8
 $p = [Console]::In.ReadToEnd() | ConvertFrom-Json
 if (Get-Module -ListAvailable -Name BurntToast) {
   Import-Module BurntToast
   New-BurntToastNotification -Text $p.title,$p.message
 } else {
   Add-Type -AssemblyName System.Windows.Forms
   Add-Type -AssemblyName System.Drawing
   $n = New-Object System.Windows.Forms.NotifyIcon
   try {
     $n.Icon = [System.Drawing.SystemIcons]::Information
     $n.Visible = $true
     $n.ShowBalloonTip(8000, $p.title, $p.message, [System.Windows.Forms.ToolTipIcon]::Info)
     Start-Sleep -Seconds 8
   } finally { $n.Dispose() }
 }
 """
    (runner or subprocess.run)(
        ['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
        input=json.dumps({'title': title, 'message': message}, ensure_ascii=False),
        text=True, encoding='utf-8', env=child_env(), shell=False,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
        capture_output=True, timeout=30, check=False,
    )


def _process_token(pid: int) -> str | None:
    """OS start identity prevents a recycled PID from being stopped as our worker."""
    if pid <= 0:
        return None
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            exit_code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) or exit_code.value != 259:
                return None
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                return None
            return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        proc = Path('/proc') / str(pid) / 'stat'
        return proc.read_text().rsplit(')', 1)[1].split()[19] if proc.exists() else str(pid)
    except ProcessLookupError:
        return None


def lock_path(root: Path) -> Path:
    return root / 'topics' / '.xuong.lock'


def running_pid(root: Path) -> int | None:
    try:
        data = json.loads(lock_path(root).read_text(encoding='utf-8'))
        pid = int(data['pid'])
        token = _process_token(pid)
        return pid if token and token == data.get('process_token') else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


class FactoryAlreadyRunning(RuntimeError):
    pass


class FactoryLock:
    """Kernel lock is released on crashes; stale metadata is replaced under it."""

    def __init__(self, root: Path):
        self.root = root
        self.stream = None

    def __enter__(self):
        path = lock_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open('a+b')
        try:
            if sys.platform == 'win32':
                import msvcrt
                self.stream.seek(65536)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.stream.close()
            raise FactoryAlreadyRunning(f'Xưởng đang chạy (PID {running_pid(self.root) or "đang khởi động"}).') from error
        self.stream.seek(0)
        self.stream.truncate()
        self.stream.write(json.dumps({
            'pid': os.getpid(), 'started_at': datetime.now(UTC).isoformat(),
            'process_token': _process_token(os.getpid()),
        }).encode('utf-8'))
        self.stream.flush()
        return self

    def __exit__(self, *args):
        self.stream.seek(0)
        self.stream.truncate()
        self.stream.flush()
        if sys.platform == 'win32':
            import msvcrt
            self.stream.seek(65536)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        self.stream.close()


def start_background(root: Path, interval: float = 120) -> int:
    existing = running_pid(root)
    if existing:
        return existing
    env = child_env()
    # Keep the selected worktree's code when changing the child's working directory.
    import_paths = [str(Path(__file__).resolve().parents[2])]
    import_paths.extend(str(Path(p).resolve()) for p in env.get('PYTHONPATH', '').split(os.pathsep) if p)
    env['PYTHONPATH'] = os.pathsep.join(dict.fromkeys(import_paths))
    process = subprocess.Popen(
        [sys.executable, '-c', 'from healthvideo.cli import app; app()',
         'xuong', '--root', str(root.resolve()), '--interval', str(interval)],
        cwd=root.resolve(), env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False,
        **({'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS}
           if sys.platform == 'win32' else {'start_new_session': True}),
    )
    for _ in range(100):
        pid = running_pid(root)
        if pid:
            return pid
        if process.poll() is not None:
            raise RuntimeError('Không khởi động được xưởng; chạy healthvideo xuong để xem lỗi.')
        time.sleep(0.05)
    raise RuntimeError(f'Xưởng PID {process.pid} chưa sẵn sàng; kiểm tra status hoặc xuong.log.')


def stop_background(root: Path) -> int | None:
    pid = running_pid(root)
    if pid:
        os.kill(pid, signal.SIGTERM)
    return pid


def prepare_semantic_revisions(root: Path) -> None:
    """Keep approved bytes in their revision, then resume script rework safely."""
    for path, project in projects(root):
        revision = path / 'revisions' / project.active_revision
        pending = root / 'topics/logs' / path.name / 'pending-semantic-revision.yaml'
        semantic = (
            project.state is WorkflowState.NEEDS_PRODUCTION_REVISION
            and project.side_state.reason_code == 'semantic_issue'
            and project.side_state.resume_state is WorkflowState.DRAFT_READY
        )
        if not semantic and not pending.exists():
            continue
        if not pending.exists():
            records = sorted((revision / 'reviews/video').glob('*-rejected*.yaml'))
            if not records:
                raise ValueError(f'{path.name}: thiếu hồ sơ từ chối video')
            record = GateRejectionRecord.model_validate(read_yaml(records[-1]))
            if (record.kind is not GateKind.VIDEO
                    or record.resume_state is not WorkflowState.DRAFT_READY
                    or record.reviewed_at != project.side_state.entered_at):
                raise ValueError(f'{path.name}: hồ sơ từ chối không khớp trạng thái')
            write_yaml_atomic(pending, {'revision': project.active_revision,
                                       'rejection': record.model_dump(mode='json')})
        intent = read_yaml(pending)
        record = GateRejectionRecord.model_validate(intent['rejection'])
        reason = f'semantic_issue: {record.reason}'
        if project.active_revision == intent['revision']:
            create_revision(path, reason, now=datetime.now(UTC), recover=True)
            project = ProjectManifestV2.model_validate(read_yaml(path / 'project.yaml'))
        revision = path / 'revisions' / project.active_revision
        provenance = read_yaml(revision / 'workflow.yaml')
        if (provenance.get('parent_revision') != intent['revision']
                or provenance.get('reason') != reason
                or (revision / 'reviews/medical-approval.yaml').exists()):
            raise ValueError(f'{path.name}: revision sửa nội dung không khớp hồ sơ từ chối')
        if project.state is WorkflowState.NEEDS_PRODUCTION_REVISION:
            resume_gate(path, GateKind.VIDEO, target=WorkflowState.DRAFT_READY,
                        reason_code='semantic_issue', now=datetime.now(UTC))
        elif project.state is not WorkflowState.DRAFT_READY:
            raise ValueError(f'{path.name}: chưa hoàn tất nối lại kịch bản')
        clear_retry(root, path.name)
        pending.unlink()


def run_factory(root: Path, deps: RunDeps, *, interval: float = 120, once: bool = False,
                sleep: Callable = time.sleep, notify: Callable | None = None,
                echo: Callable = print) -> None:
    """Advance, package approved work, and announce changes until interrupted."""
    notify = notify or globals()['notify']
    with FactoryLock(root):
        logs = root / 'topics/logs'
        logs.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(logs / 'xuong.log', maxBytes=1_000_000,
                                      backupCount=2, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger = logging.getLogger(f'healthvideo.xuong.{id(handler)}')
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.addHandler(handler)
        previous = {}
        def announce(key, title, event, signature, current):
            current[key] = signature
            if previous.get(key) == signature:
                return
            echo(f'{title}: {event} — Chạy: healthvideo duyet')
            logger.info('%s: %s', title, event)
            try:
                notify(title, event)
            except (OSError, subprocess.SubprocessError) as error:
                logger.warning('Thông báo thất bại: %s', error)
        try:
            while True:
                delay = interval
                current = {}
                try:
                    prepare_semantic_revisions(root)
                    report = run_queue(root, deps)
                    backs = [back for slug in report.waiting_model
                             if (back := waiting_until(root, slug)) is not None]
                    if backs:  # wake when the first paused topic's model returns
                        wait = (min(backs) - datetime.now(UTC)).total_seconds()
                        delay = min(interval, max(1.0, wait))
                    for path, project in projects(root):
                        event = GATES.get(project.state)
                        signature = f'{project.active_revision}:{project.artifact_hashes}'
                        if project.state == WorkflowState.VIDEO_APPROVED:
                            try:
                                package_project(path)
                                clear_retry(root, path.name)
                                event = 'đã đóng gói'
                            except (OSError, TypeError, ValueError) as error:
                                event = f'bị chặn đóng gói: {error}'
                        elif project.state == WorkflowState.PACKAGED:
                            event = 'đã đóng gói'
                        elif project.state == WorkflowState.BLOCKED or path.name in report.blocked:
                            note = logs / path.name / 'blocked.txt'
                            event = 'bị chặn: ' + (note.read_text(encoding='utf-8') if note.exists() else project.state.value)
                        if event:
                            if event == 'đã đóng gói':
                                signature = project.active_revision
                            announce(path.name, project_title(path, project), event, (event, signature), current)
                    previous = current
                except (OSError, TypeError, ValueError, RuntimeError) as error:
                    announce('__factory__', 'Xưởng', f'bị chặn: {error}', str(error), current)
                    previous = current
                    logger.exception('Vòng xưởng thất bại; sẽ thử lại')
                if once:
                    break
                sleep(delay)
        except KeyboardInterrupt:
            logger.info('Xưởng đã dừng')
        finally:
            logger.removeHandler(handler)
            handler.close()
