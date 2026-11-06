"""Isolated acceptance trials: stage 1 runs real research, draft and script review in trial dir; stages 2-4 stay offline."""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import struct
import subprocess
import threading
import wave
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from healthvideo.agents import (
    DEFAULT_AGENTS,
    AgentCli,
    AgentResult,
    AllAgentsExhausted,
    invoke_with_failover,
)
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.factory_deps import (
    changed_code_paths,
    code_snapshot,
    create_project,
)
from healthvideo.workflows.runner import render_prompt
from healthvideo.workflows.script_review import (
    next_script_action,
    record_review,
    review_view,
    revision_notes,
    script_hash,
    script_path,
)
from healthvideo.workflows.standards import prompt_block

TRIAL_LOCK = threading.RLock()
_ACTIVE_TRIALS: dict[str, threading.Thread] = {}
ORPHAN_REASON = 'App đã tắt khi mẫu đang chạy; bấm chạy lại.'
TRIAL_ISOLATION_LINE = (
    'Đây là mẫu nghiệm thu: thư mục làm việc hiện tại là bản sao repo dùng một lần; '
    'component SVG mới và test ghi vào video/src/anatomy/ của bản sao này. '
    'Ngoài bản sao, chỉ ghi trong thư mục project; không ghi đường dẫn tuyệt đối nào khác.'
)
_STEP_LABELS = {'research': 'tìm nguồn', 'draft': 'viết kịch bản', 'script_review': 'chấm kịch bản'}


def trial_root(root: Path) -> Path:
    return root / 'cache' / 'factory-test'


def stage_number(stage: int) -> int:
    if type(stage) is not int or stage not in range(1, 5):
        raise ValueError('Giai đoạn phải từ 1 đến 4.')
    return stage


def trial_dir(root: Path, trial_id: str) -> Path:
    if not re.fullmatch(r'[a-f0-9]{32}', trial_id):
        raise ValueError('Trial ID không hợp lệ.')
    base = trial_root(root).resolve()
    target = (base / trial_id).resolve()
    if target.parent != base:
        raise ValueError('Trial path escapes root.')
    return target


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_hash(record: dict) -> str:
    data = {key: record[key] for key in ('id', 'stage', 'topic', 'sample_version')}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def create_trial(root: Path, stage: int, *, topic: str = 'TEST — Hình tròn chuyển động') -> dict:
    stage_number(stage)
    if not isinstance(topic, str) or not topic.strip() or len(topic) > 500:
        raise ValueError('Nhập chủ đề TEST (tối đa 500 ký tự).')
    trial_id = uuid4().hex
    record = {'id': trial_id, 'stage': stage, 'topic': topic.strip(), 'sample_version': 1,
              'status': 'created', 'outputs': [], 'events': ['created'], 'real_service_quota': 1,
              'timeline': [{'at': datetime.now().astimezone().isoformat(), 'text': 'Đã tạo mẫu TEST.'}]}
    record['input_hash'] = input_hash(record)
    write_yaml_atomic(trial_dir(root, trial_id) / 'trial.yaml', record)
    return record


def _stage1_outputs(directory: Path) -> list[Path]:
    project_dir = directory / 'project'
    if not project_dir.is_dir():
        return []
    manifest_path = project_dir / 'project.yaml'
    rev = '001'
    if manifest_path.is_file():
        try:
            rev = str(read_yaml(manifest_path).get('active_revision') or '001')
        except Exception:  # noqa: BLE001
            rev = '001'
    candidates = (
        project_dir / 'revisions' / rev / 'script/script.yaml',
        project_dir / 'revisions' / rev / 'evidence/ledger.yaml',
        project_dir / 'revisions' / rev / 'evidence/claims.yaml',
        project_dir / 'revisions' / rev / 'evidence/records.yaml',
        project_dir / 'revisions' / rev / 'explainer/explainer.yaml',
        project_dir / 'revisions' / rev / 'script/outline.yaml',
        project_dir / 'revisions' / rev / 'script/clip-plan.yaml',
        project_dir / 'revisions' / rev / 'storyboard/storyboard.yaml',
        project_dir / 'revisions' / rev / 'assets/asset-manifest.yaml',
        project_dir / 'script/script.yaml',
        project_dir / 'script.yaml',
        project_dir / 'evidence/ledger.yaml',
        project_dir / 'ledger.yaml',
        project_dir / 'claims.yaml',
        project_dir / 'records.yaml',
    )
    seen: set[Path] = set()
    outputs: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if candidate.is_file() and resolved not in seen:
            seen.add(resolved)
            outputs.append(candidate)
    return outputs


