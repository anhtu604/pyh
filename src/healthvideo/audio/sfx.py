"""Verified CC0 effects, deterministic scene scheduling and cached voice-first mixing."""

import json
import math
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from healthvideo.audio.music import (
    MUSIC_DB,
    _command,
    _wav_info,
    mix_with_ducking,
    shared_repo_root,
)
from healthvideo.domain.license_ledger import LicenseEntry
from healthvideo.storage.files import canonical_json_hash, sha256_file

SFX_ROOT = Path(__file__).resolve().parents[3] / 'assets/sfx'
SFX_VERSION = 'cc0-bed-sidechain-v1'


def load_catalog(root: Path = SFX_ROOT) -> dict[str, dict]:
    catalog = {}
    for item in yaml.safe_load((root / 'catalog.yaml').read_text(encoding='utf-8')):
        path = root / item['file']
        if (Path(item['file']).name != item['file'] or item['id'] in catalog
                or item['license'] != 'CC0-1.0' or not item['source_url'].startswith('https://')
                or not item['author'].strip() or not item['mood'].strip()
                or sha256_file(path) != item['sha256']):
            raise ValueError('Invalid CC0 SFX catalog or hash')
        with wave.open(str(path), 'rb') as audio:
            if (audio.getframerate() != 48000 or audio.getnchannels() != 2
                    or audio.getsampwidth() != 2 or not 0 < audio.getnframes() <= 96000):
                raise ValueError('SFX must be PCM16 48 kHz stereo, at most 2 seconds')
        catalog[item['id']] = item
    return catalog


def _words(value: str) -> list[str]:
    return re.findall(r'\w+', value.casefold())


def _offset(effect, scene, board, root: Path) -> float:
    if isinstance(effect.at, (int, float)):
        return float(effect.at)
    line = scene.script_line_id
    if effect.at == 'start' or not line:
        return 0
    if Path(line).name != line or any(c in line for c in '/\\:'):
        raise ValueError('Unsafe SFX alignment line id')
    path = root / 'audio/alignment' / f'{line}.json'
    if not path.is_file():
        return 0
    rows = json.loads(path.read_text(encoding='utf-8'))
    wanted = _words(effect.at)
    if not wanted:
        return 0
    words = [(word, row['start']) for row in rows for word in _words(row['word'])]
    group_start = min(s.start_frame for s in board.scenes if s.script_line_id == line) / 30
    for index in range(len(words) - len(wanted) + 1):
        if [w[0] for w in words[index:index + len(wanted)]] == wanted:
            offset = float(words[index][1]) + group_start - scene.start_frame / 30
            if math.isfinite(offset) and 0 <= offset < scene.duration_frames / 30:
                return offset
    return 0


def resolve_sfx(board, revision_root: Path) -> list[dict]:
    """Explicit cues take priority; automatic cues fill up to two slots per scene."""
    catalog = load_catalog()
    events = []
    previous_chapter = None
    for scene in board.scenes:
        cues = [(e.id, _offset(e, scene, board, revision_root), e.volume) for e in scene.sfx]
        defaults = []
        if board.sfx_defaults:
            if scene.chapter_id and scene.chapter_id != previous_chapter:
                defaults.append('whoosh-soft')
            if scene.visual == 'source_card':
                defaults.append('chime-soft')
        for name in defaults:
            if len(cues) < 2 and name not in [cue[0] for cue in cues]:
                cues.append((name, 0, .2))
        previous_chapter = scene.chapter_id
        for name, at, volume in cues:
            at = min(at, max(0, scene.duration_frames / 30 - 1 / 48000))
            events.append({'scene': scene.id, 'id': name, 'at': at,
                               'time': scene.start_frame / 30 + at, 'volume': volume,
                               'sha256': catalog[name]['sha256']})
    return events


