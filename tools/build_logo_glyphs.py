"""Print precomputed Be Vietnam Pro ExtraBold outlines for the PYH logo."""

import argparse
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont


class AbsolutePen(BasePen):
    """Expand contours into explicit absolute commands, including composites."""

    def __init__(self, glyphs):
        super().__init__(glyphs)
        self.commands = []

    def add(self, command, *points):
        values = (f"{value:.1f}".removesuffix(".0") for point in points for value in point)
        self.commands.append(command + " ".join(values))

    def _moveTo(self, point):
        self.add("M", point)

    def _lineTo(self, point):
        self.add("L", point)

    def _curveToOne(self, first, second, end):
        self.add("C", first, second, end)

    def _qCurveToOne(self, control, end):
        self.add("Q", control, end)

    def _closePath(self):
        self.commands.append("Z")


def glyph_run(font, text, x, baseline, size, tracking):
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    scale = size / font["head"].unitsPerEm
    pen = AbsolutePen(glyphs)
    for character in text:
        glyph = glyphs[cmap[ord(character)]]
        glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        x += glyph.width * scale + tracking
    return " ".join(pen.commands)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ttf", type=Path)
    args = parser.parse_args()
    with TTFont(args.ttf) as font:
        print("# Generated from Be Vietnam Pro ExtraBold (SIL OFL 1.1).")
        print("# Command: python tools/build_logo_glyphs.py .tmp/logo-lab/BVP-ExtraBold.ttf")
        print('"""Precomputed absolute logo outlines; no runtime font dependency."""')
        print()
        for name, run in (
            ("WORDMARK", glyph_run(font, "PYH", 220, 190, 190, -4)),
            ("TAGLINE", glyph_run(font, "PROTECT YOUR HEALTH", 224, 250, 34, 3)),
        ):
            print(f"{name} = (")
            for command in run.split(" M"):
                prefix = "" if command.startswith("M") else "M"
                print(f"    {prefix + command + ' '!r}")
            print(")")


if __name__ == "__main__":
    main()
