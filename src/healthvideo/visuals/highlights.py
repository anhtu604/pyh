"""Bounded in-memory paper excerpt crops from operator-supplied raster pages."""

from __future__ import annotations

import warnings
from io import BytesIO
from pathlib import Path

from PIL import Image

from healthvideo.domain.storyboard import EvidenceHighlight

CONTEXT = 0.05  # of the full source-page width/height on each side
MAX_CROP_AREA = 0.25  # technical minimization policy, not a rights determination
MAX_PAGE_PIXELS = 20_000_000


def crop_highlight(
    page_image: Path, highlight: EvidenceHighlight
) -> tuple[bytes, tuple[float, float, float, float, int, int]]:
    """Return PNG bytes of the excerpt only; never persist the input page."""
    if not page_image.is_file() or page_image.suffix.lower() not in {
        ".png",
        ".jpg",
        ".jpeg",
    }:
        raise ValueError("page image must be a local PNG or JPEG file")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(page_image) as page:
                if (
                    page.format not in {"PNG", "JPEG"}
                    or getattr(page, "n_frames", 1) != 1
                ):
                    raise ValueError("page image must be a single PNG or JPEG frame")
                w, h = page.size
                if w <= 0 or h <= 0 or w * h > MAX_PAGE_PIXELS:
                    raise ValueError("page image dimensions exceed limit")
                x0 = max(0, highlight.x - CONTEXT)
                y0 = max(0, highlight.y - CONTEXT)
                x1 = min(1, highlight.x + highlight.width + CONTEXT)
                y1 = min(1, highlight.y + highlight.height + CONTEXT)
                if (x1 - x0) * (y1 - y0) > MAX_CROP_AREA:
                    raise ValueError(
                        "excerpt crop would retain too much of source page"
                    )
                from math import ceil, floor

                box = (floor(x0 * w), floor(y0 * h), ceil(x1 * w), ceil(y1 * h))
                if box[2] <= box[0] or box[3] <= box[1]:
                    raise ValueError("excerpt crop must have positive dimensions")
                if (box[2] - box[0]) * (box[3] - box[1]) / (w * h) > MAX_CROP_AREA:
                    raise ValueError(
                        "excerpt crop would retain too much of source page"
                    )
                page.load()
                excerpt = page.crop(box).convert("RGB")
                output = BytesIO()
                excerpt.save(output, format="PNG", optimize=False)
                return output.getvalue(), (
                    box[0] / w,
                    box[1] / h,
                    (box[2] - box[0]) / w,
                    (box[3] - box[1]) / h,
                    excerpt.width,
                    excerpt.height,
                )
        except (
            OSError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise ValueError("invalid or oversized page image") from exc
