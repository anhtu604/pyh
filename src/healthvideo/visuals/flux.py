"""Local FLUX.2 klein 4B illustrations, isolated from the production Python environment."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from healthvideo.audio.music import shared_repo_root

FLUX_PYTHON_ENV = "HEALTHVIDEO_FLUX_PYTHON"
MAX_REFS = 2
MODEL_ID = "black-forest-labs/FLUX.2-klein-4B"
REPO_ROOT = Path(__file__).resolve().parents[3]


def generate_candidates(
    prompt: str, *, out_dir: Path, width: int, height: int, seed: int,
    generate=None,
) -> tuple[Path, ...]:
    """Generate three independently seeded, cached PNGs, sequentially on the GPU."""
    generate = generate or generate_illustration
    return tuple(generate(
        prompt, out=out_dir / f"candidate-{index + 1}.png", width=width,
        height=height, seed=(seed + index) % 2**63,
    ) for index in range(3))


def flux_python(repo: Path = REPO_ROOT) -> Path:
    return Path(os.environ.get(
        FLUX_PYTHON_ENV, str(shared_repo_root(repo) / "cache/flux-venv/Scripts/python.exe")
    ))


def flux_weights(repo: Path = REPO_ROOT) -> Path:
    return shared_repo_root(repo) / "cache/models/flux2-klein-4b"


def validate_flux_weights(weights: Path) -> None:
    """Reject other FLUX variants, even when renamed to the expected folder name.

    The VAE is shared with FLUX.2-dev; its original model path is not a
    reliable variant identifier. Check the distilled pipeline and transformer.
    """
    try:
        index = json.loads((weights / "model_index.json").read_text(encoding="utf-8"))
        transformer = json.loads((weights / "transformer/config.json").read_text(encoding="utf-8"))
        encoder = json.loads((weights / "text_encoder/config.json").read_text(encoding="utf-8"))
        if (
            "9b" in weights.name.casefold() or "dev" in weights.name.casefold()
            or index.get("_class_name") != "Flux2KleinPipeline"
            or index.get("is_distilled") is not True
            or any(transformer.get(key) != value for key, value in {
                "num_attention_heads": 24, "num_layers": 5,
                "num_single_layers": 20, "joint_attention_dim": 7680,
            }.items())
            or encoder.get("hidden_size") != 2560
        ):
            raise ValueError("FLUX weights must be distilled klein 4B (Apache-2.0), not 9B/dev or base")
        for relative in ("tokenizer/tokenizer.json", "vae/config.json", "scheduler/scheduler_config.json"):
            if not (weights / relative).is_file():
                raise ValueError(f"Missing FLUX component: {relative}")
        for component in ("transformer", "text_encoder", "vae"):
            files = list((weights / component).glob("*.safetensors"))
            if not files or any(path.stat().st_size == 0 for path in files):
                raise ValueError(f"Missing FLUX weights: {component}")
            for shard_index in (weights / component).glob("*.safetensors.index.json"):
                shards = json.loads(shard_index.read_text(encoding="utf-8"))["weight_map"].values()
                if any(not (weights / component / shard).is_file() for shard in shards):
                    raise ValueError(f"Missing FLUX weight shard: {component}")
    except (OSError, KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError(f"Missing or invalid local FLUX klein 4B weights: {error}") from error


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def illustration_recipe_hash(
    prompt: str, width: int, height: int, seed: int, refs: tuple[Path, ...] = (),
) -> str:
    ref_paths = tuple(Path(ref) for ref in refs)
    if len(ref_paths) > MAX_REFS or any(not ref.is_file() for ref in ref_paths):
        raise ValueError(f"FLUX supports at most {MAX_REFS} existing reference PNGs")
    payload: list[object] = [prompt, width, height, seed, MODEL_ID]
    if ref_paths:
        payload.append([_sha256(ref) for ref in ref_paths])
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def validate_illustration_png(path: Path, width: int, height: int) -> None:
    with Image.open(path) as image:
        if image.format != "PNG" or image.size != (width, height):
            raise ValueError("FLUX illustration must be a PNG with the requested dimensions")
        image.verify()
    with Image.open(path) as image:
        image.load()


def generate_illustration(
    prompt: str, *, out: Path, width: int, height: int, seed: int,
    refs: tuple[Path, ...] = (), runner=subprocess.run, cache_dir: Path | None = None,
) -> Path:
    """Cache verified PNG bytes by the exact prompt, dimensions, seed, refs and model ID."""
    if (not prompt.strip() or any(type(value) is not int or value <= 0 for value in (width, height))
            or type(seed) is not int or not 0 <= seed < 2**63):
        raise ValueError("Illustration needs a nonempty prompt, positive integer dimensions and a seed in [0, 2**63)")
    ref_paths = tuple(Path(ref) for ref in refs)
    key = illustration_recipe_hash(prompt, width, height, seed, refs=ref_paths)
    cache = cache_dir if cache_dir is not None else shared_repo_root() / "cache/flux"
    cache.mkdir(parents=True, exist_ok=True)
    cached, metadata = cache / f"{key}.png", cache / f"{key}.json"
    valid = False
    if cached.is_file() and metadata.is_file():
        try:
            validate_illustration_png(cached, width, height)
            valid = json.loads(metadata.read_text(encoding="utf-8"))["sha256"] == _sha256(cached)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    if not valid:
        with TemporaryDirectory(prefix=".flux-", dir=cache) as temporary:
            generated = Path(temporary) / "illustration.png"
            argv = [
                str(flux_python()), "-X", "utf8", str(REPO_ROOT / "tools/flux/generate.py"),
                "--prompt", prompt, "--width", str(width), "--height", str(height),
                "--seed", str(seed), "--out", str(generated),
            ]
            for ref in ref_paths:
                argv.extend(["--ref", str(ref)])
            try:
                result = runner(argv, shell=False, check=False, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
            except OSError as error:
                raise RuntimeError(f"FLUX illustration generation could not start: {error}") from error
            if result.returncode:
                detail = (result.stderr or result.stdout or "no diagnostic output").strip()
                raise RuntimeError(f"FLUX illustration generation failed (exit {result.returncode}): {detail[-4000:]}")
            try:
                validate_illustration_png(generated, width, height)
            except (OSError, ValueError) as error:
                raise RuntimeError(f"FLUX illustration output missing, invalid or wrong dimensions: {error}") from error
            staged_metadata = Path(temporary) / "illustration.json"
            staged_metadata.write_text(json.dumps({"sha256": _sha256(generated), "model_id": MODEL_ID}), encoding="utf-8")
            os.replace(generated, cached)
            os.replace(staged_metadata, metadata)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.resolve() != cached.resolve():
        with TemporaryDirectory(prefix=".flux-copy-", dir=out.parent) as temporary:
            staged = Path(temporary) / "illustration.png"
            shutil.copyfile(cached, staged)
            os.replace(staged, out)
    return out