def _populate_stage1_view(directory: Path, record: dict) -> None:
    if record.get('stage') != 1 or record.get('status') != 'ready':
        return
    script_data: dict = {}
    ledger_data: dict = {}
    claims_data: dict = {}
    records_data: dict = {}
    for output in record.get('outputs', []):
        target = directory / output['path']
        if not target.is_file() or target.suffix != '.yaml':
            continue
        name = target.name
        if name == 'script.yaml' and not script_data:
            script_data = read_yaml(target)
        elif name == 'ledger.yaml' and not ledger_data:
            ledger_data = read_yaml(target)
        elif name == 'claims.yaml' and not claims_data:
            claims_data = read_yaml(target)
        elif name == 'records.yaml' and not records_data:
            records_data = read_yaml(target)
    script_output = next((o for o in record.get('outputs', [])
                          if o['path'].endswith('script/script.yaml')), None)
    if script_output is not None:
        record['script_review'] = review_view((directory / script_output['path']).parent.parent)
    raw_lines = script_data.get('lines', []) if isinstance(script_data, dict) else []
    record['lines'] = [
        {
            'id': line.get('id'),
            'text': line.get('text', ''),
            'purpose': line.get('purpose'),
            'claim_id': line.get('claim_id'),
            'source_marker': line.get('source_marker'),
        }
        for line in raw_lines
        if isinstance(line, dict)
    ]
    raw_claims = (
        (ledger_data.get('claims') if isinstance(ledger_data, dict) else None)
        or (claims_data.get('claims') if isinstance(claims_data, dict) else None)
        or (script_data.get('claims') if isinstance(script_data, dict) else None)
        or []
    )
    record['claims'] = [
        {
            'id': c.get('id'),
            'text': c.get('text_public') or c.get('text', ''),
            'type': c.get('type'),
            'sources': c.get('sources', []),
            'applicability': c.get('applicability', ''),
            'technical': c.get('text_technical', ''),
            'support': [
                {
                    'source_id': s.get('source_id'),
                    'locator': s.get('locator'),
                    'quote': s.get('quote'),
                }
                for s in c.get('support', [])
                if isinstance(s, dict)
            ],
        }
        for c in raw_claims
        if isinstance(c, dict)
    ]
    raw_records = (
        (ledger_data.get('records') if isinstance(ledger_data, dict) else None)
        or (records_data.get('records') if isinstance(records_data, dict) else None)
        or (script_data.get('sources') if isinstance(script_data, dict) else None)
        or (script_data.get('records') if isinstance(script_data, dict) else None)
        or []
    )
    record['records'] = [
        {
            'id': r.get('id'),
            'title': r.get('title'),
            'year': r.get('year'),
            'journal': r.get('journal'),
            'doi': r.get('doi'),
            'pmid': r.get('pmid'),
            'url': r.get('url'),
        }
        for r in raw_records
        if isinstance(r, dict)
    ]


def trial_bundle(root: Path, trial_id: str) -> dict:
    with TRIAL_LOCK:
        directory = trial_dir(root, trial_id)
        path = directory / 'trial.yaml'
        if not path.is_file():
            raise LookupError('Không có mẫu thử này.')
        record = read_yaml(path)
        if record.get('id') != trial_id:
            raise ValueError('Trial identity mismatch.')
        stage_number(record['stage'])
        if record.get('status') == 'running':
            thread = _ACTIVE_TRIALS.get(trial_id)
            if thread is None or not thread.is_alive():
                _ACTIVE_TRIALS.pop(trial_id, None)
                record.pop('step', None)
                record.update(
                    status='failed',
                    reason=ORPHAN_REASON,
                    error=ORPHAN_REASON,
                    outputs=[],
                )
                record.setdefault('events', []).append('orphan-failed')
                record.setdefault('timeline', []).append({
                    'at': datetime.now().astimezone().isoformat(),
                    'text': ORPHAN_REASON,
                })
                write_yaml_atomic(path, record)
        stale = record['input_hash'] != input_hash(record)
        for output in record['outputs']:
            target = (directory / output['path']).resolve()
            if not target.is_relative_to(directory.resolve()) or not target.is_file() or digest(target) != output['sha256']:
                stale = True
        # stage-1 samples from the old offline builder (no agent project) are not real scripts
        if record['stage'] == 1 and record['outputs'] and not any(
                o['path'].startswith('project/') for o in record['outputs']):
            stale = True
        if stale:
            record['status'] = 'stale'
        draft = directory / 'standard-draft.yaml'
        record['draft'] = read_yaml(draft) if draft.is_file() else {}
        _populate_stage1_view(directory, record)
        return record


