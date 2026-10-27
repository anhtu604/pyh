"""Isolated, offline acceptance trials. Never dispatch production work."""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import subprocess
import threading
import wave
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from healthvideo.storage.files import read_yaml, write_yaml_atomic

TRIAL_LOCK = threading.RLock()


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


def trial_bundle(root: Path, trial_id: str) -> dict:
    directory = trial_dir(root, trial_id)
    path = directory / 'trial.yaml'
    if not path.is_file():
        raise LookupError('Không có mẫu thử này.')
    record = read_yaml(path)
    if record.get('id') != trial_id:
        raise ValueError('Trial identity mismatch.')
    stage_number(record['stage'])
    stale = record['input_hash'] != input_hash(record)
    for output in record['outputs']:
        target = (directory / output['path']).resolve()
        if not target.is_relative_to(directory.resolve()) or not target.is_file() or digest(target) != output['sha256']:
            stale = True
    if stale:
        record['status'] = 'stale'
    draft = directory / 'standard-draft.yaml'
    record['draft'] = read_yaml(draft) if draft.is_file() else {}
    return record


def list_trials(root: Path) -> list[dict]:
    return [trial_bundle(root, path.parent.name)
            for path in sorted(trial_root(root).glob('*/trial.yaml'))]


def run_trial(root: Path, trial_id: str, *, real_service: bool = False) -> dict:
    if real_service is not False:
        raise ValueError('real_service chưa được cấu hình; quota tối đa 1 mẫu, chỉ dùng offline.')
    with TRIAL_LOCK:
        record = trial_bundle(root, trial_id)
        if record['status'] == 'stale':
            raise ValueError('Mẫu stale; tạo mẫu mới trước khi thử.')
        directory = trial_dir(root, trial_id)
        record.pop('draft', None)
        record['sample_version'] += 1
        record['input_hash'] = input_hash(record)
        try:
            outputs = build_stage_sample(directory, record['stage'], record['topic'])
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
