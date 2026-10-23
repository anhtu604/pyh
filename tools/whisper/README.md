# Local Whisper alignment

Run the following with the factory Python (and `PYTHONPATH=src`):

```powershell
& 'E:/Protect Your Health/.venv/Scripts/python.exe' tools/whisper/setup.py
```

`setup.py` creates the shared repository's `cache/whisper-venv`, installs the
pinned runtime, and downloads the pinned model into `cache/models/whisper-large-v3`.
Production only reads local weights; it never downloads them automatically.

The runtime can be overridden with `HEALTHVIDEO_WHISPER_PYTHON`.
`HEALTHVIDEO_WHISPER_DEVICE` accepts `auto` (default), `cuda`, or `cpu`.
`HEALTHVIDEO_WHISPER_COMPUTE_TYPE` overrides the default CUDA `int8_float16`
or CPU `int8`. In auto mode a CUDA runtime/OOM failure retries on CPU.
GPU jobs run sequentially: illustrations, TTS, Whisper, then music.

On Windows, CUDA 12/cuDNN 9 DLL directories can be supplied through
`HEALTHVIDEO_WHISPER_DLL_DIRS` (semicolon separated). The helper also checks the
existing FLUX/music torch library directories, without importing their models.
FFmpeg decodes audio to mono 16 kHz float32, avoiding a PyAV 19 decoder API change.

Model choice: **faster-whisper 1.2.1 / CTranslate2 4.8.3 / large-v3**. The runtime
and converted model are MIT licensed, support Vietnamese and word timestamps,
and run quantized on the RTX 3060. PhoWhisper has not been benchmarked here;
there is no evidence from this task that it improves this corpus.

- Runtime/license: https://github.com/SYSTRAN/faster-whisper
- Weights/license: https://huggingface.co/Systran/faster-whisper-large-v3
- Pinned revision: `edaa852ec7e145841d8ffdb056a99866b5f0a478`

Raw ASR is cached by WAV bytes, pinned model/version and execution settings.
It receives no script prompt, so pronunciation errors are not hidden by biasing.
Per-line output contains canonical script words, measured anchors, interpolated
unmatched words (`matched: false`), probabilities and heard alternatives.
Scene word/cue/entrance frames are local, including scenes sharing one line WAV.
A line with no matched anchors uses legacy caption/cue timing and remains in QA.
Missing runtime/weights or ASR errors warn and use estimated timing.

`produce` stores output beside the existing line WAVs in
`renders/audio/alignment/<line>.json`; it promotes the pronunciation report to
`reviews/pronunciation-qa.json`. The video packet links directly to line audio
and video timestamps. ASR flags require human listening; scripts and lexicon
are never automatically edited.

A reproducible benchmark copies source WAVs before inference, checks unchanged
source hashes, prints JSON and stores its scratch outputs under the chosen path:

```powershell
$env:PYTHONPATH='src'
$env:HEALTHVIDEO_WHISPER_DEVICE='cuda'
& 'E:/Protect Your Health/.venv/Scripts/python.exe' tools/whisper/benchmark.py --lines 'E:/Protect Your Health/projects/gout-tinh-the-urat/revisions/001/renders/audio/lines' --script 'E:/Protect Your Health/projects/gout-tinh-the-urat/revisions/001/script/script.yaml' --out 'E:/Protect Your Health/cache/align-try'
```

Keep all venvs, downloaded weights, audio and scratch reports out of Git.