def list_trials(root: Path) -> list[dict]:
    return [trial_bundle(root, path.parent.name)
            for path in sorted(trial_root(root).glob('*/trial.yaml'))]


def wait_trial(root: Path, trial_id: str, timeout: float = 5.0) -> dict:
    with TRIAL_LOCK:
        thread = _ACTIVE_TRIALS.get(trial_id)
    if thread is not None:
        thread.join(timeout=timeout)
    return trial_bundle(root, trial_id)


def _fail_stage1(directory: Path, reason: str, event: str) -> None:
    with TRIAL_LOCK:
        path = directory / 'trial.yaml'
        if not path.is_file():
            return
        record = read_yaml(path)
        for key in ('draft', 'lines', 'claims', 'records', 'script_review', 'step'):
            record.pop(key, None)
        now_iso = datetime.now().astimezone().isoformat()
        record.update(status='failed', reason=reason, error=reason, outputs=[])
        record.setdefault('events', []).append(event)
        record.setdefault('timeline', []).append({'at': now_iso, 'text': reason})
        write_yaml_atomic(path, record)


def trial_checkout(root: Path, directory: Path) -> Path:
    """Disposable git worktree so agent edits (e.g. new anatomy SVG) never reach the real repo."""
    checkout = directory / 'repo'
    _remove_checkout(root, checkout)
    subprocess.run(['git', 'worktree', 'add', '--detach', str(checkout), 'HEAD'],
                   cwd=root, check=True, capture_output=True)
    return checkout


def _remove_checkout(root: Path, checkout: Path) -> None:
    if checkout.exists():
        subprocess.run(['git', 'worktree', 'remove', '--force', str(checkout)], cwd=root, capture_output=True, check=False)
        shutil.rmtree(checkout, ignore_errors=True)
    if (root / '.git').exists():
        subprocess.run(['git', 'worktree', 'prune'], cwd=root, capture_output=True, check=False)


