import hashlib
import json
import wave

from healthvideo.render.timing import calibrated_rate
from healthvideo.storage.files import canonical_json_hash, sha256_file


def test_loudnorm_receipts_calibrate_the_published_voice(tmp_path):
    settings = {'speed': 1.0}
    runtime = 'rest-' + hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:24]
    profile = {'provider': 'vibi_minimax', 'voice_id': 'v', 'model_id': 'm', 'settings': settings}
    provider = {'provider': 'vibi_minimax', 'voice_id': 'v', 'model_id': 'm',
                'runtime_id': f'{runtime}-loudnorm'}
    request = {'text': 'x' * 42, 'language': 'vi', 'speed': 1.0, 'delivery_beats': []}
    cache = tmp_path / 'cache/tts'
    cache.mkdir(parents=True)
    stem = canonical_json_hash({'request': request, 'provider': provider})
    wav = cache / f'{stem}.wav'
    with wave.open(str(wav), 'wb') as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(1000)
        out.writeframes(b'\0\0' * 2000)  # 2 s
    (cache / f'{stem}.json').write_text(json.dumps(
        {'provider': provider, 'request': request, 'sha256': sha256_file(wav)}), encoding='utf-8')
    assert calibrated_rate(tmp_path, 'vi', voice_profile=profile) == 21.0
    assert calibrated_rate(tmp_path, 'en', voice_profile=profile) is None
