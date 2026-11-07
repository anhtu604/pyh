"""Rule-based Vietnamese voice and style linter for explain-first scripts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from healthvideo.domain.script import Script, ScriptLine

StyleSeverity = Literal["block", "warn"]

_META_VISUAL_PHRASES: tuple[str, ...] = (
    "trên màn hình",
    "màn hình không",
    "ô vuông",
    "ô dịch",
    "ô tế bào",
    "ô phóng đại",
    "ô yên lặng",
    "hai ô đối chiếu",
    "hình mô phỏng",
    "mô phỏng giúp",
    "các chấm",
    "chấm nhỏ",
    "chấm vàng",
    "đếm chấm",
    "ký hiệu cho",
    "chỉ là ký hiệu",
    "các ký hiệu",
    "tượng trưng cho",
    "màu xanh là",
    "hình đang cho thấy",
    "cảnh đang yên",
    "cảnh tiếp theo",
    "cảnh tua",
    "hình tua nhanh",
    "hình này không mô tả",
    "trên hình không",
)

_PRESENTER_CLICHE_PHRASES: tuple[str, ...] = (
    "video này bắt đầu",
    "ta sẽ xem",
    "chúng ta sẽ xem",
    "hãy cùng",
    "cùng khám phá",
    "hành trình",
    "điều cần giữ lại",
    "câu ngắn để nhớ",
)

_CAVEAT_LIMIT_PHRASES: tuple[str, ...] = (
    "thí nghiệm tế bào và động vật",
    "thí nghiệm ngoài cơ thể",
)

_CAVEAT_SENTENCE_MARKERS: tuple[str, ...] = (
    "giới hạn",
    "thí nghiệm",
    "ngoài cơ thể",
    "động vật",
    "không phải",
    "chưa phải",
    "không thay",
    "không dùng",
    "không suy",
    "không đo",
    "không cho biết",
    "không dự báo",
    "không khẳng định",
    "chỉ là",
    "chỉ giúp",
    "phạm vi",
    "cần phân biệt",
    "cần được phân biệt",
    "bằng chứng",
    "nghiên cứu",
    "trong ống nghiệm",
)

_MEDICAL_DISCLAIMER_MARKERS: tuple[str, ...] = (
    "không thay được buổi khám",
    "không thay thế buổi khám",
    "không dùng thay cho chẩn đoán",
    "không thay cho chẩn đoán",
    "tự chọn hay đổi thuốc",
    "tự chọn và đổi thuốc",
    "tự ý dùng hay đổi thuốc",
)

# Signs of AI writing (Wikipedia: Signs of AI writing), adapted to Vietnamese narration.
# See prompts/ai_writing_signs.vi.md; rule names start with ai_ so prompts can cite them.
_AI_CHATBOT_PHRASES: tuple[str, ...] = (
    "câu hỏi hay",
    "tất nhiên rồi",
    "chắc chắn rồi",
    "hy vọng giúp ích",
    "hy vọng thông tin",
    "tóm lại",
    "tổng kết lại",
    "kết luận lại",
    "tính đến thời điểm",
    "mô hình ngôn ngữ",
)

_AI_PUFFERY_PHRASES: tuple[str, ...] = (
    "vai trò then chốt",
    "vai trò quan trọng",
    "vai trò cốt lõi",
    "đóng vai trò là",
    "đóng vai trò như",
    "được xem là",
    "là minh chứng",
    "là lời nhắc",
    "tầm quan trọng",
    "đặt nền móng",
    "dấu ấn",
    "bước ngoặt",
    "điều này quan trọng vì",
    "qua đó cho thấy",
    "từ đó nhấn mạnh",
    "làm nổi bật",
    "góp phần",
    "chuyên gia cho rằng",
    "nhiều nghiên cứu cho thấy",
    "giới khoa học",
    "theo một số nguồn",
    "còn nhiều thách thức",
    "hứa hẹn",
    "cần lưu ý rằng",
    "điều quan trọng là",
    "thông tin còn hạn chế",
    "ghi nhận rộng rãi",
    "tài liệu cho thấy",
    "theo tài liệu",
    "bộ tài liệu",
    "không nên nhầm với",
    "không đồng nghĩa với",
)

_AI_VOCAB_WORDS: tuple[str, ...] = (
    "khám phá",
    "bức tranh toàn cảnh",
    "lăng kính",
    "chìa khóa",
    "bí mật",
    "đáng kinh ngạc",
    "vô cùng",
    "không thể phủ nhận",
    "thực sự",
    "quả thực",
    "sâu sắc",
    "toàn diện",
    "đa chiều",
)
_AI_VOCAB_ALLOWANCE = 3  # one stray word is fine; a cluster is the sign
_AI_MARKUP_RE = re.compile(r"[*#`\[\]]|[\U0001F300-\U0001FAFF☀-➿]")

_SENTENCE_SPLIT_RE = re.compile(r"[.?!…]+")
_NOT_X_BUT_Y_RE = re.compile(
    r"(?<!\w)không phải\b[^.?!;\n]{1,140}?\bmà(?:\s+là)?(?!\w)"
    r"|(?<!\w)không chỉ\b[^.?!;\n]{1,140}?\bmà còn(?!\w)"
    r"|(?<!\w)chứ không phải(?!\w)",
    re.IGNORECASE,
)
_TRIAD_RE = re.compile(
    r"\b[^\W\d_][\w\s]{1,40},\s*[^\W\d_][\w\s]{1,40}\s+và\s+[^\W\d_][\w\s]{1,40}",
    re.IGNORECASE,
)
_METAPHOR_DISCLAIMER_RE = re.compile(
    r"(?<!\w)ẩn dụ(?!\w)|(?<!\w)ví dụ\b[^.?!;\n]{0,80}?\bgiúp hình dung(?!\w)|(?<!\w)giúp hình dung(?!\w)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class StyleIssue:
    """Single style violation or warning detected on a script line."""

    line_id: str
    rule: str
    excerpt: str
    severity: StyleSeverity

    def to_dict(self) -> dict[str, str]:
        """Serialize issue to a plain JSON-compatible dictionary."""
        return {
            "line_id": self.line_id,
            "rule": self.rule,
            "excerpt": self.excerpt,
            "severity": self.severity,
        }

    def model_dump(self, mode: str = "json") -> dict[str, str]:
        """Compatibility helper matching Pydantic dump conventions."""
        _ = mode
        return self.to_dict()


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.IGNORECASE)


_META_VISUAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (phrase, _phrase_pattern(phrase)) for phrase in _META_VISUAL_PHRASES
)
_PRESENTER_CLICHE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (phrase, _phrase_pattern(phrase)) for phrase in _PRESENTER_CLICHE_PHRASES
)
_CAVEAT_LIMIT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (phrase, _phrase_pattern(phrase)) for phrase in _CAVEAT_LIMIT_PHRASES
)
# (rule, severity, patterns) checked on every non-exempt line.
_AI_PHRASE_RULES: tuple[tuple[str, StyleSeverity, tuple[re.Pattern[str], ...]], ...] = (
    ("ai_chatbot", "block", tuple(_phrase_pattern(p) for p in _AI_CHATBOT_PHRASES)),
    ("ai_puffery", "warn", tuple(_phrase_pattern(p) for p in _AI_PUFFERY_PHRASES)),
)
_AI_VOCAB_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    _phrase_pattern(word) for word in _AI_VOCAB_WORDS
)


def _is_exempt_line(line: ScriptLine) -> bool:
    if line.purpose == "outro":
        return True
    if line.claim_id is None:
        folded = line.text.casefold()
        if line.arc_beat == 7 or any(
            marker in folded for marker in _MEDICAL_DISCLAIMER_MARKERS
        ):
            return True
    return False


def _normalize_sentence(sentence: str) -> list[str]:
    cleaned = re.sub(r"[^\w\s]", " ", sentence.casefold())
    return [token for token in cleaned.split() if token]


def lint_script_style(script: Script) -> list[StyleIssue]:
    """Check Vietnamese narration style rules and return block/warn issues."""
    issues: list[StyleIssue] = []

    sentence_occurrences: dict[str, list[tuple[str, str]]] = {}
    caveat_phrase_lines: list[tuple[str, str]] = []
    not_x_but_y_matches: list[tuple[str, str]] = []
    triad_matches: list[tuple[str, str]] = []
    metaphor_matches: list[tuple[str, str]] = []
    vocab_matches: list[tuple[str, str]] = []

    for line in script.lines:
        if _is_exempt_line(line):
            continue
        text = line.text

        for _, pattern in _META_VISUAL_PATTERNS:
            match = pattern.search(text)
            if match is not None:
                issues.append(
                    StyleIssue(
                        line_id=line.id,
                        rule="meta_visual",
                        excerpt=match.group(0),
                        severity="block",
                    )
                )

        for _, pattern in _PRESENTER_CLICHE_PATTERNS:
            match = pattern.search(text)
            if match is not None:
                issues.append(
                    StyleIssue(
                        line_id=line.id,
                        rule="presenter_cliche",
                        excerpt=match.group(0),
                        severity="block",
                    )
                )

        for rule, severity, patterns in _AI_PHRASE_RULES:
            for pattern in patterns:
                match = pattern.search(text)
                if match is not None:
                    issues.append(StyleIssue(line.id, rule, match.group(0), severity))
        markup = _AI_MARKUP_RE.search(text)
        if markup is not None:
            issues.append(StyleIssue(line.id, "ai_markup", markup.group(0), "block"))
        if "—" in text:
            issues.append(StyleIssue(line.id, "ai_em_dash", "—", "warn"))
        for pattern in _AI_VOCAB_PATTERNS:
            vocab_matches.extend((line.id, m.group(0)) for m in pattern.finditer(text))

        matched_caveat_phrase: str | None = None
        for _, pattern in _CAVEAT_LIMIT_PATTERNS:
            match = pattern.search(text)
            if match is not None:
                matched_caveat_phrase = match.group(0)
                break
        if matched_caveat_phrase is not None:
            caveat_phrase_lines.append((line.id, matched_caveat_phrase))

        for raw_sentence in _SENTENCE_SPLIT_RE.split(text):
            sentence = raw_sentence.strip()
            if not sentence:
                continue
            words = sentence.split()
            if len(words) > 40:
                issues.append(
                    StyleIssue(
                        line_id=line.id,
                        rule="long_sentence",
                        excerpt=sentence,
                        severity="warn",
                    )
                )
            norm_tokens = _normalize_sentence(sentence)
            if len(norm_tokens) >= 4:
                norm_key = " ".join(norm_tokens)
                sentence_occurrences.setdefault(norm_key, []).append(
                    (line.id, sentence)
                )

        for match in _NOT_X_BUT_Y_RE.finditer(text):
            not_x_but_y_matches.append((line.id, match.group(0).strip()))

        for match in _TRIAD_RE.finditer(text):
            triad_matches.append((line.id, match.group(0).strip()))

        for match in _METAPHOR_DISCLAIMER_RE.finditer(text):
            metaphor_matches.append((line.id, match.group(0).strip()))

    flagged_caveat_lines: set[tuple[str, str]] = set()
    for norm_key, occurrences in sentence_occurrences.items():
        if len(occurrences) < 2:
            continue
        distinct_lines = {line_id for line_id, _ in occurrences}
        has_caveat_marker = any(
            marker in norm_key for marker in _CAVEAT_SENTENCE_MARKERS
        )
        if len(distinct_lines) >= 2 or has_caveat_marker:
            for line_id, excerpt in occurrences[1:]:
                key = (line_id, excerpt)
                if key not in flagged_caveat_lines:
                    flagged_caveat_lines.add(key)
                    issues.append(
                        StyleIssue(
                            line_id=line_id,
                            rule="repeated_caveat",
                            excerpt=excerpt,
                            severity="block",
                        )
                    )

    if len(caveat_phrase_lines) > 2:
        for line_id, phrase_excerpt in caveat_phrase_lines[2:]:
            issues.append(
                StyleIssue(
                    line_id=line_id,
                    rule="repeated_caveat",
                    excerpt=phrase_excerpt,
                    severity="block",
                )
            )

    if len(not_x_but_y_matches) > 2:
        for line_id, excerpt in not_x_but_y_matches[2:]:
            issues.append(
                StyleIssue(
                    line_id=line_id,
                    rule="not_x_but_y",
                    excerpt=excerpt,
                    severity="warn",
                )
            )

    if len(triad_matches) > 3:
        for line_id, excerpt in triad_matches[3:]:
            issues.append(
                StyleIssue(
                    line_id=line_id,
                    rule="triad",
                    excerpt=excerpt,
                    severity="warn",
                )
            )

    for line_id, excerpt in vocab_matches[_AI_VOCAB_ALLOWANCE:]:
        issues.append(StyleIssue(line_id, "ai_vocab", excerpt, "warn"))

    if len(metaphor_matches) > 1:
        for line_id, excerpt in metaphor_matches[1:]:
            issues.append(
                StyleIssue(
                    line_id=line_id,
                    rule="metaphor_disclaimer",
                    excerpt=excerpt,
                    severity="warn",
                )
            )

    return issues
