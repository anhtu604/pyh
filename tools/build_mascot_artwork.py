"""Rebuild deterministic sticker PNGs from the checked-in, unoutlined sources.

Run from any directory: python tools/build_mascot_artwork.py.
The profile owns the colours; sources are never modified by this tool.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]
POSES = ("welcome", "explain", "caution")


def _disk_dilation(alpha: Image.Image, radius: int) -> Image.Image:
    """Dilate the alpha silhouette with a circular kernel at 3x resolution.

    Drawing disks only on the boundary is equivalent to the union of disks
    on every foreground pixel, with the original interior retained. Supersampling
    preserves round joins and gives a narrow, antialiased edge, without blur/glow.
    """
    scale = 3
    solid = alpha.point(lambda value: 255 if value >= 128 else 0)
    boundary = ImageChops.subtract(solid, solid.filter(ImageFilter.MinFilter(3)))
    enlarged = solid.resize((alpha.width * scale, alpha.height * scale), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(enlarged)
    r = radius * scale
    for index, value in enumerate(boundary.get_flattened_data()):
        if value:
            x = (index % alpha.width) * scale + 1
            y = (index // alpha.width) * scale + 1
            draw.ellipse((x - r, y - r, x + r, y + r), fill=255)
    return enlarged.resize(alpha.size, Image.Resampling.LANCZOS)


def outline_figure(
    source: Image.Image, night: str, off_white: str, *,
    inner_width: int | None = None, outer_width: int | None = None,
) -> Image.Image:
    """Return a tightly cropped RGBA figure with two alpha-derived outline rings."""
    figure = source.convert("RGBA")
    bbox = figure.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("Mascot source must have a non-empty alpha channel")
    figure = figure.crop(bbox)
    inner = inner_width if inner_width is not None else max(1, round(figure.height * 0.016))
    outer = outer_width if outer_width is not None else max(1, round(inner / 2))
    if inner < 1 or outer < 1:
        raise ValueError("Outline widths must be positive")
    figure = ImageOps.expand(figure, border=inner + outer + 8)
    alpha = figure.getchannel("A")
    result = Image.new("RGBA", figure.size, off_white)
    result.putalpha(_disk_dilation(alpha, inner + outer))
    dark = Image.new("RGBA", figure.size, night)
    dark.putalpha(_disk_dilation(alpha, inner))
    result = Image.alpha_composite(Image.alpha_composite(result, dark), figure)
    return ImageOps.expand(result.crop(result.getbbox()), border=6)


def main() -> None:
    profile = yaml.safe_load((ROOT / "profiles/brand.vi.yaml").read_text(encoding="utf-8"))
    colours = profile["colors"]
    directory = ROOT / "assets/brand/mascot"
    figures = {}
    for pose in POSES:
        with Image.open(directory / "source" / f"{pose}.png") as source:
            figures[pose] = outline_figure(source, colours["night"], colours["off_white"])
    size = (max(768, *(im.width for im in figures.values())),
            max(768, *(im.height for im in figures.values())))
    for pose, figure in figures.items():
        canvas = Image.new("RGBA", size)
        canvas.alpha_composite(figure, ((size[0] - figure.width) // 2, size[1] - figure.height))
        output = directory / f"{pose}.png"
        canvas.save(output, optimize=False, compress_level=9)
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        print(f"{pose}: sha256={digest} canvas={size[0]}x{size[1]}")


if __name__ == "__main__":
    main()
