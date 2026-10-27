import importlib

import pytest

from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import factory


def module():
    return importlib.import_module('healthvideo.workflows.factory_trials')


@pytest.mark.parametrize('stage', [1, 2, 3, 4])
def test_trial_never_starts_production_worker(tmp_path, monkeypatch, stage):
    def forbidden(*args, **kwargs):
        pytest.fail('Production worker called')
    monkeypatch.setattr(factory, 'start_background', forbidden)
    trials = module()
    trial = trials.create_trial(tmp_path, stage)
    result = trials.run_trial(tmp_path, trial['id'])
    assert result['status'] == 'ready'
    assert result['outputs']
    assert trials.trial_bundle(tmp_path, trial['id'])['input_hash'] == result['input_hash']
    assert not (tmp_path / 'topics').exists()
    assert not (tmp_path / 'projects').exists()
    assert not (tmp_path / 'profiles').exists()
    assert all(p.is_relative_to(trials.trial_root(tmp_path)) for p in tmp_path.rglob('*') if p.is_file())


@pytest.mark.parametrize('bad', ['../x', '..', 'a/b', 'a\\b', '/x', 'C:x'])
def test_trial_path_traversal(tmp_path, bad):
    with pytest.raises((ValueError, LookupError)):
        module().trial_bundle(tmp_path, bad)


def test_changed_output_and_input_are_stale(tmp_path):
    trials = module()
    trial = trials.create_trial(tmp_path, 1)
    result = trials.run_trial(tmp_path, trial['id'])
    output = trials.trial_root(tmp_path) / trial['id'] / result['outputs'][0]['path']
    output.write_text('changed', encoding='utf-8')
    assert trials.trial_bundle(tmp_path, trial['id'])['status'] == 'stale'
    record = trials.trial_root(tmp_path) / trial['id'] / 'trial.yaml'
    data = read_yaml(record)
    data['topic'] = 'changed input'
    write_yaml_atomic(record, data)
    assert trials.trial_bundle(tmp_path, trial['id'])['status'] == 'stale'


def test_real_service_is_fail_closed_and_stage_validated(tmp_path):
    trials = module()
    for stage in [0, 5, True, '1']:
        with pytest.raises(ValueError):
            trials.create_trial(tmp_path, stage)
    trial = trials.create_trial(tmp_path, 1)
    with pytest.raises(ValueError, match='real_service'):
        trials.run_trial(tmp_path, trial['id'], real_service=True)


def test_stage_one_script_links_nonmedical_lines(tmp_path):
    outputs = module().build_stage_sample(tmp_path, 1)
    script = read_yaml(next(p for p in outputs if p.name == 'script.yaml'))
    assert script['mode'] == 'TEST'
    assert script['sources'] == []
    assert script['scenes'][0]['script_line'] == script['lines'][0]['id']


def test_samples_include_image_audio_and_seekable_video(tmp_path):
    import wave

    from PIL import Image

    from tools.factory_trial_samples import build_samples
    samples = build_samples(tmp_path)
    assert set(samples) == {1, 2, 3, 4}
    script = read_yaml(next(p for p in samples[1] if p.name == 'script.yaml'))
    assert script['mode'] == 'TEST'
    assert script['sources'] == []
    assert script['scenes'][0]['script_line'] == script['lines'][0]['id']
    assert all(p.is_relative_to(module().trial_root(tmp_path)) for paths in samples.values() for p in paths)
    image = next(p for p in samples[2] if p.suffix == '.png')
    with Image.open(image) as picture:
        assert picture.size == (640, 360)
    audio = next(p for p in samples[2] if p.suffix == '.wav')
    with wave.open(str(audio)) as sound:
        assert sound.getnframes() / sound.getframerate() == 2
    assert len([p for p in samples[3] if p.suffix == '.mp4']) == 2
    assert all(p.stat().st_size > 1000 for p in samples[3] if p.suffix == '.mp4')
