"""Deterministic QA checks for generated Vietnamese ``.srt`` subtitle files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from healthvideo.domain.script import Script
from healthvideo.qa.script import QAIssue
from healthvideo.storage.files import AgentEncodingError, validate_agent_text

_TIMESTAMP_RE = re.compile(
    r"^(\d{2,}):([0-5]\d):([0-5]\d),(\d{3})\s*-->\s*(\d{2,}):([0-5]\d):([0-5]\d),(\d{3})$"
)
_LEADING_QMARK_WORD_RE = re.compile(r"(?:^|\s)\?[A-Za-zÀ-ỹ]")
_MULTI_QMARK_RE = re.compile(r"\?{2,}")


@dataclass(frozen=True, slots=True)
class SrtCue:
    """Parsed cue from an ``.srt`` subtitle track."""

    index: int
    start_ms: int
    end_ms: int
    text: str


def _parse_ts_parts(hours: str, minutes: str, seconds: str, millis: str) -> int:
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


def parse_srt_timestamp_pair(line: str) -> tuple[int, int] | None:
    """Parse ``HH:MM:SS,mmm --> HH:MM:SS,mmm`` into millisecond bounds, or ``None`` if invalid."""
    match = _TIMESTAMP_RE.match(line.strip())
    if match is None:
        return None
    h1, m1, s1, ms1, h2, m2, s2, ms2 = match.groups()
    return _parse_ts_parts(h1, m1, s1, ms1), _parse_ts_parts(h2, m2, s2, ms2)


def _has_lossy_utf8_text(text: str) -> bool:
    if "\ufffd" in text:
        return True
    if _LEADING_QMARK_WORD_RE.search(text) or _MULTI_QMARK_RE.search(text):
        return True
    try:
        validate_agent_text(text, "subtitles.vi.srt")
    except AgentEncodingError:
        return True
    return False


def parse_srt(
    content: str,
    *,
    max_overlap_ms: int = 0,
    max_lines_per_cue: int = 2,
    max_chars_per_line: int = 42,
) -> tuple[list[SrtCue], list[QAIssue]]:
    """Parse SRT content and return ``(valid_cues, qa_issues)``."""
    cleaned = content.lstrip("\ufeff")
    issues: list[QAIssue] = []
    cues: list[SrtCue] = []
    blocks = [block for block in re.split(r"\r?\n\s*\r?\n", cleaned.strip()) if block.strip()]

    prev_start_ms: int | None = None
    prev_end_ms: int | None = None

    for expected_index, block in enumerate(blocks, start=1):
        raw_lines = block.splitlines()
        cue_label = f"cue-{expected_index}"
        if len(raw_lines) < 2:
            issues.append(
                QAIssue(
                    code="malformed_srt_block",
                    line_id=cue_label,
                    message="Khối phụ đề thiếu dòng chỉ số hoặc timestamp.",
                    severity="error",
                )
            )
            continue

        index_line = raw_lines[0].strip()
        try:
            cue_index = int(index_line)
        except ValueError:
            issues.append(
                QAIssue(
                    code="invalid_cue_index",
                    line_id=cue_label,
                    message=f"Chỉ số cue không hợp lệ: {index_line!r}",
                    severity="error",
                )
            )
            cue_index = expected_index
        else:
            if cue_index != expected_index:
                issues.append(
                    QAIssue(
                        code="invalid_cue_index",
                        line_id=f"cue-{cue_index}",
                        message=f"Chỉ số cue {cue_index} không tuần tự (kỳ vọng {expected_index}).",
                        severity="error",
                    )
                )

        cue_ref = f"cue-{cue_index}"
        ts_pair = parse_srt_timestamp_pair(raw_lines[1])
        if ts_pair is None:
            issues.append(
                QAIssue(
                    code="invalid_timestamp",
                    line_id=cue_ref,
                    message=f"Timestamp SRT không hợp lệ: {raw_lines[1].strip()!r}",
                    severity="error",
                )
            )
            continue

        start_ms, end_ms = ts_pair
        if end_ms <= start_ms:
            issues.append(
                QAIssue(
                    code="non_positive_duration",
                    line_id=cue_ref,
                    message=f"Thời lượng cue không dương ({start_ms}ms -> {end_ms}ms).",
                    severity="error",
                )
            )
        if prev_start_ms is not None and start_ms < prev_start_ms:
            issues.append(
                QAIssue(
                    code="non_monotonic_timestamp",
                    line_id=cue_ref,
                    message=f"Timestamp bắt đầu giảm ({start_ms}ms < {prev_start_ms}ms).",
                    severity="error",
                )
            )
        elif prev_end_ms is not None and start_ms < prev_end_ms - max_overlap_ms:
            issues.append(
                QAIssue(
                    code="overlapping_cue",
                    line_id=cue_ref,
                    message=(
                        f"Cue chồng lấp bất thường ({start_ms}ms < {prev_end_ms}ms"
                        f", ngưỡng cho phép {max_overlap_ms}ms)."
                    ),
                    severity="error",
                )
            )

        prev_start_ms = start_ms
        prev_end_ms = end_ms if prev_end_ms is None else max(prev_end_ms, end_ms)

        text_lines = [line.rstrip() for line in raw_lines[2:]]
        cue_text = "\n".join(text_lines).strip()
        if not cue_text:
            issues.append(
                QAIssue(
                    code="empty_cue_text",
                    line_id=cue_ref,
                    message="Nội dung cue phụ đề bị rỗng.",
                    severity="error",
                )
            )
            continue

        if _has_lossy_utf8_text(cue_text):
            issues.append(
                QAIssue(
                    code="lossy_utf8_srt",
                    line_id=cue_ref,
                    message="Phụ đề có dấu hiệu mất dấu tiếng Việt ('?' hoặc ký tự thay thế UTF-8).",
                    severity="error",
                )
            )

        nonblank_lines = [line for line in text_lines if line.strip()]
        if len(nonblank_lines) > max_lines_per_cue or any(
            len(line) > max_chars_per_line for line in nonblank_lines
        ):
            issues.append(
                QAIssue(
                    code="cue_layout_overflow",
                    line_id=cue_ref,
                    message=(
                        f"Cue vượt giới hạn hiển thị ({len(nonblank_lines)} dòng, "
                        f"tối đa {max_lines_per_cue} dòng × {max_chars_per_line} ký tự)."
                    ),
                    severity="warning",
                )
            )

        cues.append(SrtCue(index=cue_index, start_ms=start_ms, end_ms=end_ms, text=cue_text))

    return cues, issues


def review_srt(
    content: str,
    *,
    script: Script | None = None,
    require_nonempty: bool = True,
    max_overlap_ms: int = 0,
    max_lines_per_cue: int = 2,
    max_chars_per_line: int = 42,
) -> list[QAIssue]:
    """Deterministically audit SRT subtitle content for emptiness, timing, overlap, and clean UTF-8."""
    has_dialogue = (
        any(line.tts_text(expressive=False).strip() for line in script.lines)
        if script is not None
        else require_nonempty
    )
    if not content.strip():
        if has_dialogue:
            return [
                QAIssue(
                    code="empty_srt",
                    line_id="",
                    message="File phụ đề .srt rỗng dù kịch bản có lời thoại.",
                    severity="error",
                )
            ]
        return []

    cues, issues = parse_srt(
        content,
        max_overlap_ms=max_overlap_ms,
        max_lines_per_cue=max_lines_per_cue,
        max_chars_per_line=max_chars_per_line,
    )
    if has_dialogue and not cues and not any(issue.code == "empty_srt" for issue in issues):
        issues.append(
            QAIssue(
                code="srt_missing_dialogue",
                line_id="",
                message="Không có cue phụ đề hợp lệ nào khớp lời thoại kịch bản.",
                severity="error",
            )
        )
    return issues


def review_srt_file(
    path: Path,
    *,
    script: Script | None = None,
    require_nonempty: bool = True,
    max_overlap_ms: int = 0,
    max_lines_per_cue: int = 2,
    max_chars_per_line: int = 42,
) -> list[QAIssue]:
    """Read an ``.srt`` file strictly as UTF-8 and run ``review_srt``."""
    if not path.is_file():
        if require_nonempty:
            return [
                QAIssue(
                    code="missing_srt",
                    line_id="",
                    message=f"Thiếu file phụ đề: {path.name}",
                    severity="error",
                )
            ]
        return []
    try:
        content = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return [
            QAIssue(
                code="invalid_utf8_srt",
                line_id="",
                message=f"{path.name} không phải UTF-8 hợp lệ.",
                severity="error",
            )
        ]
    return review_srt(
        content,
        script=script,
        require_nonempty=require_nonempty,
        max_overlap_ms=max_overlap_ms,
        max_lines_per_cue=max_lines_per_cue,
        max_chars_per_line=max_chars_per_line,
    )
