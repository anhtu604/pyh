"""Install the optional isolated runtime and explicitly download pinned weights."""
import subprocess
import sys
import venv
from pathlib import Path

from healthvideo.audio.align import (
    MODEL_ID,
    MODEL_REVISION,
    whisper_model,
    whisper_python,
)
from healthvideo.audio.music import shared_repo_root


def main():
    root = shared_repo_root()
    environment = root/'cache/whisper-venv'
    python = whisper_python()
    if not python.is_file():
        venv.create(environment, with_pip=True)
        python = environment/'Scripts/python.exe' if sys.platform == 'win32' else environment/'bin/python'
    requirements = Path(__file__).with_name('requirements.txt')
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(requirements)], check=True)
    code = (
        'from huggingface_hub import snapshot_download; import sys; '
        'snapshot_download(sys.argv[1],revision=sys.argv[2],local_dir=sys.argv[3],'
        'allow_patterns=["model.bin","config.json","tokenizer.json",'
        '"preprocessor_config.json","vocabulary.json","README.md"])'
    )
    subprocess.run([str(python), '-c', code, MODEL_ID, MODEL_REVISION, str(whisper_model())], check=True)


if __name__ == '__main__':
    main()
