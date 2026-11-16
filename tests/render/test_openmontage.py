import json
import os
import subprocess
import wave
from pathlib import Path

import pytest

from healthvideo.render import openmontage as om
from healthvideo.storage.files import canonical_json_hash, sha256_file


def test_default_selection_preserves_remotion(monkeypatch, tmp_path):
    from healthvideo.render import remotion

    monkeypatch.delenv('PYH_RENDERER', raising=False)
    assert om.selected_renderer() is remotion
    args = (tmp_path / 'i.json', tmp_path / 'o.mp4', tmp_path)
    assert om.selected_renderer().build_render_argv(*args) == remotion.build_render_argv(*args)
    assert canonical_json_hash(om.selected_renderer().renderer_identity()) == canonical_json_hash(remotion.renderer_identity())
    monkeypatch.setenv('PYH_RENDERER', 'openmontage')
    assert om.selected_renderer() is om
    monkeypatch.setenv('PYH_RENDERER', 'typo')
    with pytest.raises(ValueError, match='PYH_RENDERER'):
        om.selected_renderer()


@pytest.mark.parametrize('previous,current', [('remotion', 'openmontage'), ('openmontage', 'remotion')])
def test_pending_visual_preview_never_crosses_renderer(tmp_path, previous, current):
    manifest = tmp_path / 'render-manifest.json'
    manifest.write_text(json.dumps({'renderer_identity': {'name': previous}}))
    om.require_preview_renderer(manifest, previous)
    with pytest.raises(ValueError, match='visual review'):
        om.require_preview_renderer(manifest, current)


def test_missing_checkout_has_install_remedy(tmp_path, monkeypatch):
    monkeypatch.setenv('PYH_OPENMONTAGE_PATH', str(tmp_path / 'missing'))
    with pytest.raises(FileNotFoundError, match='healthvideo openmontage-install'):
        om.renderer_identity()


def test_identity_binds_commit_runtime_and_adapter(tmp_path, monkeypatch):
    checkout = tmp_path / 'checkout'
    source = checkout / 'tools/video/hyperframes_compose.py'
    source.parent.mkdir(parents=True)
    source.write_text('# pinned upstream')
    runtime = checkout / '.pyh-runtime/node_modules/hyperframes'
    (runtime / 'bin').mkdir(parents=True)
    (runtime / 'package.json').write_text(json.dumps({'version': om.HYPERFRAMES_VERSION}))
    script = runtime / 'bin/hyperframes.mjs'
    script.write_text('original runtime')
    monkeypatch.setattr(om, '_browser_path', lambda runtime: script)
    monkeypatch.setenv('PYH_OPENMONTAGE_PATH', str(checkout))
    monkeypatch.delenv('PYH_HYPERFRAMES_PATH', raising=False)
    monkeypatch.setattr(om, '_git', lambda path, *args: om.COMMIT if args[0] == 'rev-parse' else '')
    monkeypatch.setattr(om.shutil, 'which', lambda name: name)
    monkeypatch.setattr(om, 'run_bounded', lambda *a, **kw: subprocess.CompletedProcess(a, 0, 'v22.0.0'))
    identity = om.renderer_identity()
    assert identity['name'] == 'openmontage' and identity['commit'] == om.COMMIT
    assert identity['version'] == om.VERSION
    script.write_text('changed runtime')
    assert om.renderer_identity() != identity
    monkeypatch.setattr(om, '_git', lambda *a: 'wrong-commit')
    with pytest.raises(ValueError, match='commit'):
        om.renderer_identity()


