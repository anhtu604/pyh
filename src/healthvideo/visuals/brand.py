"""Font-free deterministic SVG marks for the PHY identity."""

from healthvideo.domain.brand import BrandProfile, LogoVariant


def render_phy_logo(brand: BrandProfile, variant: LogoVariant) -> bytes:
    """Render the approved P-bubble, H-plus, and Y-check geometry."""
    if variant is LogoVariant.MONOGRAM:
        body = _mark(brand, compact=True, one_color=False)
        view_box = "0 0 320 320"
    elif variant is LogoVariant.ONE_COLOR:
        body = _mark(brand, compact=False, one_color=True)
        view_box = "0 0 760 260"
    else:
        body = _mark(brand, compact=False, one_color=False)
        view_box = "0 0 760 260"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" '
        'role="img" aria-label="PHY">\n'
        f"{body}"
        "</svg>\n"
    ).encode()


def _mark(brand: BrandProfile, *, compact: bool, one_color: bool) -> str:
    navy = brand.colors.navy
    teal = navy if one_color else brand.colors.teal
    yellow = navy if one_color else brand.colors.yellow
    transform = ' transform="translate(-16 30) scale(.46)"' if compact else ""
    return (
        f'<g id="phy-wordmark"{transform}>\n'
        f'  <path id="phy-p-bubble" fill="{navy}" fill-rule="evenodd" '
        'd="M50 35h145c70 0 110 38 110 98s-40 97-110 97h-55v-60h52c31 0 48-13 48-37s-17-38-48-38h-77v135H50V35zm65 75h76c15 0 23 8 23 23s-8 22-23 22h-76v-45z"/>\n'
        f'  <path id="phy-h-frame" fill="{teal}" d="M330 35h65v70h75V35h65v195h-65v-70h-75v70h-65V35z"/>\n'
        f'  <path id="phy-h-plus" fill="{navy}" d="M416 86h33v28h28v33h-28v28h-33v-28h-28v-33h28V86z"/>\n'
        f'  <path id="phy-y-stem" fill="{navy}" d="M555 35h70l38 57 38-57h70l-76 112v83h-65v-83L555 35z"/>\n'
        f'  <path id="phy-y-check" fill="none" stroke="{yellow}" stroke-linecap="round" '
        'stroke-linejoin="round" stroke-width="25" d="M642 72l26 25 61-66"/>\n'
        "</g>\n"
    )
