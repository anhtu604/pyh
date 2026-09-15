"""Finite deterministic whiteboard templates."""

from enum import StrEnum
from html import escape

from pydantic import BaseModel, ConfigDict, field_validator

from healthvideo.domain.brand import BrandProfile


class WhiteboardTemplate(StrEnum):
    CONNECTOR = "connector"
    COMPARISON = "comparison"
    THREE_STEP = "three_step"
    CALLOUT = "callout"


class WhiteboardPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    labels: tuple[str, ...] = ()

    @field_validator("labels")
    @classmethod
    def _visible_safe_labels(cls, labels: tuple[str, ...]) -> tuple[str, ...]:
        for label in labels:
            if not label.strip():
                raise ValueError("whiteboard labels must be nonblank")
            if any(ord(character) < 32 and character not in "\t\n\r" for character in label):
                raise ValueError("whiteboard labels cannot contain control characters")
        return labels


_LABEL_COUNTS = {
    WhiteboardTemplate.CONNECTOR: 0,
    WhiteboardTemplate.COMPARISON: 2,
    WhiteboardTemplate.THREE_STEP: 3,
    WhiteboardTemplate.CALLOUT: 1,
}


def render_whiteboard(
    brand: BrandProfile, template: WhiteboardTemplate, payload: WhiteboardPayload
) -> bytes:
    """Lay out only the values explicitly supplied by the operator."""
    expected = _LABEL_COUNTS[template]
    if len(payload.labels) != expected:
        raise ValueError(f"{template.value} requires exactly {expected} labels")
    colors = brand.colors
    labels = tuple(escape(label, quote=True) for label in payload.labels)
    shapes = _shapes(template, labels, colors.navy, colors.teal, colors.yellow)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1000" '
        f'role="img" aria-label="PYH whiteboard {template.value}">\n'
        f'<g id="whiteboard-{template.value}" fill="none" stroke="{colors.navy}" '
        'stroke-width="18" stroke-linecap="round" stroke-linejoin="round">\n'
        f'{shapes}</g>\n</svg>\n'
    ).encode()


def _label(value: str, x: int, y: int, color: str) -> str:
    return (
        f'<text x="{x}" y="{y}" fill="{color}" stroke="none" '
        'font-family="Arial, sans-serif" font-size="58" font-weight="700" '
        f'text-anchor="middle">{value}</text>\n'
    )


def _shapes(
    template: WhiteboardTemplate,
    labels: tuple[str, ...],
    navy: str,
    teal: str,
    yellow: str,
) -> str:
    if template is WhiteboardTemplate.CONNECTOR:
        return '<path d="M140 500H900m-85-70 85 70-85 70"/>\n'
    if template is WhiteboardTemplate.COMPARISON:
        return (
            f'<rect x="90" y="250" width="390" height="420" rx="48" fill="{teal}" fill-opacity=".12"/>\n'
            f'<rect x="600" y="250" width="390" height="420" rx="48" fill="{yellow}" fill-opacity=".18"/>\n'
            + _label(labels[0], 285, 480, navy)
            + _label(labels[1], 795, 480, navy)
        )
    if template is WhiteboardTemplate.THREE_STEP:
        return "".join(
            f'<circle cx="{x}" cy="450" r="120" fill="{teal}" fill-opacity=".12"/>\n'
            + _label(label, x, 470, navy)
            for x, label in zip((190, 540, 890), labels, strict=True)
        ) + '<path d="M310 450h110m240 0h110"/>\n'
    return (
        f'<path d="M170 220h740v500H610l-70 90-70-90H170z" fill="{yellow}" fill-opacity=".16"/>\n'
        + _label(labels[0], 540, 500, navy)
    )
