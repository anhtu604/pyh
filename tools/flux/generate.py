"""Run local, unlabeled FLUX.2 klein 4B inference inside cache/flux-venv."""

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from healthvideo.visuals.flux import flux_weights, validate_flux_weights

MAX_REFS = 2


def _load_ref_image(path: Path, image_module, max_side: int = 512):
    with image_module.open(path) as img:
        if "A" in img.getbands():
            rgba = img.convert("RGBA")
            bg = image_module.new("RGBA", rgba.size, (255, 255, 255, 255))
            rgb = image_module.alpha_composite(bg, rgba).convert("RGB")
        else:
            rgb = img.convert("RGB")
        if max(rgb.size) > max_side:
            rgb.thumbnail((max_side, max_side), image_module.Resampling.LANCZOS)
        return rgb


def generate(
    prompt: str, width: int, height: int, seed: int, out: Path,
    refs: tuple[Path, ...] = (),
) -> dict:
    if not prompt.strip() or min(width, height) <= 0 or not 0 <= seed < 2**63:
        raise ValueError("A nonempty prompt, positive dimensions and seed in [0, 2**63) are required")
    refs = tuple(Path(r) for r in refs)
    if len(refs) > MAX_REFS or any(not r.is_file() for r in refs):
        raise ValueError(f"At most {MAX_REFS} existing reference PNGs are allowed")
    weights = flux_weights(REPO_ROOT)
    validate_flux_weights(weights)
    # Import models only in this dedicated subprocess; it exits before VieNeu/ACE-Step.
    import gc

    import torch
    from diffusers import Flux2KleinPipeline
    from PIL import Image
    from transformers import Qwen2TokenizerFast, Qwen3ForCausalLM

    if not torch.cuda.is_available():
        raise RuntimeError("FLUX requires a CUDA GPU; install CUDA torch in flux-venv")
    ref_images = [_load_ref_image(r, Image) for r in refs] if refs else None
    full_prompt = prompt + "\nUnlabeled illustration only. No text, letters, numbers, anatomical labels or captions."
    tokenizer = Qwen2TokenizerFast.from_pretrained(weights / "tokenizer", local_files_only=True)
    text_encoder = Qwen3ForCausalLM.from_pretrained(
        weights / "text_encoder", dtype=torch.bfloat16, low_cpu_mem_usage=True, local_files_only=True,
    ).to("cuda")
    with torch.inference_mode():
        prompt_embeds = Flux2KleinPipeline._get_qwen3_prompt_embeds(
            text_encoder=text_encoder, tokenizer=tokenizer, prompt=full_prompt,
            dtype=torch.bfloat16, device=torch.device("cpu"),
        ).detach().clone()
    del text_encoder, tokenizer
    gc.collect()
    torch.cuda.empty_cache()

    pipe = Flux2KleinPipeline.from_pretrained(
        weights, text_encoder=None, tokenizer=None, dtype=torch.bfloat16,
        low_cpu_mem_usage=True, local_files_only=True,
    ).to("cuda")
    pipe.vae.enable_tiling()
    multiple = pipe.vae_scale_factor * 2
    native_width = max(multiple, round(width / multiple) * multiple)
    native_height = max(multiple, round(height / multiple) * multiple)
    call_kwargs = {
        "prompt": None,
        "prompt_embeds": prompt_embeds.to("cuda"),
        "width": native_width, "height": native_height, "num_inference_steps": 4,
        "guidance_scale": 1.0, "generator": torch.Generator(device="cpu").manual_seed(seed),
    }
    if ref_images:
        call_kwargs["image"] = ref_images
    image = pipe(**call_kwargs).images[0]
    out.parent.mkdir(parents=True, exist_ok=True)
    image.resize((width, height), Image.Resampling.LANCZOS).save(out, format="PNG")
    del pipe, image, prompt_embeds
    gc.collect()
    torch.cuda.empty_cache()
    return {"width": width, "height": height, "seed": seed, "refs": [str(r) for r in refs]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ref", action="append", type=Path, default=[])
    args = parser.parse_args()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = generate(args.prompt, args.width, args.height, args.seed, args.out, refs=tuple(args.ref))
        print(json.dumps(result), flush=True)
        os._exit(0)
    except (RuntimeError, ValueError, OSError, ImportError) as error:
        print(f"FLUX illustration generation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