def _run_stage1_worker(
    root: Path,
    trial_id: str,
    directory: Path,
    project_dir: Path,
    topic: str,
    invoke: Callable[..., AgentResult],
    agents: Sequence[AgentCli],
) -> None:
    log_dir = directory / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    checkout = directory / 'repo'
    try:
        guarded = (root / '.git').exists()
        before = code_snapshot(root) if guarded else {}
        try:
            checkout = trial_checkout(root, directory)
        except (OSError, subprocess.CalledProcessError) as exc:
            _fail_stage1(directory, f'Không tạo được bản sao repo cho mẫu thử: {exc}', 'checkout-failed')
            return
        step: str | None = 'research'
        rewriting = False
        while step is not None:
            step_vi = _STEP_LABELS[step]
            if step != 'research':
                with TRIAL_LOCK:
                    record = read_yaml(directory / 'trial.yaml')
                    record['step'] = step
                    record.setdefault('timeline', []).append({
                        'at': datetime.now().astimezone().isoformat(),
                        'text': ('Đang sửa kịch bản theo nhận xét biên tập…' if rewriting
                                 else f'Đang {step_vi} ({step})…'),
                    })
                    write_yaml_atomic(directory / 'trial.yaml', record)
            fields: dict[str, str] = {
                'project': str(project_dir),
                'slug': 'project',
                'title': topic,
                'question': topic,
                'doctor_note': '',
            }
            if step in {'draft', 'script_review'}:
                fields['reject_note'] = revision_notes(project_dir) if rewriting else ''
            prompt = render_prompt(step, **fields)
            standards_block = prompt_block(root)
            if standards_block:
                prompt = f'{prompt.rstrip()}\n\n{standards_block}'
            prompt = f'{prompt.rstrip()}\n\n{TRIAL_ISOLATION_LINE}\n'
            reviewing = step == 'script_review'
            reviewed_hash = script_hash(project_dir) if reviewing else ''
            try:
                result = invoke(
                    tuple(reversed(agents)) if reviewing else agents,
                    prompt,
                    cwd=checkout,
                    log_dir=log_dir,
                )
            except AllAgentsExhausted:
                _fail_stage1(
                    directory,
                    f'Agent đã hết hạn mức (quota) ở bước {step_vi}; vui lòng thử lại sau.',
                    f'{step}-quota-exhausted',
                )
                return
            except Exception as exc:  # noqa: BLE001
                _fail_stage1(
                    directory,
                    f'Agent gặp lỗi ở bước {step_vi}: {exc}',
                    f'{step}-exception',
                )
                return
            if not result.ok:
                if result.quota_exhausted:
                    reason = f'Agent ({result.agent}) đã hết hạn mức (quota) ở bước {step_vi}; vui lòng thử lại sau.'
                else:
                    reason = f'Agent ({result.agent}) gặp lỗi ở bước {step_vi}; bấm chạy lại để thử lại.'
                _fail_stage1(directory, reason, f'{step}-failed')
                return
            blocked = project_dir / 'blocked-reason.md'
            if blocked.is_file():
                detail = blocked.read_text(encoding='utf-8', errors='replace').strip()
                _fail_stage1(
                    directory,
                    f'Không đủ bằng chứng xác minh: {detail}' if detail else 'Không đủ bằng chứng xác minh.',
                    f'{step}-blocked',
                )
                return
            if step == 'research':
                step = 'draft'
                continue
            if step == 'draft' and not script_path(project_dir).is_file():
                break
            try:
                if reviewing:
                    record_review(project_dir, reviewed_hash)
                action = next_script_action(project_dir)
            except (OSError, ValueError) as exc:
                _fail_stage1(directory, f'Không chấm được kịch bản: {exc}', 'script-review-failed')
                return
            if rewriting and action == 'draft':
                _fail_stage1(directory, 'Agent không sửa kịch bản theo nhận xét biên tập.', 'draft-unchanged')
                return
            rewriting = reviewing and action == 'draft'
            step = None if action == 'submit_medical' else action
        leaked = changed_code_paths(root, before) if guarded else []
        if leaked:
            _fail_stage1(
                directory,
                'Agent đã ghi ra ngoài khu thử, cần gỡ tay: '
                + ', '.join(p.as_posix() for p in leaked),
                'leaked-into-repo',
            )
            return
        outputs = _stage1_outputs(directory)
        if not any(p.name == 'script.yaml' for p in outputs):
            _fail_stage1(
                directory,
                'Agent chạy xong nhưng chưa tạo được file kịch bản (script.yaml).',
                'draft-missing-script',
            )
            return
        with TRIAL_LOCK:
            now_iso = datetime.now().astimezone().isoformat()
            record = read_yaml(directory / 'trial.yaml')
            for key in ('draft', 'lines', 'claims', 'records', 'script_review', 'reason', 'error', 'step'):
                record.pop(key, None)
            record.update(
                status='ready',
                completed_at=now_iso,
                outputs=[
                    {'path': p.relative_to(directory).as_posix(), 'sha256': digest(p)}
                    for p in outputs
                ],
            )
            record.setdefault('events', []).append('stage1-ready')
            record.setdefault('timeline', []).append({
                'at': now_iso,
                'text': 'Đã viết xong kịch bản mẫu; sẵn sàng xem.',
            })
            write_yaml_atomic(directory / 'trial.yaml', record)
    finally:
        _remove_checkout(root, checkout)
        with TRIAL_LOCK:
            if _ACTIVE_TRIALS.get(trial_id) is threading.current_thread():
                _ACTIVE_TRIALS.pop(trial_id, None)


