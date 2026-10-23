"""Run inside cache/whisper-venv. No script/initial prompt is supplied to ASR."""
import argparse
import ctypes
import json
import os
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding='utf-8'))
    # Windows wheels may need the CUDA libraries shipped with a separate torch venv.
    handles = []
    if os.name == 'nt' and os.environ.get('HEALTHVIDEO_WHISPER_DEVICE') != 'cpu':
        cache = Path(request['model']).parents[1]
        directories = [*os.environ.get('HEALTHVIDEO_WHISPER_DLL_DIRS', '').split(os.pathsep),
                       str(cache/'flux-venv/Lib/site-packages/torch/lib'),
                       str(cache/'music-venv/Lib/site-packages/torch/lib')]
        for directory in directories:
            if directory and Path(directory).is_dir():
                handles.append(os.add_dll_directory(directory))
                os.environ['PATH'] = directory + os.pathsep + os.environ.get('PATH', '')
                for name in ('cublasLt64_12.dll', 'cublas64_12.dll', 'cudnn64_9.dll'):
                    library = Path(directory)/name
                    if library.is_file():
                        try:
                            handles.append(ctypes.WinDLL(str(library)))
                        except OSError:
                            pass  # Other DLL paths or the CPU fallback may still work.
    import ctranslate2
    from faster_whisper import WhisperModel

    device = os.environ.get('HEALTHVIDEO_WHISPER_DEVICE', 'auto')
    if device == 'auto':
        device = 'cuda' if ctranslate2.get_cuda_device_count() else 'cpu'
    compute = os.environ.get('HEALTHVIDEO_WHISPER_COMPUTE_TYPE', 'auto')
    if compute == 'auto':
        compute = 'int8_float16' if device == 'cuda' else 'int8'
    import numpy as np

    def decode(wav):
        # Decode with the factory's required FFmpeg; PyAV 19 removed the
        # metadata_errors keyword used by faster-whisper 1.2.1's decoder.
        decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', wav, '-f', 'f32le',
                                  '-ac', '1', '-ar', '16000', 'pipe:1'],
                                 shell=False, capture_output=True, check=True)
        return np.frombuffer(decoded.stdout, dtype=np.float32).copy()

    result = {}
    try:
        model = WhisperModel(request['model'], device=device, compute_type=compute, local_files_only=True)
        for item in request['lines']:
            segments, _ = model.transcribe(decode(item['wav']), language='vi', word_timestamps=True,
                                           beam_size=5, condition_on_previous_text=False,
                                           temperature=0, vad_filter=False)
            result[item['id']] = [{'word': w.word, 'start': w.start, 'end': w.end, 'prob': w.probability}
                                  for segment in segments for w in (segment.words or [])]
    except RuntimeError:
        if device != 'cuda' or os.environ.get('HEALTHVIDEO_WHISPER_DEVICE') == 'cuda':
            raise
        # A busy/unavailable GPU must not block production; CPU int8 needs no VRAM.
        model = WhisperModel(request['model'], device='cpu', compute_type='int8', local_files_only=True)
        for item in request['lines']:
            segments, _ = model.transcribe(decode(item['wav']), language='vi', word_timestamps=True,
                                           beam_size=5, condition_on_previous_text=False, temperature=0)
            result[item['id']] = [{'word': w.word, 'start': w.start, 'end': w.end, 'prob': w.probability}
                                  for segment in segments for w in (segment.words or [])]
    args.out.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