def test_timeout_uses_bounded_process_and_keeps_log(tmp_path, monkeypatch):
    monkeypatch.setattr(om, 'ROOT', tmp_path)

    def timeout(argv, **kwargs):
        assert kwargs['shell'] is False and kwargs['timeout'] == om.TIMEOUT
        raise subprocess.TimeoutExpired(argv, kwargs['timeout'])

    monkeypatch.setattr(om, 'run_bounded', timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        om.run_render_argv(['fake-render'])
    logs = list((tmp_path / 'topics/logs/render').glob('openmontage-*.log'))
    assert len(logs) == 1 and 'TimeoutExpired' in logs[0].read_text()


def test_install_is_explicit_and_pins_checkout_and_runtime(tmp_path, monkeypatch):
    checkout = tmp_path / 'checkout'
    commands = []
    monkeypatch.setattr(om, '_git', lambda path, *args: om.COMMIT if args[0] == 'rev-parse' else '')
    monkeypatch.setattr(om, '_npm_argv', lambda: ['node', 'npm-cli.js'])
    monkeypatch.setattr(om, 'run_bounded', lambda argv, **kw: commands.append(argv))
    assert om.install(checkout) == checkout
    assert commands[0] == ['git', 'clone', '--no-checkout', 'https://github.com/calesthio/OpenMontage', str(checkout)]
    assert f'hyperframes@{om.HYPERFRAMES_VERSION}' in commands[1]
    assert commands[1][:2] == ['node', 'npm-cli.js']
    assert commands[2][-2:] == ['browser', 'ensure']


def test_npm_uses_node_entrypoint_without_cmd_shell(tmp_path, monkeypatch):
    node = tmp_path / 'node.exe'
    script = tmp_path / 'node_modules/npm/bin/npm-cli.js'
    script.parent.mkdir(parents=True)
    script.write_text('// npm')
    monkeypatch.setattr(om.shutil, 'which', lambda command: str(node if command == 'node' else tmp_path / 'npm.cmd'))
    assert om._npm_argv() == [str(node), str(script)]


def test_doctor_optional_failure_is_warning(monkeypatch):
    from typer.testing import CliRunner

    from healthvideo import cli

    monkeypatch.setattr(cli, 'check_environment', lambda runner: [])
    monkeypatch.setattr(om, 'renderer_identity', lambda: (_ for _ in ()).throw(FileNotFoundError('optional absent')))
    result = CliRunner().invoke(cli.app, ['doctor'])
    assert result.exit_code == 0
    assert 'WARN OpenMontage (optional)' in result.stdout


def fixture_props(tmp_path):
    with wave.open(str(tmp_path / 'tone.wav'), 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        # Original synthetic tone, no third-party media or TTS.
        import math
        import struct

        wav.writeframes(b''.join(struct.pack('<h', int(5000 * math.sin(i * 2 * math.pi * 440 / 24000)))
                                 for i in range(48000)))
    props = {'title': 'Kiểm thử', 'audio_file': 'tone.wav', 'width': 1920,
             'height': 1080, 'fps': 30, 'scenes': [
                 {'id': 'S01', 'start_frame': 0, 'duration_frames': 60,
                  'visual': 'whiteboard', 'on_screen_text': 'Xin chào',
                  'narration': 'Xin chào', 'words': [
                      {'text': 'Xin', 'start_frame': 0, 'end_frame': 30},
                      {'text': 'chào', 'start_frame': 30, 'end_frame': 60}],
                  'visual_assets': []}]}
    path = tmp_path / 'props.json'
    path.write_text(json.dumps(props), encoding='utf-8')
    return path


def test_argv_and_renderer_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(om, 'renderer_identity', lambda: {'name': 'openmontage', 'commit': om.COMMIT, 'version': om.VERSION})
    argv = om.build_render_argv(tmp_path / 'i.json', tmp_path / 'o.mp4', tmp_path)
    assert argv[1:3] == ['-m', 'healthvideo.render.openmontage']
    for flag in ('--props', '--output', '--public-dir'):
        assert Path(argv[argv.index(flag) + 1]).is_absolute()
    from healthvideo.render.remotion import renderer_identity

    assert canonical_json_hash(om.renderer_identity()) != canonical_json_hash(renderer_identity())


def test_workspace_uses_real_frame_timing_and_escaped_text(tmp_path):
    path = fixture_props(tmp_path)
    workspace = om.materialize_workspace(path, tmp_path)
    html = (workspace / 'index.html').read_text(encoding='utf-8')
    assert 'data-duration="2.0"' in html
    assert 'data-start="1.0"' in html
    assert 'chào' in html
    assert '<audio' in html and 'tone.wav' in html
    assert (workspace / 'tone.wav').read_bytes() == (tmp_path / 'tone.wav').read_bytes()


@pytest.mark.parametrize('code,error', [(2, RuntimeError), (0, FileNotFoundError)])
def test_runner_failure_and_missing_mp4(tmp_path, monkeypatch, code, error):
    monkeypatch.setattr(om, 'build_render_argv', lambda *args: ['fake'])
    with pytest.raises(error, match='OpenMontage'):
        om.render(tmp_path / 'i.json', tmp_path / 'o.mp4', tmp_path, runner=lambda argv: code)


def test_produce_selection_changes_hash_and_keeps_qa(tmp_path, monkeypatch):
    from healthvideo.tts.silent import SilentTTS
    from healthvideo.workflows.produce import produce_project
    from tests.workflows.test_produce import (
        _v2_medically_approved_project,
        _write_synthetic_output,
    )

    project = _v2_medically_approved_project(tmp_path)
    monkeypatch.delenv('PYH_RENDERER', raising=False)
    calls = []

    def fake(argv):
        calls.append(argv)
        _write_synthetic_output(argv)
        return 0

    output = produce_project(project, SilentTTS(), fake)
    manifest = output.parent / 'render-manifest.json'
    original = json.loads(manifest.read_text())
    assert original['renderer_identity']['name'] == 'remotion'
    assert calls[0][:2] == ['pnpm', '--dir']
    monkeypatch.setenv('PYH_RENDERER', 'remotion')
    produce_project(project, SilentTTS(), fake)
    assert json.loads(manifest.read_text())['input_hash'] == original['input_hash']
    assert len(calls) == 1
    monkeypatch.setenv('PYH_RENDERER', 'openmontage')
    monkeypatch.setattr(om, 'renderer_identity', lambda: {'name': 'openmontage', 'commit': om.COMMIT, 'version': om.VERSION})
    produce_project(project, SilentTTS(), fake)
    current = json.loads(manifest.read_text())
    assert current['input_hash'] != original['input_hash']
    assert current['renderer_identity']['name'] == 'openmontage'
    assert calls[-1][1:3] == ['-m', 'healthvideo.render.openmontage']
    assert (output.parent.parent / 'reviews/video-qa.json').is_file()
    assert (output.parent / 'pronunciation-qa.json').is_file()


def test_unsupported_anatomy_fails_explicitly(tmp_path):
    path = fixture_props(tmp_path)
    props = json.loads(path.read_text())
    props['scenes'][0]['visual'] = 'anatomy_animation'
    path.write_text(json.dumps(props))
    with pytest.raises(ValueError, match='anatomy_animation'):
        om.materialize_workspace(path, tmp_path)


def test_asset_sha_and_provenance_required(tmp_path):
    path = fixture_props(tmp_path)
    image = tmp_path / 'image.svg'
    image.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    props = json.loads(path.read_text())
    props['scenes'][0]['visual_assets'] = [{'path': 'image.svg', 'role': 'whiteboard'}]
    path.write_text(json.dumps(props))
    with pytest.raises(ValueError, match='license/source/SHA'):
        om.materialize_workspace(path, tmp_path)
    rights = [{'path': 'image.svg', 'source': 'generated:test', 'license': 'CC0', 'sha256': sha256_file(image)}]
    om.materialize_workspace(path, tmp_path, assets=rights)
    image.write_text('changed')
    with pytest.raises(ValueError, match='SHA'):
        om.materialize_workspace(path, tmp_path, assets=rights)


@pytest.mark.skipif(os.environ.get('PYH_OPENMONTAGE_SMOKE') != '1', reason='Opt-in OpenMontage runtime smoke')
def test_real_audio_subtitle_smoke(tmp_path):
    props = fixture_props(tmp_path)
    output = tmp_path / 'smoke.mp4'
    om.render(props, output, tmp_path)
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                            '-of', 'json', str(output)], capture_output=True, text=True, check=True)
    report = json.loads(probe.stdout)
    assert abs(float(report['format']['duration']) - 2.0) <= 0.2
    assert {s['codec_type'] for s in report['streams']} >= {'audio', 'video'}
    assert output.stat().st_size > 1000