def run_trial(
    root: Path,
    trial_id: str,
    *,
    real_service: bool = False,
    invoke: Callable[..., AgentResult] | None = None,
    agents: Sequence[AgentCli] = DEFAULT_AGENTS,
) -> dict:
    with TRIAL_LOCK:
        record = trial_bundle(root, trial_id)
        stage = record['stage']
        if stage != 1 and real_service is not False:
            raise ValueError('real_service chưa được cấu hình; quota tối đa 1 mẫu, chỉ dùng offline.')
        if record['status'] == 'stale':
            raise ValueError('Mẫu stale; tạo mẫu mới trước khi thử.')
        directory = trial_dir(root, trial_id)
        for key in ('draft', 'lines', 'claims', 'records', 'script_review', 'reason', 'error', 'step'):
            record.pop(key, None)
        if stage == 1:
            for tid, existing in list(_ACTIVE_TRIALS.items()):
                if existing.is_alive():
                    raise ValueError('Đang có mẫu chạy.')
                _ACTIVE_TRIALS.pop(tid, None)
            record['sample_version'] += 1
            record['input_hash'] = input_hash(record)
            project_dir = directory / 'project'
            if project_dir.exists():
                shutil.rmtree(project_dir)
            now = datetime.now().astimezone()
            entry = QueueEntry(
                slug='project',
                title=record['topic'],
                question=record['topic'],
                added=now.date(),
            )
            project_dir = create_project(root, entry, projects_dir=directory)
            now_iso = now.isoformat()
            record.update(
                status='running',
                started_at=now_iso,
                step='research',
                outputs=[],
            )
            record.setdefault('events', []).append('stage1-started')
            record.setdefault('timeline', []).append({
                'at': now_iso,
                'text': 'Đang tìm nguồn và lập sổ cái bằng chứng (research)…',
            })
            write_yaml_atomic(directory / 'trial.yaml', record)
            invoke_fn = invoke if invoke is not None else invoke_with_failover
            worker = threading.Thread(
                target=_run_stage1_worker,
                args=(root, trial_id, directory, project_dir, record['topic'], invoke_fn, agents),
                daemon=True,
            )
            _ACTIVE_TRIALS[trial_id] = worker
            draft_path = directory / 'standard-draft.yaml'
            running_snapshot = {**record, 'draft': read_yaml(draft_path) if draft_path.is_file() else {}}
            worker.start()
            return running_snapshot

        record['sample_version'] += 1
        record['input_hash'] = input_hash(record)
        try:
            outputs = build_stage_sample(directory, stage, record['topic'])
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            record.update(status='failed', outputs=[])
            record['events'].append(f'Offline sample failed: {type(error).__name__}')
            record.setdefault('timeline', []).append({
                'at': datetime.now().astimezone().isoformat(), 'text': 'Dựng mẫu ngoại tuyến chưa thành công.'})
            write_yaml_atomic(directory / 'trial.yaml', record)
            raise RuntimeError('Không dựng được mẫu offline; kiểm Remotion/FFmpeg local rồi thử lại.') from error
        record.update(status='ready', outputs=[{'path': p.relative_to(directory).as_posix(), 'sha256': digest(p)}
                                                for p in outputs])
        record['events'].append('offline-run')
        record.setdefault('timeline', []).append({
            'at': datetime.now().astimezone().isoformat(), 'text': 'Đã dựng mẫu ngoại tuyến; sẵn sàng xem.'})
        write_yaml_atomic(directory / 'trial.yaml', record)
        return trial_bundle(root, trial_id)


def _video_dependencies() -> tuple[Path, Path]:
    # Search the source checkout and its parents (including the main worktree).
    selected_modules = None
    selected_browser = None
    for parent in Path(__file__).resolve().parents:
        modules = parent / 'video/node_modules'
        cli = modules / '@remotion/cli/remotion-cli.js'
        browsers = list((modules / '.remotion').glob('**/chrome-headless-shell.exe'))
        browsers += list((modules / '.remotion').glob('**/chrome-headless-shell'))
        if selected_modules is None and cli.is_file():
            selected_modules = modules
        if selected_browser is None and browsers:
            selected_browser = browsers[0]
    if selected_modules is not None and selected_browser is not None:
        return selected_modules, selected_browser
    raise RuntimeError('Local locked Remotion runtime/browser required; downloads disabled.')


