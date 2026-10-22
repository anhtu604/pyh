"""FLUX background and branded Remotion still, cached by recipe and verified bytes."""

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageOps

from healthvideo.domain.brand import LogoVariant, load_brand_profile
from healthvideo.domain.license_ledger import LicenseEntry, LicenseLedger
from healthvideo.domain.posts import CLAIM_REF, PostSet
from healthvideo.render.remotion import RemotionRunner, renderer_identity
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)
from healthvideo.visuals.brand import render_pyh_logo
from healthvideo.visuals.flux import (
    MODEL_ID,
    generate_illustration,
    validate_illustration_png,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BRAND_PROFILE_PATH = REPO_ROOT / "profiles/brand.vi.yaml"
BACKGROUND_PROMPT_SUFFIX = (
    "\nDecorative illustration only. No text, letters, numbers, labels, logos or watermarks."
    " Keep the left two thirds quiet for a headline; place the subject on the right."
)


def _run(argv: list[str]) -> int:
    from healthvideo.workflows.factory_deps import _run_render_argv

    return _run_render_argv(argv)


def render_thumbnail(revision_root: Path, *, runner: RemotionRunner = _run) -> Path:
    """Materialize a thumbnail without changing any medically reviewed artifacts."""
    posts = PostSet.model_validate(read_yaml(revision_root / "posts/posts.yaml"))
    if posts.thumbnail is None:
        raise ValueError("posts.yaml has no thumbnail recipe")
    spec = posts.thumbnail
    brand = load_brand_profile(BRAND_PROFILE_PATH)
    logo = render_pyh_logo(brand, LogoVariant.REVERSE)
    prompt = spec.background_prompt + BACKGROUND_PROMPT_SUFFIX
    key = canonical_json_hash({
        "thumbnail": spec.model_dump(), "brand": brand.model_dump(mode="json"),
        "renderer": renderer_identity(), "logo": logo.decode(), "model": MODEL_ID,
        "prompt": prompt, "size": [1280, 720], "recipe_version": 1,
    })
    directory = revision_root / "posts"
    output = directory / "thumbnail.png"
    receipt = directory / "thumbnail.json"
    background = directory / "thumbnail-background.png"
    ledger_path = directory / "license-ledger.yaml"
    if receipt.is_file() and output.is_file() and background.is_file() and ledger_path.is_file():
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
            validate_illustration_png(output, 1280, 720)
            if data == {
                "input_hash": key, "sha256": sha256_file(output),
                "background_sha256": sha256_file(background),
                "ledger_sha256": sha256_file(ledger_path),
            }:
                return output
        except (OSError, ValueError):
            pass
    directory.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".thumbnail-", dir=directory) as temporary:
        staging = Path(temporary)
        # FLUX dimensions are multiples of 16; crop 1280x736 to the YouTube canvas.
        generated = generate_illustration(prompt, out=staging / "flux.png", width=1280, height=736, seed=spec.seed)
        with Image.open(generated) as image:
            ImageOps.fit(image.convert("RGB"), (1280, 720)).save(staging / background.name)
        (staging / "logo.svg").write_bytes(logo)
        shutil.copytree(REPO_ROOT / "video/public/fonts", staging / "fonts")
        props = {
            "headline": CLAIM_REF.sub("", spec.headline).strip(),
            "background": background.name, "logo": "logo.svg",
            "colors": brand.colors.model_dump(),
        }
        props_path = staging / "props.json"
        props_path.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        staged_output = staging / output.name
        argv = ["pnpm", "--dir", str(REPO_ROOT / "video"), "exec", "remotion", "still",
                "src/index.ts", "Thumbnail", "--props", str(props_path.resolve()),
                "--output", str(staged_output.resolve()), "--public-dir", str(staging.resolve())]
        code = runner(argv)
        if code:
            raise RuntimeError(f"Remotion thumbnail failed with exit code {code}")
        validate_illustration_png(staged_output, 1280, 720)
        entry = LicenseEntry(
            path="posts/thumbnail-background.png", source="generated:flux2-klein-4b",
            creator=brand.assets.creator, license="Apache-2.0",
            rights_basis="Generated unlabeled illustration using Apache-2.0 FLUX.2 klein 4B weights",
            revision=revision_root.name, sha256=sha256_file(staging / background.name),
        )
        write_yaml_atomic(staging / ledger_path.name, LicenseLedger(entries=(entry,)).model_dump(mode="json"))
        for name in (background.name, output.name, ledger_path.name):
            (staging / name).replace(directory / name)
        (staging / receipt.name).write_text(json.dumps({
            "input_hash": key, "sha256": sha256_file(output),
            "background_sha256": sha256_file(background), "ledger_sha256": sha256_file(ledger_path),
        }), encoding="utf-8")
        (staging / receipt.name).replace(receipt)
    return output


def render_optional_thumbnail(revision_root: Path, *, runner: RemotionRunner) -> None:
    posts_path = revision_root / "posts/posts.yaml"
    if posts_path.is_file() and PostSet.model_validate(read_yaml(posts_path)).thumbnail is not None:
        from healthvideo.workflows.gate_review import check_revision_posts

        errors = check_revision_posts(revision_root, require_medical_approval=True)
        if errors:
            raise ValueError("Invalid thumbnail posts: " + "; ".join(errors))
        render_thumbnail(revision_root, runner=runner)
