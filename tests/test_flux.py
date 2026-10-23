import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from PIL import Image


def test_illustration_cached_by_hash(tmp_path, monkeypatch):
    from healthvideo.visuals import flux

    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        assert kwargs['shell'] is False
        size = tuple(int(argv[argv.index(flag) + 1]) for flag in ('--width', '--height'))
        Image.new('RGB', size, 'green').save(Path(argv[argv.index('--out') + 1]))
        return CompletedProcess(argv, 0, json.dumps({'width': 64, 'height': 32, 'seed': 42}), '')

    monkeypatch.setenv('HEALTHVIDEO_FLUX_PYTHON', 'custom-python.exe')
    cache = tmp_path / 'cache'
    for name in ('first', 'second'):
        out = tmp_path / f'{name}.png'
        assert flux.generate_illustration('park', out=out, width=64, height=32,
                                          seed=42, runner=runner, cache_dir=cache) == out
        assert Image.open(out).size == (64, 32)
    assert len(calls) == 1
    assert calls[0][0] == 'custom-python.exe'
    for prompt, width, height, seed in [('other', 64, 32, 42), ('park', 64, 32, 43)]:
        flux.generate_illustration(prompt, out=tmp_path / 'changed.png', width=width,
                                   height=height, seed=seed, runner=runner, cache_dir=cache)
    assert len(calls) == 3
    for width, height in [(32, 64), (128, 32), (64, 64)]:
        flux.generate_illustration('park', out=tmp_path / 'resized.png', width=width,
                                   height=height, seed=42, runner=runner, cache_dir=cache)
    assert len(calls) == 6
    monkeypatch.setattr(flux, 'MODEL_ID', 'other-model-for-cache-test')
    flux.generate_illustration('park', out=tmp_path / 'model.png', width=64, height=32,
                               seed=42, runner=runner, cache_dir=cache)
    assert len(calls) == 7
    next(cache.glob('*.png')).write_bytes(b'broken')
    # Corruption must never silently escape the content-addressed cache.
    for key in cache.glob('*.png'):
        key.write_bytes(b'broken')
    flux.generate_illustration('park', out=tmp_path / 'fixed.png', width=64, height=32,
                               seed=42, runner=runner, cache_dir=cache)
    assert len(calls) == 8


@pytest.mark.parametrize('field,value', [('prompt', ' '), ('width', 0), ('height', -1), ('seed', -1)])
def test_illustration_rejects_invalid_arguments(tmp_path, field, value):
    from healthvideo.visuals.flux import generate_illustration

    args = {'prompt': 'park', 'width': 64, 'height': 32, 'seed': 42}
    args[field] = value
    with pytest.raises(ValueError):
        generate_illustration(**args, out=tmp_path / 'out.png', cache_dir=tmp_path / 'cache',
                              runner=lambda *a, **k: pytest.fail('invalid input reached model'))


def test_illustration_rejects_wrong_size_and_runner_failure(tmp_path):
    from healthvideo.visuals.flux import generate_illustration

    def runner(argv, **kwargs):
        Image.new('RGB', (32, 32)).save(Path(argv[argv.index('--out') + 1]))
        return CompletedProcess(argv, 0, '', '')

    with pytest.raises(RuntimeError, match='dimensions'):
        generate_illustration('park', out=tmp_path / 'out.png', width=64, height=32,
                              seed=42, runner=runner, cache_dir=tmp_path / 'cache')
    with pytest.raises(RuntimeError, match='CUDA out of memory'):
        generate_illustration('park', out=tmp_path / 'out.png', width=64, height=32,
                              seed=42, cache_dir=tmp_path / 'cache',
                              runner=lambda *a, **k: CompletedProcess([], 1, '', 'CUDA out of memory'))


def illustration_record(**changes):
    return dict(path='assets/illustrations/park.png', kind='illustration', semantic=False,
                source='generated:flux2-klein-4b', license='Apache-2.0', creator='FLUX.2 klein 4B',
                revision='001', prompt='A park without lettering', seed=42,
                storyboard_role='whiteboard', **changes)


@pytest.mark.parametrize('field', ['labels', 'annotations'])
@pytest.mark.parametrize('target', ['assets/illustrations/park.png', 'assets/illustrations/./park.png'])
def test_illustration_asset_rejects_text_labels(tmp_path, field, target):
    from healthvideo.assets import referenced_storyboard_assets
    from healthvideo.domain.asset_manifest import AssetManifest
    from healthvideo.domain.storyboard import Storyboard

    manifest = AssetManifest.model_validate({'assets': [illustration_record()]})
    board = Storyboard.model_validate({'title': 'Park', 'scenes': [{
        'id': 'S01', 'start_frame': 0, 'duration_frames': 90, 'narration': 'Park', 'visual': 'whiteboard', "on_screen_text": "Synthetic illustration.",
        'visual_assets': [{'path': 'assets/illustrations/park.png', 'role': 'whiteboard'}],
        field: [{'asset_path': target, 'text': 'artery'}],
    }]})
    with pytest.raises(ValueError, match='AI illustration.*Remotion.*SVG'):
        referenced_storyboard_assets(tmp_path, board, manifest)


@pytest.mark.parametrize('field,value', [('prompt', None), ('seed', None), ('semantic', True)])
def test_illustration_manifest_requires_decorative_prompt_and_seed(field, value):
    from healthvideo.domain.asset_manifest import AssetRecord

    data = illustration_record()
    data[field] = value
    with pytest.raises(ValueError):
        AssetRecord.model_validate(data)


@pytest.mark.parametrize('heads', [48, 24])
def test_doctor_flags_non_4b_weights(tmp_path, monkeypatch, heads):
    from healthvideo.workflows import doctor

    weights = tmp_path / 'flux2-klein-4b'
    weights.mkdir()
    (weights / 'model_index.json').write_text(json.dumps({'_class_name': 'Flux2KleinPipeline', 'is_distilled': True}))
    for component in ['transformer', 'text_encoder', 'tokenizer', 'vae', 'scheduler']:
        (weights / component).mkdir()
    (weights / 'transformer/config.json').write_text(json.dumps({
        'num_attention_heads': heads, 'num_layers': 5 if heads == 24 else 8,
        'num_single_layers': 20 if heads == 24 else 24, 'joint_attention_dim': 7680,
    }))
    (weights / 'text_encoder/config.json').write_text(json.dumps({'hidden_size': 2560}))
    for component in ['transformer', 'text_encoder', 'vae']:
        (weights / component / 'model.safetensors').write_bytes(b'weights')
    (weights / 'tokenizer/tokenizer.json').write_text('{}')
    (weights / 'vae/config.json').write_text('{}')
    (weights / 'scheduler/scheduler_config.json').write_text('{}')
    monkeypatch.setattr(doctor, 'flux_weights', lambda repo: weights)
    results = doctor.check_environment(lambda argv: (0, '24.14.0'))
    result = next(item for item in results if item.name == 'flux_weights')
    assert result.required == 'recommended'
    assert result.ok is (heads == 24)
    if heads != 24:
        assert '9B/dev' in result.detected


def test_exported_manifest_schema_keeps_existing_hash_required():
    from jsonschema import Draft202012Validator

    from healthvideo.domain.asset_manifest import AssetManifest

    validator = Draft202012Validator(AssetManifest.model_json_schema())
    pending = illustration_record()
    assert not list(validator.iter_errors({'assets': [pending]}))
    for payload in [dict(pending, kind='background'), dict(pending, prompt=None), dict(pending, seed=None)]:
        assert list(validator.iter_errors({'assets': [payload]}))
