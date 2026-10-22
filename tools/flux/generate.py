"""Run local, unlabeled FLUX.2 klein 4B inference inside cache/flux-venv."""

import argparse
import contextlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from healthvideo.visuals.flux import flux_weights, validate_flux_weights


def generate(prompt: str, width: int, height: int, seed: int, out: Path) -> dict:
    if not prompt.strip() or min(width, height) <= 0 or not 0 <= seed < 2**63:
        raise ValueError("A nonempty prompt, positive dimensions and seed in [0, 2**63) are required")
    weights = flux_weights(REPO_ROOT)
    validate_flux_weights(weights)
    # Import models only in this dedicated subprocess; it exits before VieNeu/ACE-Step.
    import torch
    from diffusers import Flux2KleinPipeline
    from PIL import Image

    if not torch.cuda.is_available():
        raise RuntimeError("FLUX requires a CUDA GPU; install CUDA torch in flux-venv")
    pipe = Flux2KleinPipeline.from_pretrained(weights, dtype=torch.bfloat16, local_files_only=True)
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()
    multiple = pipe.vae_scale_factor * 2
    native_width = max(multiple, round(width / multiple) * multiple)
    native_height = max(multiple, round(height / multiple) * multiple)
    image = pipe(
        prompt=prompt + "\nUnlabeled illustration only. No text, letters, numbers, anatomical labels or captions.",
        width=native_width, height=native_height, num_inference_steps=4,
        guidance_scale=1.0, generator=torch.Generator(device="cpu").manual_seed(seed),
    ).images[0]
    out.parent.mkdir(parents=True, exist_ok=True)
    image.resize((width, height), Image.Resampling.LANCZOS).save(out, format="PNG")
    return {"width": width, "height": height, "seed": seed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = generate(args.prompt, args.width, args.height, args.seed, args.out)
        print(json.dumps(result))
    except (RuntimeError, ValueError, OSError, ImportError) as error:
        print(f"FLUX illustration generation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
