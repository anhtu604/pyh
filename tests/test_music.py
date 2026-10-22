import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import pytest

from healthvideo.audio import music


def write_wav(path: Path, seconds: float = 0.25, *, channels: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setparams((channels, 2, 48000, 0, "NONE", "not compressed"))
        audio.writeframes(b"".join(
            struct.pack("<h", int(4000 * math.sin(i * 0.06))) * channels
            for i in range(round(seconds * 48000))
        ))


def test_music_cached_by_hash(tmp_path, monkeypatch):
    monkeypatch.setenv(music.MUSIC_PYTHON_ENV, "isolated-python.exe")
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        assert kwargs["shell"] is False
        assert argv[0] == "isolated-python.exe"
        write_wav(Path(argv[argv.index("--out") + 1]), float(argv[argv.index("--seconds") + 1]))
        return subprocess.CompletedProcess(argv, 0, '{"seconds":0.25,"sample_rate":48000}', "")

    args = {"seconds": 0.25, "seed": 42, "cache_dir": tmp_path / "cache", "runner": runner}
    out = music.generate_music("calm", out=tmp_path / "one.wav", **args)
    music.generate_music("calm", out=tmp_path / "two.wav", **args)
    assert len(calls) == 1
    assert out.read_bytes() == (tmp_path / "two.wav").read_bytes()
    music.generate_music("curious", out=out, **args)
    music.generate_music("curious", out=out, **{**args, "seed": 43})
    music.generate_music("curious", out=out, **{**args, "seconds": 0.5})
    monkeypatch.setattr(music, "MODEL_ID", music.MODEL_ID + "-changed")
    music.generate_music("curious", out=out, **args)
    assert len(calls) == 5


def test_music_worktree_uses_shared_cache(tmp_path, monkeypatch):
    monkeypatch.delenv(music.MUSIC_PYTHON_ENV, raising=False)
    main = tmp_path / "main repo"
    worktree = main / ".claude/worktrees/music"
    git_dir = main / ".git/worktrees/music"
    worktree.mkdir(parents=True)
    git_dir.mkdir(parents=True)
    (worktree / ".git").write_text(f"gitdir: {git_dir.as_posix()}\n")
    (git_dir / "commondir").write_text("../..\n")
    assert music.shared_repo_root(worktree) == main
    assert music.music_python(worktree) == main / "cache/music-venv/Scripts/python.exe"
    assert music.music_weights(worktree) == main / "cache/models/ace-step-1.5"


def test_music_tool_json_contract_without_gpu(tmp_path, monkeypatch, capsys):
    import importlib.util
    import json
    import sys

    spec = importlib.util.spec_from_file_location("music_tool", music.REPO_ROOT / "tools/music/generate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    received = []

    def generate(mood, seconds, seed, out):
        received.append((mood, seconds, seed, out))
        return {"seconds": seconds, "sample_rate": 48000}

    monkeypatch.setattr(module, "generate", generate)
    out = tmp_path / "music.wav"
    monkeypatch.setattr(sys, "argv", ["generate.py", "--mood", "gentle piano", "--seconds", "30",
                                      "--seed", "42", "--out", str(out)])
    assert module.main() == 0
    assert received == [("gentle piano", 30.0, 42, out)]
    assert json.loads(capsys.readouterr().out) == {"seconds": 30.0, "sample_rate": 48000}


def test_music_failure_blocks_with_clear_error(tmp_path):
    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, "", "CUDA out of memory")

    with pytest.raises(RuntimeError, match="ACE-Step.*CUDA out of memory"):
        music.generate_music("calm", seconds=30, seed=42, out=tmp_path / "out.wav",
                             cache_dir=tmp_path / "cache", runner=runner)
    assert not (tmp_path / "out.wav").exists()


def test_music_rejects_wrong_duration_without_poisoning_cache(tmp_path):
    def runner(argv, **kwargs):
        write_wav(Path(argv[argv.index("--out") + 1]), 0.1)
        return subprocess.CompletedProcess(argv, 0, "", "")

    with pytest.raises(RuntimeError, match="duration"):
        music.generate_music("calm", seconds=30, seed=42, out=tmp_path / "out.wav",
                             cache_dir=tmp_path / "cache", runner=runner)
    assert not list((tmp_path / "cache").glob("*.wav"))


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf")])
def test_music_rejects_invalid_duration(tmp_path, seconds):
    with pytest.raises(ValueError):
        music.generate_music("calm", seconds=seconds, seed=42, out=tmp_path / "out.wav")


def test_mix_keeps_narration_duration(tmp_path):
    narration, background, out = (tmp_path / name for name in ("voice.wav", "music.wav", "mix.wav"))
    write_wav(narration, 1.137, channels=1)
    write_wav(background, 0.23)
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        # Exercise FFmpeg when installed; retain a fake-runner contract elsewhere.
        if shutil.which("ffmpeg"):
            kwargs.pop("check")
            return subprocess.run(argv, check=False, **kwargs)
        write_wav(Path(argv[-1]), 1.137)
        return subprocess.CompletedProcess(argv, 0, "", "")

    assert music.mix_with_ducking(narration, background, out=out, runner=runner) == out
    assert "sidechaincompress" in calls[0][calls[0].index("-filter_complex") + 1]
    assert "-stream_loop" in calls[0]
    with wave.open(str(out)) as mixed, wave.open(str(narration)) as voice:
        assert mixed.getnframes() / mixed.getframerate() == voice.getnframes() / voice.getframerate()
        assert mixed.getnchannels() == 2


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is not installed")
def test_mix_ducks_music_during_speech(tmp_path):
    voice, bed, mixed = (tmp_path / name for name in ("voice.wav", "bed.wav", "mixed.wav"))
    # -20 dBFS RMS voice is representative of narration, below the compressor's old threshold.
    samples = [0 if i < 24000 else round(4634 * math.sin(2 * math.pi * 440 * i / 48000))
               for i in range(96000)]
    with wave.open(str(voice), "wb") as audio:
        audio.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        audio.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    with wave.open(str(bed), "wb") as audio:
        audio.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        audio.writeframes(struct.pack("<h", 6000) * 2 * 48000)
    music.mix_with_ducking(voice, bed, out=mixed)
    with wave.open(str(mixed)) as audio:
        data = audio.readframes(audio.getnframes())
    output = struct.unpack(f"<{len(data) // 2}h", data)[::2]
    quiet_bed = sum(output[4800:19200]) / 14400
    speech_bed = sum(output[i] - samples[i] for i in range(48000, 72000)) / 24000
    assert speech_bed < quiet_bed * 0.4  # At least 8 dB less music under speech.


def test_music_doctor_is_recommended(tmp_path, monkeypatch):
    from healthvideo.workflows import doctor

    monkeypatch.setattr(doctor, "REPO_ROOT", tmp_path)
    monkeypatch.delenv(music.MUSIC_PYTHON_ENV, raising=False)
    checks = {check.name: check for check in doctor.check_environment(lambda _: (0, "24.14.0"))}
    for name in ("music_venv", "music_weights"):
        assert checks[name].required == "recommended"
        assert not checks[name].ok
        assert not doctor.has_mandatory_failure([checks[name]])


def test_mix_rejects_ducking_beyond_ffmpeg_threshold_range(tmp_path):
    with pytest.raises(ValueError, match="Ducking"):
        music.mix_with_ducking(tmp_path / "missing.wav", tmp_path / "bed.wav",
                               out=tmp_path / "mix.wav", duck_db=-40)
