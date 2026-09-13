"""Deterministic, non-clinical PHY mascot SVG rig."""

from html import escape

from healthvideo.domain.brand import BrandProfile, MascotPose

_ARMS = {
    MascotPose.WELCOME: (
        '<path id="mascot-left-arm" d="M205 440Q105 410 92 286"/>\n'
        '<path id="mascot-right-arm" d="M435 440Q520 470 540 555"/>\n'
    ),
    MascotPose.EXPLAIN: (
        '<path id="mascot-left-arm" d="M205 440Q126 486 105 560"/>\n'
        '<path id="mascot-right-arm" d="M435 438Q560 360 674 250"/>\n'
    ),
    MascotPose.CAUTION: (
        '<path id="mascot-left-arm" d="M205 440Q112 390 105 280"/>\n'
        '<path id="mascot-right-arm" d="M435 440Q528 390 535 280"/>\n'
    ),
}


def render_mascot(brand: BrandProfile, pose: MascotPose) -> bytes:
    """Render one fixed reaction pose without accepting content fields."""
    colors = brand.colors
    arms = _ARMS[pose]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 900" role="img" '
        f'aria-label="PHY guide {pose.value}">\n'
        f'<g id="mascot-pose-{pose.value}" stroke="{colors.navy}" stroke-width="34" '
        'stroke-linecap="round" stroke-linejoin="round" fill="none">\n'
        f'{arms}'
        f'<path id="mascot-body" fill="{colors.navy}" d="M190 420Q320 360 450 420L490 800H150z"/>\n'
        f'<path id="mascot-outerwear-panel" fill="{colors.teal}" stroke="none" d="M190 430h70v370h-80z"/>\n'
        f'<path id="mascot-h-seam" stroke="{colors.teal}" d="M265 450v280m0-110h112m0-170v280"/>\n'
        f'<circle id="mascot-head" fill="{colors.off_white}" cx="320" cy="275" r="150"/>\n'
        f'<path id="mascot-short-hair" fill="{colors.navy}" d="M178 262Q180 90 320 92Q475 94 462 260Q420 178 347 162Q255 205 178 262z"/>\n'
        '<circle id="mascot-glass-left" cx="264" cy="276" r="54"/>\n'
        '<circle id="mascot-glass-right" cx="382" cy="270" r="49"/>\n'
        '<path id="mascot-glass-bridge" d="M318 270h17"/>\n'
        f'<path id="mascot-smile" stroke="{colors.charcoal}" stroke-width="18" d="M276 340Q320 380 366 338"/>\n'
        f'<path id="mascot-p-badge" fill="{colors.off_white}" stroke="none" d="M390 500h46q42 0 42 38t-42 38h-17v48h-29zm29 24v28h15q16 0 16-14t-16-14z" fill-rule="evenodd"/>\n'
        f'<path id="mascot-y-check" stroke="{colors.yellow}" stroke-width="18" d="M430 684l20 20 42-48"/>\n'
        '</g>\n</svg>\n'
    ).encode()


def render_mascot_annotation(
    brand: BrandProfile, pose: MascotPose, annotation: str
) -> bytes:
    """Bake operator-supplied semantic text into a distinct mascot asset."""
    if not annotation.strip() or len(annotation) > 240:
        raise ValueError("mascot annotation must be visible and at most 240 characters")
    if any(ord(character) < 32 and character not in "\t\n\r" for character in annotation):
        raise ValueError("mascot annotation cannot contain control characters")
    base = render_mascot(brand, pose).decode()
    bubble = (
        f'<g id="mascot-medical-annotation"><rect x="470" y="80" width="270" '
        f'height="220" rx="30" fill="{brand.colors.off_white}" stroke="{brand.colors.navy}" '
        f'stroke-width="12"/><text x="605" y="180" fill="{brand.colors.charcoal}" '
        'font-family="Arial, sans-serif" font-size="28" text-anchor="middle">'
        f'{escape(annotation, quote=True)}</text></g>\n'
    )
    return base.replace("</svg>\n", f"{bubble}</svg>\n").encode()
