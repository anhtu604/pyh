"""Rebuild the small CC0 library from Kenney's original archive (no credentials)."""

import array
import hashlib
import math
import shutil
import subprocess
import tempfile
import urllib.request
import wave
import zipfile
from pathlib import Path

import yaml

URL = 'https://kenney.nl/media/pages/assets/interface-sounds/fa43c1dd4d-1677589452/kenney_interface-sounds.zip'
CHOICES = [('whoosh-soft', 'open_001', .75), ('chime-soft', 'glass_001', .8),
           ('pop-soft', 'drop_001', .85), ('tick', 'tick_001', .85),
           ('swell-low', 'maximize_001', .5), ('chime-warm', 'confirmation_001', .65),
           ('tap-soft', 'select_001', .8)]


def main():
    out = Path(__file__).resolve().parents[2] / 'assets/sfx'
    out.mkdir(parents=True, exist_ok=True)
    items = []
    with tempfile.TemporaryDirectory() as temporary:
        src = Path(temporary)
        archive = src / 'original.zip'
        urllib.request.urlretrieve(URL, archive)
        with zipfile.ZipFile(archive) as z:
            for name in ['License.txt', *(f'Audio/{original}.ogg' for _, original, _ in CHOICES)]:
                z.extract(name, src)
        for name, original, speed in CHOICES:
            path = out / f'{name}.wav'
            filters = (f'asetrate=44100*{speed},aresample=48000,lowpass=f=2400,'
                       'atrim=duration=1.95,afade=t=in:d=0.012,areverse,afade=t=in:d=0.06,areverse')
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(src / f'Audio/{original}.ogg'),
                            '-af', filters, '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(path)], check=True)
            with wave.open(str(path), 'rb') as audio:
                data = array.array('h', audio.readframes(audio.getnframes()))
            rms = math.sqrt(sum(x*x for x in data) / len(data))
            peak = max(abs(x) for x in data)
            gain = min(32767 * 10**(-26/20) / rms, 32767 * 10**(-12/20) / peak)
            data = array.array('h', (round(x * gain) for x in data))
            with wave.open(str(path), 'wb') as audio:
                audio.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
                audio.writeframes(data.tobytes())
            items.append(dict(id=name, file=path.name, source_url='https://kenney.nl/assets/interface-sounds',
                              license='CC0-1.0', author='Kenney',
                              sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                              mood='calm, soft, restrained', original_file=f'Audio/{original}.ogg'))
            print(name, original, path.stat().st_size, round(len(data) / 2 / 48000, 3))
        shutil.copyfile(src / 'License.txt', out / 'LICENSE-Kenney.txt')
    (out / 'catalog.yaml').write_text(yaml.safe_dump(items, sort_keys=False), encoding='utf-8')


if __name__ == '__main__':
    main()
