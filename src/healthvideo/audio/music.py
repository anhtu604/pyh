"""ACE-Step runs in its own environment; FFmpeg mixes without a command shell."""

import hashlib
import json
import math
import os
import shutil
import subprocess
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

MUSIC_PYTHON_ENV = "HEALTHVIDEO_MUSIC_PYTHON"
MODEL_ID = "ace-step-1.5/acestep-v15-turbo+acestep-5Hz-lm-1.7B:pt-offload-v1"
DEFAULT_MOOD = "calm curious documentary"
MUSIC_SECONDS = 30.0
MUSIC_SEED = 42
MUSIC_DB = -20.0
DUCK_DB = -12.0
MIX_VERSION = "sidechain-v1"
REPO_ROOT = Path(__file__).resolve().parents[3]


def shared_repo_root(repo: Path = REPO_ROOT) -> Path:
    """Resolve a linked worktree's cache to the main repository, without shelling out."""
    git_file = repo / ".git"
    if git_file.is_file():
        content = git_file.read_text(encoding="utf-8").strip()
        if content.startswith("gitdir: "):
            git_dir = (repo / content[8:]).resolve()
            common = git_dir / "commondir"
            if common.is_file():
                return (git_dir / common.read_text(encoding="utf-8").strip()).resolve().parent
    return repo


def music_python(repo: Path = REPO_ROOT) -> Path:
    return Path(os.environ.get(
        MUSIC_PYTHON_ENV, str(shared_repo_root(repo) / "cache/music-venv/Scripts/python.exe")
    ))


def music_weights(repo: Path = REPO_ROOT) -> Path:
    return shared_repo_root(repo) / "cache/models/ace-step-1.5"


def _wav_info(path: Path) -> tuple[int, int, int]:
    try:
        with wave.open(str(path), "rb") as audio:
            if audio.getnframes() <= 0:
                raise ValueError("WAV is empty")
            remaining = audio.getnframes()
            while remaining:
                count = min(remaining, 8192)
                if len(audio.readframes(count)) != count * audio.getnchannels() * audio.getsampwidth():
                    raise ValueError("WAV is truncated")
                remaining -= count
            return audio.getnframes(), audio.getframerate(), audio.getnchannels()
    except (OSError, wave.Error, EOFError) as error:
        raise ValueError(f"Invalid audio WAV: {path}") from error


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _command(argv: list[str], runner, label: str) -> None:
    try:
        result = runner(argv, shell=False, check=False, capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    except OSError as error:
        raise RuntimeError(f"{label} could not start: {error}") from error
    if result.returncode:
        detail = (result.stderr or result.stdout or "no diagnostic output").strip()
        raise RuntimeError(f"{label} failed (exit {result.returncode}): {detail[-4000:]}")


def generate_music(
    mood: str, *, seconds: float, out: Path, seed: int,
    runner=subprocess.run, cache_dir: Path | None = None,
) -> Path:
    """Cache instrumental PCM WAV by mood, duration, seed and explicit model identity."""
    if not mood.strip() or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Music needs a nonempty mood and a positive finite duration")
    key = hashlib.sha256(json.dumps(
        [mood, float(seconds), seed, MODEL_ID], ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    cache = cache_dir if cache_dir is not None else shared_repo_root() / "cache/music"
    cache.mkdir(parents=True, exist_ok=True)
    cached, metadata = cache / f"{key}.wav", cache / f"{key}.json"
    valid = False
    if cached.is_file() and metadata.is_file():
        try:
            frames, rate, channels = _wav_info(cached)
            valid = (rate == 48000 and channels == 2 and abs(frames / rate - seconds) <= 1 / rate
                     and json.loads(metadata.read_text(encoding="utf-8"))["sha256"] == _sha256(cached))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    if not valid:
        with TemporaryDirectory(prefix=".music-", dir=cache) as temporary:
            generated = Path(temporary) / "music.wav"
            _command([
                str(music_python()), "-X", "utf8", str(REPO_ROOT / "tools/music/generate.py"),
                "--mood", mood, "--seconds", str(float(seconds)), "--seed", str(seed),
                "--out", str(generated),
            ], runner, "ACE-Step music generation")
            if not generated.is_file():
                raise RuntimeError("ACE-Step music generation did not create a WAV")
            frames, rate, channels = _wav_info(generated)
            if rate != 48000 or channels != 2:
                raise RuntimeError("ACE-Step music must be 48 kHz stereo WAV")
            if abs(frames / rate - seconds) > 1 / rate:
                raise RuntimeError("ACE-Step music duration differs from the requested duration")
            digest = _sha256(generated)
            staged_metadata = Path(temporary) / "music.json"
            staged_metadata.write_text(json.dumps({"sha256": digest, "model_id": MODEL_ID}), encoding="utf-8")
            os.replace(generated, cached)
            os.replace(staged_metadata, metadata)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.resolve() != cached.resolve():
        with TemporaryDirectory(prefix=".music-copy-", dir=out.parent) as temporary:
            staged = Path(temporary) / "music.wav"
            shutil.copyfile(cached, staged)
            os.replace(staged, out)
    return out


def mix_with_ducking(
    narration: Path, music: Path, *, out: Path, music_db: float = MUSIC_DB,
    duck_db: float = DUCK_DB, runner=subprocess.run,
) -> Path:
    """Loop music under voice. duck_db targets reduction at -20 dBFS RMS speech.

    A 4:1 compressor gives this reduction at nominal speech; quieter speech reduces it less.
    Narration determines the output length, including its reviewed silence padding.
    """
    if not math.isfinite(music_db) or not math.isfinite(duck_db) or not -60 <= music_db <= 0:
        raise ValueError("Music level must be finite and between -60 and 0 dB")
    if not -30 <= duck_db <= 0:
        raise ValueError("Ducking must be between -30 and 0 dB (FFmpeg threshold range)")
    frames, rate, _ = _wav_info(narration)
    _wav_info(music)
    duration = frames / rate
    threshold = 0.1 * 10 ** (duck_db / (20 * 0.75))
    ratio = 1 if duck_db == 0 else 4
    filters = (
        "[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[voice][sc];"
        f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={music_db}dB[bed];"
        f"[bed][sc]sidechaincompress=threshold={threshold:.9f}:ratio={ratio}:attack=20:release=300:detection=rms[ducked];"
        f"[voice][ducked]amix=inputs=2:duration=first:normalize=0,"
        f"apad,atrim=duration={duration:.9f}[mixed]"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".music-mix-", dir=out.parent) as temporary:
        staged = Path(temporary) / "mixed.wav"
        _command([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(narration), "-stream_loop", "-1", "-i", str(music),
            "-filter_complex", filters, "-map", "[mixed]", "-t", f"{duration:.9f}",
            "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(staged),
        ], runner, "FFmpeg music ducking")
        mixed_frames, mixed_rate, channels = _wav_info(staged)
        if abs(mixed_frames / mixed_rate - duration) > 1 / mixed_rate or channels != 2:
            raise RuntimeError("FFmpeg music ducking changed narration duration or channels")
        os.replace(staged, out)
    return out
