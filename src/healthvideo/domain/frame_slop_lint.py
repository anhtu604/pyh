"""Zero-LLM rule-based linter for rendered HTML/SVG medical animation frames."""

from __future__ import annotations

import html
import re
from collections.abc import Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal

from healthvideo.domain.medanim_library import MedAnimEntry

LintSeverity = Literal["block", "warn"]

_FONT_SIZE_RE = re.compile(r"(?:^|;)\s*font-size\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*(?:px)?\b", re.IGNORECASE)
_FONT_ITALIC_RE = re.compile(r"(?:^|;)\s*font-style\s*:\s*italic\b", re.IGNORECASE)
_TEXT_DEC_UNDERLINE_RE = re.compile(
    r"(?:^|;)\s*text-decoration(?:-line)?\s*:[^;]*\bunderline\b", re.IGNORECASE
)
_BORDER_BOTTOM_RE = re.compile(r"(?:^|;)\s*border-bottom(?:-width)?\s*:", re.IGNORECASE)
_HIDDEN_STYLE_RE = re.compile(
    r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\.0+)?\s*(?:;|$))",
    re.IGNORECASE,
)

_DRAFT_NOTE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("draft_note_missing_art", re.compile(r"(?i)\*\s*chưa có hình\b|\bchưa có hình\b")),
    ("draft_note_overview_star", re.compile(r"(?i)\bminh họa khái quát\s*\*|\bnội mô minh họa khái quát\b")),
    ("draft_note_acceptance", re.compile(r"(?i)\bcần bổ sung trước nghiệm thu\b")),
    (
        "draft_note_marker",
        re.compile(r"(?i)(?<![A-Za-z0-9_])(?:TODO|FIXME|TBD|WIP|PLACEHOLDER|LOREM\s+IPSUM|DRAFT\s+ONLY|INTERNAL\s+NOTE)(?![A-Za-z0-9_])"),
    ),
    ("draft_note_recolored", re.compile(r"(?i)\brecolou?red\b")),
    (
        "draft_note_asterisk",
        re.compile(r"(?:^|\s)\*[A-Za-zÀ-ỹ][^*\n]{2,}|[A-Za-zÀ-ỹ][^*\n]{2,}\*(?:\s|[.,;:!?]|$)"),
    ),
)

_SCALE_BAR_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:µm|μm|um|nm|pm)\b", re.IGNORECASE)
_PLACEHOLDER_STAT_RE = re.compile(r"(?:^|\s)(?:XX|\?\?|00)\s*%", re.IGNORECASE)
_STANDALONE_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_.,:/-])(\d+(?:[.,]\d+)?)(?:\s*%)?(?![A-Za-z0-9_:/-]|[.,]\d)"
)
_TOKEN_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")

_SKIP_TEXT_TAGS: frozenset[str] = frozenset({"script", "style", "defs"})
_CAPTION_OR_MINIMAP_ATTRS: frozenset[str] = frozenset(
    {"data-style-captions", "data-caption-line", "data-captions", "data-word", "data-mini-map", "data-mini-map-step"}
)


@dataclass(frozen=True)
class FrameSlopIssue:
    """One deterministic slop violation found in a rendered HTML/SVG frame."""

    rule: str
    severity: LintSeverity
    excerpt: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "excerpt": self.excerpt,
            "detail": self.detail,
        }


@dataclass
class _NodeState:
    tag: str
    attrs: dict[str, str]
    font_size_px: float | None
    is_italic: bool
    in_hidden: bool
    in_skip_tag: bool
    in_caption_scope: bool
    in_label_scope: bool
    is_title_scope: bool
    text_parts: list[str]


