"""Run with cache/music-venv: instrumental ACE-Step 1.5 -> PCM16 stereo 48 kHz WAV."""

import argparse
import gc
import json
import math
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

# The model venv deliberately does not install the main application's dependencies.
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from healthvideo.audio.music import music_weights, shared_repo_root


def _release_memory(torch_module: Any = None) -> None:
    """Release Python objects and CUDA allocator cache between heavy model steps."""
    gc.collect()
    if torch_module is not None:
        try:
            if torch_module.cuda.is_available():
                torch_module.cuda.empty_cache()
        except (AttributeError, RuntimeError):
            pass


def _shape_seamless_loop(samples, target_frames: int, np, *, rate: int = 48000):
    """Trim quiet ACE-Step intro/tail and apply a circular raised-cosine loop crossfade."""
    if target_frames <= 0 or len(samples) <= 0:
        return samples[:target_frames]
    win = max(1, rate // 10)
    full_windows = len(samples) // win
    start_frame = 0
    end_frame = len(samples)
    if full_windows >= 6:
        trimmed = samples[: full_windows * win].reshape(full_windows, win, samples.shape[1])
        rms = np.sqrt(np.mean(trimmed ** 2, axis=(1, 2)))
        nonzero = rms[rms > 1e-6]
        if len(nonzero) > 0:
            med = float(np.median(nonzero))
            thresh = 0.15 * med
            max_intro_windows = min(full_windows - 1, round(2.0 * rate / win))
            start_win = 0
            while start_win < max_intro_windows and rms[start_win] < thresh:
                start_win += 1
            min_windows = max(1, min(full_windows - start_win, target_frames // (2 * win)))
            end_win = full_windows
            while end_win > start_win + min_windows and rms[end_win - 1] < thresh:
                end_win -= 1
            cand_start = start_win * win
            cand_end = min(len(samples), end_win * win)
            if cand_end - cand_start >= min(len(samples), max(rate, target_frames // 2)):
                start_frame, end_frame = cand_start, cand_end

    body = np.asarray(samples[start_frame:end_frame], dtype=np.float32)
    fade_frames = min(2 * rate, target_frames // 4, len(body) // 4)
    if fade_frames >= 1 and len(body) >= target_frames + fade_frames:
        pre_head = body[:fade_frames]
        core = body[fade_frames : fade_frames + target_frames].copy()
        theta = np.linspace(0.0, math.pi / 2.0, fade_frames, endpoint=False, dtype=np.float32)[:, None]
        core[-fade_frames:] = core[-fade_frames:] * (np.cos(theta) ** 2) + pre_head * (np.sin(theta) ** 2)
        return np.clip(core, -1.0, 1.0)

    if len(body) < target_frames:
        if len(body) < 4:
            pad_width = target_frames - len(body)
            return np.pad(body, ((0, pad_width), (0, 0)))
        step_fade = min(fade_frames, len(body) // 4)
        chunks = [body]
        total = len(body)
        theta = np.linspace(0.0, math.pi / 2.0, step_fade, endpoint=False, dtype=np.float32)[:, None]
        while total < target_frames + step_fade:
            prev = chunks[-1]
            if step_fade >= 1:
                prev = prev.copy()
                prev[-step_fade:] = prev[-step_fade:] * (np.cos(theta) ** 2) + body[:step_fade] * (np.sin(theta) ** 2)
                chunks[-1] = prev
                nxt = body[step_fade:]
            else:
                nxt = body
            chunks.append(nxt)
            total += len(nxt)
        body = np.concatenate(chunks, axis=0)
        fade_frames = step_fade

    core = body[:target_frames].copy()
    if fade_frames >= 1:
        avail = min(fade_frames, len(body) - target_frames)
        if avail >= 1:
            pre_head = body[:avail]
            core = body[avail : avail + target_frames].copy()
            theta = np.linspace(0.0, math.pi / 2.0, avail, endpoint=False, dtype=np.float32)[:, None]
            core[-avail:] = core[-avail:] * (np.cos(theta) ** 2) + pre_head * (np.sin(theta) ** 2)
        else:
            theta = np.linspace(0.0, math.pi / 2.0, fade_frames, endpoint=False, dtype=np.float32)[:, None]
            core[-fade_frames:] = (
                core[-fade_frames:] * (np.cos(theta) ** 2) + core[:fade_frames] * (np.sin(theta) ** 2)
            )
    return np.clip(core, -1.0, 1.0)


def generate(mood: str, seconds: float, seed: int, out: Path) -> dict:
    if not mood.strip() or not math.isfinite(seconds) or not 0 < seconds <= 480:
        raise ValueError("ACE-Step needs a mood and duration between 0 and 480 seconds")
    checkpoints = music_weights(REPO)
    os.environ["ACESTEP_PROJECT_ROOT"] = str(shared_repo_root(REPO) / "cache/ace-step-src")
    os.environ["ACESTEP_CHECKPOINTS_DIR"] = str(checkpoints)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    # Upstream sometimes prints progress; stdout is reserved for the JSON contract.
    with redirect_stdout(sys.stderr):
        import numpy as np
        import soundfile as sf
        from acestep.handler import AceStepHandler
        from acestep.inference import GenerationConfig, GenerationParams, generate_music
        from acestep.llm_inference import LLMHandler
        from scipy.signal import resample_poly

        try:
            import torch as torch_module
        except ImportError:
            torch_module = None

        dit = None
        lm = None
        _release_memory(torch_module)
        try:
            dit = AceStepHandler()
            message, ok = dit.initialize_service(
                project_root=str(shared_repo_root(REPO) / "cache/ace-step-src"),
                config_path="acestep-v15-turbo", device="cuda",
                offload_to_cpu=True, offload_dit_to_cpu=True,
            )
            if not ok:
                raise RuntimeError(message)
            _release_memory(torch_module)
            lm = LLMHandler()
            message, ok = lm.initialize(
                checkpoint_dir=str(checkpoints), lm_model_path="acestep-5Hz-lm-1.7B",
                backend="pt", device="cuda", offload_to_cpu=True,
            )
            if not ok:
                raise RuntimeError(message)
            out.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=".ace-step-", dir=out.parent) as temporary:
                raw_seconds = min(480.0, seconds + 8.0) if seconds <= 472.0 else seconds
                caption = (
                    f"{mood}, warm ambient felt piano and soft acoustic pad, "
                    "steady calm documentary underscore for medical voiceover, "
                    "even gentle dynamics, no drums, no harsh percussion, "
                    "no sudden drops, no fade out, instrumental background music, "
                    "no vocals, no singing"
                )
                result = generate_music(
                    dit, lm,
                    GenerationParams(
                        caption=caption,
                        lyrics="[Instrumental]", instrumental=True, duration=raw_seconds, seed=seed,
                    ),
                    GenerationConfig(batch_size=1, use_random_seed=False, seeds=[seed], audio_format="wav"),
                    save_dir=temporary,
                )
                if not result.success or not result.audios:
                    raise RuntimeError(result.error or "ACE-Step returned no audio")
                samples, rate = sf.read(result.audios[0]["path"], always_2d=True, dtype="float32")
                if samples.shape[1] == 1:
                    samples = np.repeat(samples, 2, axis=1)
                if samples.shape[1] != 2 or not np.isfinite(samples).all() or not len(samples):
                    raise RuntimeError("ACE-Step returned invalid stereo audio")
                if rate != 48000:
                    divisor = math.gcd(rate, 48000)
                    samples = resample_poly(samples, 48000 // divisor, rate // divisor, axis=0)
                target_frames = round(seconds * 48000)
                shaped = _shape_seamless_loop(samples, target_frames, np, rate=48000)
                if len(shaped) < target_frames:
                    shaped = np.pad(shaped, ((0, target_frames - len(shaped)), (0, 0)))
                normalized = Path(temporary) / "normalized.wav"
                sf.write(normalized, shaped[:target_frames], 48000, subtype="PCM_16")
                os.replace(normalized, out)
        finally:
            dit = None
            lm = None
            _release_memory(torch_module)
    return {"seconds": target_frames / 48000, "sample_rate": 48000}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mood", required=True)
    parser.add_argument("--seconds", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(generate(args.mood, args.seconds, args.seed, args.out)))
    except (RuntimeError, ValueError, OSError, ImportError, MemoryError) as error:
        detail = str(error)
        lower = detail.lower()
        if isinstance(error, MemoryError) or "1455" in lower or "paging file" in lower:
            print(
                f"ACE-Step music generation failed (transient memory/pagefile pressure): {detail}",
                file=sys.stderr,
            )
        else:
            print(f"ACE-Step music generation failed: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
