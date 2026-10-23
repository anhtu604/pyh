import json
import math
import shutil
import struct
import wave

import pytest
from pydantic import ValidationError

from healthvideo.domain.storyboard import Scene, Storyboard


def scene(**kwargs):
    return Scene(id='S01', start_frame=0, duration_frames=90, narration='test',
                 script_line_id='LN01', visual='whiteboard', on_screen_text='test', **kwargs)


def test_sfx_catalog_all_cc0_with_hash():
    from healthvideo.audio.sfx import load_catalog
    catalog = load_catalog()
    assert 6 <= len(catalog) <= 8
    for item in catalog.values():
        assert item['license'] == 'CC0-1.0'
        assert item['source_url'].startswith('https://kenney.nl/')
        assert len(item['sha256']) == 64


@pytest.mark.parametrize('effects', [
    [{'id': 'unknown', 'at': 'start', 'volume': .2}],
    [{'id': 'tick', 'at': 'start', 'volume': .5}],
    [{'id': 'tick', 'at': 'start', 'volume': .1}],
    [{'id': 'tick', 'at': -1, 'volume': .2}],
    [{'id': 'tick', 'at': 'start', 'volume': .2}] * 3,
])
def test_storyboard_sfx_limits(effects):
    with pytest.raises(ValidationError):
        scene(sfx=effects)


def test_default_sfx_on_chapter_and_source_card(tmp_path):
    from healthvideo.audio.sfx import resolve_sfx
    first = scene(chapter_id='CH01')
    card = Scene(id='S02', start_frame=90, duration_frames=90, narration='source',
                 chapter_id='CH01', visual='source_card', claim_id='C01', source_marker='[1]',
                 source_card={'source_id': 'R1', 'title': 'Test', 'journal': 'Test', 'interpretation': 'Test'})
    board = Storyboard(title='test', scenes=(first, card))
    events = resolve_sfx(board, tmp_path)
    assert [(e['scene'], e['id'], e['time']) for e in events] == [
        ('S01', 'whoosh-soft', 0), ('S02', 'chime-soft', 3)]
    assert resolve_sfx(board.model_copy(update={'sfx_defaults': False}), tmp_path) == []


def test_sfx_keyword_alignment_and_fallback(tmp_path):
    from healthvideo.audio.sfx import resolve_sfx
    board = Storyboard(title='test', sfx_defaults=False, scenes=(scene(sfx=[
        {'id': 'tick', 'at': 'tinh thể', 'volume': .2}]),))
    assert resolve_sfx(board, tmp_path)[0]['at'] == 0
    folder = tmp_path / 'audio/alignment'
    folder.mkdir(parents=True)
    (folder / 'LN01.json').write_text(json.dumps([
        {'word': 'Tinh', 'start': .4, 'end': .5}, {'word': 'thể,', 'start': .5, 'end': .8}]))
    assert resolve_sfx(board, tmp_path)[0]['at'] == .4