class _FrameDOMScanner(HTMLParser):
    """Lightweight HTML/SVG scanner collecting visible text segments and style attributes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[_NodeState] = []
        self.issues: list[FrameSlopIssue] = []
        self.visible_segments: list[tuple[str, _NodeState | None]] = []
        self.detected_format: Literal["landscape", "portrait"] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        attr_map = {k.lower(): (v if v is not None else "") for k, v in attrs}
        parent = self.stack[-1] if self.stack else None

        if attr_map.get("data-format") in {"landscape", "portrait"}:
            self.detected_format = attr_map["data-format"]  # type: ignore[assignment]

        style_text = attr_map.get("style", "")
        font_size = parent.font_size_px if parent else None
        font_match = _FONT_SIZE_RE.search(style_text)
        if font_match:
            font_size = float(font_match.group(1))
        elif "font-size" in attr_map:
            raw_fs = attr_map["font-size"].strip().removesuffix("px").strip()
            try:
                font_size = float(raw_fs)
            except ValueError:
                pass

        is_italic = (parent.is_italic if parent else False) or bool(_FONT_ITALIC_RE.search(style_text))
        if attr_map.get("font-style", "").strip().lower() == "italic":
            is_italic = True

        in_hidden = (parent.in_hidden if parent else False) or bool(_HIDDEN_STYLE_RE.search(style_text))
        if attr_map.get("aria-hidden", "").strip().lower() == "true" and font_size is None and tag_l == "img":
            in_hidden = True

        in_skip = (parent.in_skip_tag if parent else False) or (tag_l in _SKIP_TEXT_TAGS)
        in_caption = (parent.in_caption_scope if parent else False) or any(
            k in attr_map for k in _CAPTION_OR_MINIMAP_ATTRS
        )
        in_label = (parent.in_label_scope if parent else False) or ("data-medanim-label" in attr_map)
        is_title = (parent.is_title_scope if parent else False) or (
            tag_l == "h1" or "data-medanim-title" in attr_map
        )

        state = _NodeState(
            tag=tag_l,
            attrs=attr_map,
            font_size_px=font_size,
            is_italic=is_italic,
            in_hidden=in_hidden,
            in_skip_tag=in_skip,
            in_caption_scope=in_caption,
            in_label_scope=in_label,
            is_title_scope=is_title,
            text_parts=[],
        )
        self.stack.append(state)

        # Check underline styles immediately on element open.
        if not in_hidden and not in_skip:
            has_u_tag = tag_l == "u"
            has_css_underline = bool(_TEXT_DEC_UNDERLINE_RE.search(style_text))
            has_attr_underline = "underline" in attr_map.get("text-decoration", "").lower()
            has_word_border = ("data-word" in attr_map) and bool(_BORDER_BOTTOM_RE.search(style_text))
            if (
                has_u_tag
                or has_css_underline
                or has_attr_underline
                or (in_caption and has_word_border)
            ):
                self.issues.append(
                    FrameSlopIssue(
                        rule="style_a_underline",
                        severity="block",
                        excerpt=f"<{tag_l}>",
                        detail="Vi phạm Style A: cấm gạch chân từng chữ hoặc text-decoration: underline trên khung hình.",
                    )
                )

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        while self.stack:
            node = self.stack.pop()
            if not node.in_skip_tag and not node.in_hidden and node.text_parts:
                text = " ".join("".join(node.text_parts).split())
                if text:
                    self.visible_segments.append((text, node))
            if node.tag == tag_l:
                break

    def handle_data(self, data: str) -> None:
        if not data or not data.strip():
            return
        if not self.stack:
            self.visible_segments.append((" ".join(data.split()), None))
            return
        top = self.stack[-1]
        if not top.in_skip_tag and not top.in_hidden:
            top.text_parts.append(html.unescape(data))

    def finish(self) -> None:
        while self.stack:
            node = self.stack.pop()
            if not node.in_skip_tag and not node.in_hidden and node.text_parts:
                text = " ".join("".join(node.text_parts).split())
                if text:
                    self.visible_segments.append((text, node))


def _normalize_number(token: str) -> str:
    return token.strip().replace(",", ".")


def allowed_numbers_from_medanim(entry: MedAnimEntry) -> set[str]:
    """Extract grounded numeric tokens from a MedAnimEntry's sources, steps, and assets."""
    chunks: list[str] = [entry.title, entry.summary]
    for src in entry.sources:
        chunks.extend(x for x in (src.pmid, src.pmcid, src.doi, src.citation, src.url, src.scope) if x)
    for step in entry.steps:
        chunks.extend([step.id, step.narration, step.claim])
        for q in step.quotes:
            chunks.extend(x for x in (q.quote, q.locator, q.scope) if x)
    for asset in entry.assets:
        chunks.extend(x for x in (asset.author, asset.license, asset.source_page, asset.original_url, asset.attribution) if x)

    allowed: set[str] = set()
    for chunk in chunks:
        for num in _TOKEN_NUMBER_RE.findall(chunk):
            allowed.add(_normalize_number(num))
    return allowed