def sfx_rights(events: list[dict], revision: str) -> list[LicenseEntry]:
    catalog = load_catalog()
    return [LicenseEntry(path=f'audio/sfx/{catalog[name]["file"]}',
                         source=catalog[name]['source_url'], creator=catalog[name]['author'],
                         license='CC0-1.0', rights_basis='Kenney CC0; softened/normalized derivative',
                         revision=revision, sha256=catalog[name]['sha256'])
            for name in sorted({event['id'] for event in events})]


def sfx_identity(board, root: Path) -> dict:
    """Include catalog bytes/provenance and optional external alignment in production cache key."""
    catalog = load_catalog()
    alignments = {}
    for scene in board.scenes:
        if any(isinstance(e.at, str) and e.at != 'start' for e in scene.sfx) and scene.script_line_id:
            line = scene.script_line_id
            if Path(line).name != line or any(c in line for c in '/\\:'):
                raise ValueError('Unsafe SFX alignment line id')
            path = root / 'audio/alignment' / f'{line}.json'
            alignments[line] = sha256_file(path) if path.is_file() else None
    return {'version': SFX_VERSION, 'catalog': catalog, 'alignment': alignments}


def mix_sfx(voice: Path, events: list[dict], *, out: Path, music: Path | None = None,
            cache_dir: Path | None = None, runner=subprocess.run) -> Path:
    """Premix attenuated music and quiet SFX, then duck the entire bed under speech.

    Catalog RMS is -26 dBFS, then cue volume is 0.15–0.4. Unlike the old music
    path, gain is applied to music BEFORE premixing; ducking uses unity bed gain.
    """
    catalog = load_catalog()
    frames, rate, _ = _wav_info(voice)
    duration = frames / rate
    key = canonical_json_hash({'version': SFX_VERSION, 'voice': sha256_file(voice), 'events': events,
                                   'files': {e['id']: catalog[e['id']]['sha256'] for e in events},
                                   'music': sha256_file(music) if music else None, 'music_db': MUSIC_DB})
    cache = cache_dir if cache_dir is not None else shared_repo_root() / 'cache/sfx'
    cache.mkdir(parents=True, exist_ok=True)
    cached, receipt = cache / f'{key}.wav', cache / f'{key}.json'
    valid = False
    try:
        valid = (json.loads(receipt.read_text())['sha256'] == sha256_file(cached)
                 and _wav_info(cached) == (round(duration * 48000), 48000, 2))
    except (OSError, ValueError, KeyError):
        pass
    if not valid:
        with TemporaryDirectory(prefix='.sfx-', dir=cache) as temporary:
            temp = Path(temporary)
            argv = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y']
            if music:
                argv += ['-stream_loop', '-1', '-i', str(music)]
                filters = [f'[0:a]volume={MUSIC_DB}dB,apad,atrim=duration={duration:.9f}[base]']
            else:
                argv += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
                filters = [f'[0:a]atrim=duration={duration:.9f}[base]']
            labels = ['[base]']
            for index, event in enumerate(events, 1):
                argv += ['-i', str(SFX_ROOT / catalog[event['id']]['file'])]
                samples = round(event['time'] * 48000)
                filters.append(f'[{index}:a]volume={event["volume"]},adelay={samples}S:all=1[e{index}]')
                labels.append(f'[e{index}]')
            filters.append(''.join(labels) + f'amix=inputs={len(labels)}:duration=first:normalize=0[bed]')
            filter_path = temp / 'filters.txt'
            filter_path.write_text(';'.join(filters), encoding='utf-8')
            bed = temp / 'bed.wav'
            _command(argv + ['-filter_complex_script', str(filter_path), '-map', '[bed]',
                             '-t', f'{duration:.9f}', '-ar', '48000', '-ac', '2',
                             '-c:a', 'pcm_s16le', str(bed)], runner, 'SFX premix')
            mixed = temp / 'mixed.wav'
            mix_with_ducking(voice, bed, out=mixed, music_db=0, runner=runner)
            digest = sha256_file(mixed)
            os.replace(mixed, cached)
            receipt.write_text(json.dumps({'sha256': digest}), encoding='utf-8')
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cached, out)
    return out
