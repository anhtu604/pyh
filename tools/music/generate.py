"""Run with cache/music-venv: instrumental ACE-Step 1.5 -> PCM16 stereo 48 kHz WAV."""

import argparse
import json
import math
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

# The model venv deliberately does not install the main application's dependencies.
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from healthvideo.audio.music import music_weights, shared_repo_root


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

        dit = AceStepHandler()
        message, ok = dit.initialize_service(
            project_root=str(shared_repo_root(REPO) / "cache/ace-step-src"),
            config_path="acestep-v15-turbo", device="cuda",
            offload_to_cpu=True, offload_dit_to_cpu=True,
        )
        if not ok:
            raise RuntimeError(message)
        lm = LLMHandler()
        message, ok = lm.initialize(
            checkpoint_dir=str(checkpoints), lm_model_path="acestep-5Hz-lm-1.7B",
            backend="pt", device="cuda", offload_to_cpu=True,
        )
        if not ok:
            raise RuntimeError(message)
        out.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".ace-step-", dir=out.parent) as temporary:
            result = generate_music(
                dit, lm,
                GenerationParams(
                    caption=f"{mood}, instrumental background music, no vocals, no singing",
                    lyrics="[Instrumental]", instrumental=True, duration=seconds, seed=seed,
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
            if len(samples) < target_frames:
                samples = np.pad(samples, ((0, target_frames - len(samples)), (0, 0)))
            normalized = Path(temporary) / "normalized.wav"
            sf.write(normalized, samples[:target_frames], 48000, subtype="PCM_16")
            os.replace(normalized, out)
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
    except (RuntimeError, ValueError, OSError, ImportError) as error:
        print(f"ACE-Step music generation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