def lint_rendered_frame(
    markup: str,
    *,
    frame_format: Literal["landscape", "portrait"] | None = None,
    min_font_px: float = 18.0,
    min_label_font_px: float | None = None,
    min_title_font_px: float = 72.0,
    allowed_numbers: Iterable[str | int | float] | None = None,
) -> list[FrameSlopIssue]:
    """Lint rendered HTML/SVG frame markup without LLM calls.

    Detects:
    1. Internal draft notes (`*Chưa có hình`, `TODO`, `recoloured`, `minh họa khái quát*`, ...)
    2. Style A caption/word underlines (`text-decoration: underline`, `<u>`, per-word underline)
    3. Undersized typography below Style A thresholds
    4. Stray/ungrounded numbers (microscopy scale bars like `50 µm`, `XX%`, or numbers outside `allowed_numbers`)
    """
    if not isinstance(markup, str):
        raise TypeError("markup must be a string")
    if not markup.strip():
        return []

    scanner = _FrameDOMScanner()
    scanner.feed(markup)
    scanner.close()
    scanner.finish()

    effective_format = frame_format or scanner.detected_format or "landscape"
    label_floor = (
        min_label_font_px
        if min_label_font_px is not None
        else (52.0 if effective_format == "portrait" else 44.0)
    )

    allowed_set: set[str] | None = None
    if allowed_numbers is not None:
        allowed_set = set()
        for item in allowed_numbers:
            text = str(item)
            for num in _TOKEN_NUMBER_RE.findall(text):
                allowed_set.add(_normalize_number(num))
            cleaned = _normalize_number(text)
            if cleaned:
                allowed_set.add(cleaned)

    issues: list[FrameSlopIssue] = list(scanner.issues)
    seen_keys: set[tuple[str, str]] = {(i.rule, i.excerpt) for i in issues}

    def _add(issue: FrameSlopIssue) -> None:
        key = (issue.rule, issue.excerpt)
        if key not in seen_keys:
            seen_keys.add(key)
            issues.append(issue)

    for text, node in scanner.visible_segments:
        # 1. Internal draft / placeholder notes
        for rule_code, pattern in _DRAFT_NOTE_PATTERNS:
            match = pattern.search(text)
            if match is not None:
                _add(
                    FrameSlopIssue(
                        rule="internal_draft_note",
                        severity="block",
                        excerpt=match.group(0).strip(),
                        detail=f"Phát hiện ghi chú nháp/tạm nội bộ ({rule_code}) trên khung hình.",
                    )
                )

        # 3. Font size thresholds
        if node is not None and node.font_size_px is not None:
            fs = node.font_size_px
            if fs < min_font_px:
                _add(
                    FrameSlopIssue(
                        rule="small_font",
                        severity="block",
                        excerpt=f"{fs:g}px: {text[:40]}",
                        detail=f"Cỡ chữ {fs:g}px nhỏ hơn ngưỡng tối thiểu {min_font_px:g}px.",
                    )
                )
            elif node.is_title_scope and fs < min_title_font_px:
                _add(
                    FrameSlopIssue(
                        rule="small_font",
                        severity="block",
                        excerpt=f"{fs:g}px: {text[:40]}",
                        detail=f"Tiêu đề {fs:g}px nhỏ hơn chuẩn Style A ({min_title_font_px:g}px).",
                    )
                )
            elif node.in_label_scope and not node.is_italic and fs < label_floor:
                _add(
                    FrameSlopIssue(
                        rule="small_font",
                        severity="block",
                        excerpt=f"{fs:g}px: {text[:40]}",
                        detail=f"Nhãn chính {fs:g}px nhỏ hơn chuẩn Style A {effective_format} ({label_floor:g}px).",
                    )
                )

        # 4. Stray numbers (scale bars, placeholders, or numbers absent from allowed_numbers)
        scale_match = _SCALE_BAR_RE.search(text)
        if scale_match is not None:
            norm_val = _normalize_number(_TOKEN_NUMBER_RE.findall(scale_match.group(0))[0])
            if allowed_set is None or norm_val not in allowed_set:
                _add(
                    FrameSlopIssue(
                        rule="stray_number",
                        severity="block",
                        excerpt=scale_match.group(0),
                        detail="Phát hiện thước đo/đơn vị hiển vi lạc từ hình gốc trên khung hình.",
                    )
                )

        ph_match = _PLACEHOLDER_STAT_RE.search(text)
        if ph_match is not None:
            _add(
                FrameSlopIssue(
                    rule="stray_number",
                    severity="block",
                    excerpt=ph_match.group(0).strip(),
                    detail="Phát hiện số liệu giữ chỗ chưa điền trên khung hình.",
                )
            )

        if allowed_set is not None:
            for num_match in _STANDALONE_NUMBER_RE.finditer(text):
                raw_num = num_match.group(1)
                norm_num = _normalize_number(raw_num)
                if norm_num not in allowed_set:
                    _add(
                        FrameSlopIssue(
                            rule="stray_number",
                            severity="block",
                            excerpt=num_match.group(0).strip(),
                            detail=f"Số liệu {num_match.group(0).strip()!r} không có trong danh sách số liệu đã kiểm chứng.",
                        )
                    )

    return issues
