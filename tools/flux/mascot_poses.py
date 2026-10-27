"""Generate candidate mascot poses from a single reference anchor image using FLUX.2 klein."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from healthvideo.storage.files import read_yaml
from healthvideo.visuals.flux import MODEL_ID, generate_illustration

DEFAULT_ANCHOR = REPO_ROOT / "assets/brand/mascot/explain.png"
DEFAULT_POSES_FILE = REPO_ROOT / "assets/brand/mascot/poses.yaml"
DEFAULT_OUT_DIR = REPO_ROOT / "cache/mascot-poses"

KEEP_CLAUSE = (
    "Keep exactly the same character as the reference: face, glasses, hair, coat colors, badge, "
    "dark-navy pants, and cream sneakers."
)
BACKGROUND_CLAUSE = (
    "Full-body front view from head to feet centered on a plain solid white background matching the reference, "
    "clean 2D flat vector illustration with bold dark-navy outline, flat matte colors, no 3D render, no text."
)


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def build_pose_prompt(change: str) -> str:
    clause = change.strip()
    if not clause.endswith("."):
        clause += "."
    return f"{clause} {KEEP_CLAUSE} {BACKGROUND_CLAUSE}"


def load_pose_specs(poses_file: Path = DEFAULT_POSES_FILE) -> list[dict]:
    data = read_yaml(poses_file)
    poses = data.get("poses") if isinstance(data, dict) else None
    if not isinstance(poses, list) or not poses:
        raise ValueError(f"Expected non-empty 'poses' list in {poses_file}")
    specs: list[dict] = []
    seen: set[str] = set()
    for item in poses:
        pose_id = str(item.get("id", "")).strip()
        change = str(item.get("change", "")).strip()
        seed = item.get("seed")
        if not pose_id or not change or type(seed) is not int or seed < 0 or pose_id in seen:
            raise ValueError(f"Invalid or duplicate pose entry in {poses_file}: {item}")
        seen.add(pose_id)
        specs.append({
            "id": pose_id,
            "label": str(item.get("label", pose_id)).strip(),
            "change": change,
            "seed": seed,
        })
    return specs


def _paste_rgba_on_white(image: Image.Image) -> Image.Image:
    if "A" in image.getbands():
        rgba = image.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(bg, rgba).convert("RGB")
    return image.convert("RGB")


def render_contact_sheet(
    anchor: Path, manifest: dict, sheet_path: Path, *, cols: int = 4, thumb_size: tuple[int, int] = (384, 512),
) -> Path:
    tiles: list[tuple[str, Path]] = [("anchor (explain)", anchor)]
    for pose_id, entry in manifest.get("poses", {}).items():
        pose_file = Path(entry["path"])
        if not pose_file.is_absolute():
            pose_file = sheet_path.parent / pose_file.name
        if pose_file.is_file():
            tag = f"{pose_id} [STALE]" if entry.get("stale") else pose_id
            tiles.append((tag, pose_file))
    tw, th = thumb_size
    pad, header = 20, 44
    rows = (len(tiles) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + header + pad) + pad), (247, 244, 236))
    draw = ImageDraw.Draw(canvas)
    for idx, (title, img_path) in enumerate(tiles):
        r, c = divmod(idx, cols)
        x = pad + c * (tw + pad)
        y = pad + r * (th + header + pad)
        draw.rectangle([x, y, x + tw, y + th + header], fill=(255, 255, 255), outline=(18, 48, 74), width=2)
        draw.text((x + 12, y + 14), title, fill=(18, 48, 74))
        with Image.open(img_path) as raw:
            rgb = _paste_rgba_on_white(raw)
            rgb.thumbnail((tw - 16, th - 16), Image.Resampling.LANCZOS)
            ox = x + (tw - rgb.width) // 2
            oy = y + header + (th - rgb.height) // 2
            canvas.paste(rgb, (ox, oy))
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(sheet_path, format="PNG")
    return sheet_path


def generate_mascot_poses(
    *,
    anchor: Path = DEFAULT_ANCHOR,
    poses_file: Path = DEFAULT_POSES_FILE,
    out_dir: Path = DEFAULT_OUT_DIR,
    only: str | None = None,
    width: int = 768,
    height: int = 1024,
    generate=generate_illustration,
) -> dict:
    if not anchor.is_file():
        raise ValueError(f"Anchor image does not exist: {anchor}")
    specs = load_pose_specs(poses_file)
    spec_by_id = {spec["id"]: spec for spec in specs}
    if only is not None and only not in spec_by_id:
        raise ValueError(f"Unknown pose id '{only}'. Available: {', '.join(spec_by_id)}")

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    existing_poses: dict[str, dict] = {}
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded.get("poses"), dict):
                existing_poses = loaded["poses"]
        except (OSError, json.JSONDecodeError):
            existing_poses = {}

    anchor_hash = _sha256(anchor)
    poses_manifest: dict[str, dict] = {}

    for spec in specs:
        pose_id = spec["id"]
        out_png = out_dir / f"{pose_id}.png"
        prev = existing_poses.get(pose_id)
        should_generate = (
            only == pose_id
            if only is not None
            else (prev is None or not out_png.is_file())
        )
        if should_generate:
            prompt = build_pose_prompt(spec["change"])
            generate(
                prompt,
                out=out_png,
                width=width,
                height=height,
                seed=spec["seed"],
                refs=(anchor,),
            )
            poses_manifest[pose_id] = {
                "id": pose_id,
                "label": spec["label"],
                "anchor_sha256": anchor_hash,
                "prompt": prompt,
                "seed": spec["seed"],
                "model": MODEL_ID,
                "path": out_png.as_posix(),
                "stale": False,
            }
        elif prev is not None:
            updated = dict(prev)
            updated["stale"] = updated.get("anchor_sha256") != anchor_hash
            poses_manifest[pose_id] = updated

    manifest = {
        "anchor": anchor.as_posix(),
        "anchor_sha256": anchor_hash,
        "model": MODEL_ID,
        "poses": poses_manifest,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    render_contact_sheet(anchor, manifest, out_dir / "sheet.png")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor", type=Path, default=DEFAULT_ANCHOR)
    parser.add_argument("--poses-file", type=Path, default=DEFAULT_POSES_FILE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--only", type=str, default=None, help="Regenerate only a single pose ID")
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=1024)
    args = parser.parse_args()
    try:
        manifest = generate_mascot_poses(
            anchor=args.anchor,
            poses_file=args.poses_file,
            out_dir=args.out_dir,
            only=args.only,
            width=args.width,
            height=args.height,
        )
        print(json.dumps({
            "out_dir": args.out_dir.as_posix(),
            "sheet": (args.out_dir / "sheet.png").as_posix(),
            "poses": len(manifest["poses"]),
        }))
    except (RuntimeError, ValueError, OSError) as error:
        print(f"Mascot pose generation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