def _render_samples(directory: Path) -> list[Path]:
    modules, browser = _video_dependencies()
    entry = directory / 'sample-entry.js'
    react = json.dumps((modules / 'react/index.js').as_posix())
    remotion = json.dumps((modules / 'remotion/dist/esm/index.mjs').as_posix())
    entry.write_text(
        f'import React from {react};\n'
        f'import {{registerRoot,Composition,AbsoluteFill,useCurrentFrame,useVideoConfig}} from {remotion};\n'
        'const h=React.createElement;\n'
        'const Scene=()=>{const f=useCurrentFrame();const {fps,width,height}=useVideoConfig();\n'
        'return h(AbsoluteFill,{style:{background:"#102635",color:"#f7fafb",fontFamily:"Arial",'
        'fontSize:24,padding:24}},h("div",null,"TEST · Hình tròn chuyển động"),'
        'h("div",{style:{position:"absolute",top:height*.45,left:40+(width-140)*f/(5*fps),'
        'width:60,height:60,borderRadius:30,background:"#47d7bd"}}),'
        'h("div",{style:{position:"absolute",bottom:24}},f<fps*2.5?"Hình tròn di chuyển":"Hình tròn dừng lại"));};\n'
        'const Root=()=>h(React.Fragment,null,'
        'h(Composition,{id:"TrialWide",component:Scene,width:640,height:360,fps:24,durationInFrames:120}),'
        'h(Composition,{id:"TrialVertical",component:Scene,width:360,height:640,fps:24,durationInFrames:120}));\n'
        'registerRoot(Root);\n', encoding='utf-8')
    outputs = []
    for composition, name in [('TrialWide', 'wide.mp4'), ('TrialVertical', 'vertical.mp4')]:
        output = directory / name
        command = ['node', str(modules / '@remotion/cli/remotion-cli.js'), 'render', str(entry),
                   composition, str(output), '--codec=h264', '--concurrency=1', '--log=error',
                   f'--browser-executable={browser}', '--public-dir=' + str(directory / 'public'),
                   '--webpack-cache=false']
        result = subprocess.run(command, cwd=directory, capture_output=True, timeout=180, check=False,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise RuntimeError('Remotion sample render failed: ' + result.stderr.decode('utf-8', errors='replace')[-1000:])
        outputs.append(output)
    return outputs


def build_stage_sample(directory: Path, stage: int, topic: str = 'TEST — Hình tròn chuyển động') -> list[Path]:
    """Create nonmedical local evidence; all generated bytes stay in the given trial."""
    from PIL import Image, ImageDraw, ImageFont

    stage_number(stage)
    directory.mkdir(parents=True, exist_ok=True)
    summary = directory / 'sample.txt'
    summary.write_text(f'TEST · Giai đoạn {stage}\n{topic}\nMẫu phi y khoa, không có nguồn hay số liệu nghiên cứu.\n', encoding='utf-8')
    outputs = [summary]
    if stage == 1:
        script = directory / 'script.yaml'
        write_yaml_atomic(script, {'mode': 'TEST', 'topic': topic, 'sources': [],
                                  'lines': [{'id': 'T01', 'text': 'Một hình tròn đi ngang qua màn hình.'},
                                            {'id': 'T02', 'text': 'Hình tròn dừng lại.'}],
                                  'scenes': [{'id': 'S01', 'script_line': 'T01', 'visual': 'Hình tròn di chuyển'},
                                             {'id': 'S02', 'script_line': 'T02', 'visual': 'Hình tròn đứng yên'}]})
        outputs.append(script)
    if stage in (2, 4):
        image = directory / ('illustration.png' if stage == 2 else 'thumbnail.png')
        canvas = Image.new('RGB', (640, 360), '#102635')
        draw = ImageDraw.Draw(canvas)
        draw.ellipse((260, 110, 380, 230), fill='#47d7bd')
        # Use a local Unicode font; Pillow's default font omits Vietnamese glyphs.
        font = next((font for name in ('arial.ttf', 'DejaVuSans.ttf')
                     for font in _sample_fonts(ImageFont, name)), None)
        draw.text((30, 30), 'TEST · Hình tròn chuyển động', fill='white', font=font)
        canvas.save(image)
        outputs.append(image)
    if stage == 2:
        audio = directory / 'tone.wav'
        with wave.open(str(audio), 'wb') as sound:
            sound.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            sound.writeframes(b''.join(struct.pack('<h', int(4000 * math.sin(2 * math.pi * 440 * i / 16000)))
                                       for i in range(32000)))
        outputs.append(audio)
    if stage == 3:
        outputs.extend(_render_samples(directory))
        qa = directory / 'qa.json'
        qa.write_text(json.dumps({'mode': 'TEST', 'duration_seconds': 5, 'fps': 24,
                                  'captions': ['Hình tròn di chuyển', 'Hình tròn dừng lại'],
                                  'renderer': 'Remotion', 'formats': ['16:9', '9:16']}), encoding='utf-8')
        outputs.append(qa)
    if stage == 4:
        caption = directory / 'captions.txt'
        caption.write_text('TEST — Hình tròn chuyển động\nMột hình tròn đi ngang qua màn hình.\nMẫu thử, không xuất bản.\n', encoding='utf-8')
        outputs.append(caption)
    manifest = directory / 'sample-hashes.json'
    manifest.write_text(json.dumps({p.name: digest(p) for p in outputs}, sort_keys=True), encoding='utf-8')
    return [*outputs, manifest]


def _sample_fonts(image_font, name: str) -> list:
    try:
        return [image_font.truetype(name, 28)]
    except OSError:
        return []
