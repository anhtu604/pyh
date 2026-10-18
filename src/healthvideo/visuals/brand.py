"""Font-free deterministic SVG marks for the PYH identity."""

from healthvideo.domain.brand import BrandProfile, LogoVariant
from healthvideo.visuals._logo_glyphs import TAGLINE, WORDMARK


def render_pyh_logo(brand: BrandProfile, variant: LogoVariant) -> bytes:
    """Render the approved bubble symbol and precomputed type outlines."""
    c = brand.colors
    avatar = variant is LogoVariant.MONOGRAM
    mono = variant is LogoVariant.ONE_COLOR
    x, y, s = (80, 72, 160) if avatar else (40, 50, 150)
    r = s * .28
    bubble = (
        f'M{x+r} {y}H{x+s-r}Q{x+s} {y} {x+s} {y+r}'
        f'V{y+s-r}Q{x+s} {y+s} {x+s-r} {y+s}'
        f'H{x+s*.42}L{x+s*.12} {y+s*1.2}L{x+s*.2} {y+s}'
        f'H{x+r}Q{x} {y+s} {x} {y+s-r}V{y+r}Q{x} {y} {x+r} {y}Z'
    )
    body = ''
    if avatar:
        body += f'<rect x="40" y="40" width="240" height="240" rx="53" fill="{c.navy}"/>\n'
    if mono:
        # Filled outline of the round-capped check; even-odd makes it transparent.
        hole = (
            'M73.8 135.1L99.3 159.1Q106.5 165.9 113.9 158.4L159.9 104.4'
            'Q166.3 97 158.9 90.6Q151.5 84.2 145.1 91.6L105.3 137.8'
            'L87.2 120.9Q80.1 114.2 73.4 121.3Q66.7 128.4 73.8 135.1Z'
        )
        body += f'<path id="pyh-bubble" fill="{c.navy}" fill-rule="evenodd" d="{bubble} {hole}"/>\n'
    else:
        body += f'<path id="pyh-bubble" fill="{c.teal}" d="{bubble}"/>\n'
        body += (
            f'<path id="pyh-check" fill="none" stroke="{c.yellow}" stroke-width="{s*.13:.1f}" '
            f'stroke-linecap="round" stroke-linejoin="round" d="M{x+s*.27} {y+s*.52}'
            f'L{x+s*.44} {y+s*.68}L{x+s*.75} {y+s*.32}"/>\n'
        )
    if not avatar:
        ink = c.off_white if variant is LogoVariant.REVERSE else c.navy
        sub = ink if mono or variant is LogoVariant.REVERSE else c.charcoal
        body += f'<path id="pyh-wordmark" fill="{ink}" d="{WORDMARK}"/>\n'
        body += f'<path id="pyh-tagline" fill="{sub}" d="{TAGLINE}"/>\n'
    view_box = '0 0 320 320' if avatar else '0 0 760 300'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" '
            f'role="img" aria-label="PYH">\n{body}</svg>\n').encode()