def test_ledger_records_sfx():
    from healthvideo.audio.sfx import sfx_rights
    entries = sfx_rights([{'id': 'tick'}], '001')
    assert entries[0].source.startswith('https://kenney.nl/')
    assert entries[0].license == 'CC0-1.0'
    assert len(entries[0].sha256) == 64


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg required')
def test_sfx_mixed_below_voice(tmp_path):
    from healthvideo.audio.sfx import mix_sfx
    voice = tmp_path / 'voice.wav'
    with wave.open(str(voice), 'wb') as f:
        f.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
        f.writeframes(b''.join(struct.pack('<hh', *([int(5000 * math.sin(i * 2 * math.pi * 220 / 48000))] * 2))
                              for i in range(48000)))
    out = tmp_path / 'mixed.wav'
    events = [{'scene': 'S01', 'id': 'chime-soft', 'at': 0, 'time': 0, 'volume': .4}]
    mix_sfx(voice, events, out=out, cache_dir=tmp_path / 'cache')
    def samples(path):
        with wave.open(str(path), 'rb') as f:
            raw = f.readframes(f.getnframes())
            return struct.unpack('<' + 'h' * (len(raw) // 2), raw)
    v, mixed = samples(voice), samples(out)
    assert len(v) == len(mixed)
    voice_rms = math.sqrt(sum(x*x for x in v) / len(v))
    sfx_rms = math.sqrt(sum((b-a)**2 for a,b in zip(v,mixed)) / len(v))
    assert 0 < sfx_rms < voice_rms / 4


def test_video_packet_lists_sfx(tmp_path):
    from healthvideo.storage.files import write_yaml_atomic
    from healthvideo.workflows.review_html import render_video_packet
    from tests.helpers import create_v2_project_fixture
    revision = create_v2_project_fixture(tmp_path) / 'revisions/001'
    write_yaml_atomic(revision / 'renders/render-manifest.json', {'sfx': [
        {'scene': 'S01', 'id': 'tick', 'at': .5, 'time': 2.5, 'volume': .2}]})
    html = render_video_packet(revision)
    assert '<h2>SFX' in html
    assert 'S01' in html and 'tick' in html and '2.5' in html


def test_sfx_production_package_and_cache(tmp_path):
    from datetime import UTC, datetime
    from pathlib import Path

    from healthvideo.domain.gate_review import GateKind
    from healthvideo.domain.project_v2 import WorkflowState
    from healthvideo.storage.files import read_yaml, write_yaml_atomic
    from healthvideo.tts.silent import SilentTTS
    from healthvideo.workflows.gate_review import approve_gate
    from healthvideo.workflows.package import package_project
    from healthvideo.workflows.produce import produce_project
    from tests.helpers import create_v2_project_fixture, write_posts_fixture

    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    root = project / 'revisions/001'
    board = read_yaml(root / 'storyboard/storyboard.yaml')
    board['scenes'][0]['sfx'] = [{'id': 'tick', 'at': 'start', 'volume': .2}]
    write_yaml_atomic(root / 'storyboard/storyboard.yaml', board)
    now = datetime(2026, 10, 23, tzinfo=UTC)
    approve_gate(project, GateKind.MEDICAL, reviewer='test', now=now)
    def render(argv):
        Path(argv[argv.index('--output') + 1]).write_bytes(b'video')
        return 0
    produce_project(project, SilentTTS(), render, music=False)
    manifest = json.loads((root / 'renders/render-manifest.json').read_text())
    assert manifest['sfx'][0]['id'] == 'tick'
    entries = read_yaml(root / 'renders/license-ledger.yaml')['entries']
    assert entries[0]['license'] == 'CC0-1.0'
    assert (root / 'renders/audio/sfx/tick.wav').is_file()
    produce_project(project, SilentTTS(), lambda _: pytest.fail('cache missed'), music=False)
    write_posts_fixture(root)
    approve_gate(project, GateKind.VIDEO, reviewer='test', now=now)
    package = package_project(project)
    assert json.loads((package / 'audio/sfx.json').read_text())[0]['id'] == 'tick'
    assert read_yaml(package / 'audio/license-ledger.yaml')['entries'][0]['sha256'] == entries[0]['sha256']


def test_clips_preserve_sfx_scene_offsets(tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from pathlib import Path

    from healthvideo.domain.gate_review import GateKind
    from healthvideo.tts.silent import SilentTTS
    from healthvideo.workflows.gate_review import approve_gate
    from healthvideo.workflows.produce import produce_project
    from tests.helpers import create_long_form_project_fixture

    project = create_long_form_project_fixture(tmp_path)
    root = project / 'revisions/001'
    approve_gate(project, GateKind.MEDICAL, reviewer='test', now=datetime(2026, 10, 23, tzinfo=UTC))
    def render(argv):
        out = Path(argv[argv.index('--output') + 1]) if '--output' in argv else Path(argv[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b'video')
        return 0
    produce_project(project, SilentTTS(), render, music=False)
    manifest = json.loads((root / 'renders/render-manifest.json').read_text())
    assert manifest['sfx']
    for clip in manifest['clips']:
        events_path = root / f'renders/audio/clips/{clip}.sfx.json'
        if events_path.exists():
            for event in json.loads(events_path.read_text()):
                original = next(e for e in manifest['sfx'] if e['scene'] == event['scene'] and e['id'] == event['id'])
                assert event['at'] == original['at']
