import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.explainer import Explainer
from healthvideo.domain.project_v2 import ProjectManifestV2
from healthvideo.domain.script import Script
from healthvideo.storage.explainer import read_explainer
from healthvideo.storage.files import read_yaml


class QAIssue(BaseModel):
    code: str
    line_id: str
    message: str
    severity: Literal["error", "warning"] = "error"


_NUM = r"\d+(?:[.,]\d+)*"
_NUM_EXPR = rf"{_NUM}(?:\s*(?:[-–—/]|đến|tới)\s*{_NUM})?"

# Medical dose, lab concentration, blood-pressure, and pill-count units (BLOCK when unlinked).
# Longest / compound units come first so `mg/dL`, `mmol/L`, or `U/L` match as one span.
# Bare `g` is intentionally omitted to avoid false-blocking Vietnamese clock shorthand (`8g sáng`);
# Vietnamese TTS scripts spell out `gam`, `miligam`, `microgam`, `mililit`.
_DOSE_UNITS = (
    r"mg/dL|mg/L|mg/kg|mg/ngày|mcg/kg|mcg/ngày|"
    r"[µμ]g/dL|[µμ]g/L|[µμ]g/kg|"
    r"g/dL|g/L|mmol/L|[µμ]mol/L|mEq/L|"
    r"mIU/L|mIU/mL|IU/L|IU/mL|IU/ngày|U/L|"
    r"mL/kg|ml/kg|mmHg|"
    r"miligam|microgam|mililit|gam|"
    r"mg|mcg|[µμ]g|mL|ml|IU|UI|"
    r"đơn\s+vị|"
    r"viên(?!\s+(?:sỏi|đá|gạch|kẹo))"
)

_DOSE_RE = re.compile(
    rf"(?<!\w){_NUM_EXPR}\s*(?:{_DOSE_UNITS})(?![^\W\d_])",
    re.IGNORECASE,
)

# Non-statistical natural expressions masked before checking `number_without_claim`:
# - Spelled-out words (`một`, `hai bước`, `mỗi ngày`) contain no Arabic digits and are never matched.
# - Citation brackets (`[1]`, `[1, 2]`), clock times (`22:00`, `7h30`, `8 giờ sáng`),
#   hyphenated medical names (`omega-3`, `COVID-19`), ordinals/classifications (`thứ 2`, `týp 2`, `bước 1`),
#   and natural structural counts (`3 bước`, `2 cách`, `1 lượt like`) are masked to prevent false positives.
_IGNORED_NUMBER_RE = re.compile(
    r"\[\d+(?:\s*,\s*\d+)*\]"
    r"|(?<!\w)\d{1,2}:\d{2}(?!\w)"
    r"|(?<!\w)\d{1,2}\s*(?:h\d{0,2}|giờ(?:\s+(?:sáng|trưa|chiều|tối|đêm))?)(?![^\W\d_])"
    r"|\b(?:omega|covid|type|týp|tuýp)\s*[-–]?\s*\d+(?![^\W\d_])"
    r"|\b(?:thứ|số|bước|phần|mục|chương|độ|giai\s+đoạn|loại)\s+\d+(?![^\W\d_])"
    r"|(?<!\w)\d+(?:\s*(?:[-–—]|đến|tới)\s*\d+)?\s+"
    r"(?:bước|điều|điểm|cách|ý|phần(?!\s+trăm)|mục|loại|lý\s+do|dấu\s+hiệu|sai\s+lầm|câu\s+hỏi|ví\s+dụ|lượt|video|tập|chương)(?![^\W\d_])",
    re.IGNORECASE,
)

# Meaningful statistical / numeric expressions (WARN when unlinked):
# - Percentages: `20%`, `40–60%`, `20 phần trăm`, `40 đến 60 phần trăm`
# - Years: `19xx` / `20xx`
# - Multipliers: `2 lần`, `6 lần`, `3,5 lần`
# - Ratios: `1/3`, `1:10`, `3 trong 10`, `1 trên 5`
# - Quantified study/clinical/duration counts: `6 ngày`, `2 tuần`, `3 tháng`, `100 người`, `2 lít`, `38 độ`, ...
# - Decimal numerals (`1,5`, `2.5`) or multi-digit numerals (`>= 10`) not already masked
# Bare single-digit indices (`1`..`9` without unit/ratio/decimal, e.g. `TERM 1`, `nhóm 2`) are ignored.
_STAT_UNITS = (
    r"người|bệnh\s+nhân|ca|trường\s+hợp|"
    r"ngày|tuần|tháng|năm|phút|tiếng|"
    r"lít|kg|cm|mm|độ|°C|kcal|calo"
)
_MEANINGFUL_NUMBER_RE = re.compile(
    rf"(?<!\w){_NUM_EXPR}\s*(?:%|phần\s+trăm)(?![^\W\d_])"
    rf"|(?<!\w)(?:19|20)\d{{2}}(?!\d)"
    rf"|(?<!\w){_NUM_EXPR}\s+lần(?![^\W\d_])"
    rf"|(?<!\w){_NUM}\s*(?:/|:|trong|trên)\s*{_NUM}(?!\w)"
    rf"|(?<!\w){_NUM_EXPR}\s+(?:{_STAT_UNITS})(?![^\W\d_])"
    rf"|(?<!\w)\d+[.,]\d+(?!\w)"
    rf"|(?<!\w)\d{{2,}}(?!\w)",
    re.IGNORECASE,
)


def _check_unclaimed_numbers(line_id: str, text: str) -> list[QAIssue]:
    """Flag unlinked spoken lines that state medical doses (error/BLOCK) or meaningful numbers (warning/WARN).

    Rules:
    - `dose_without_claim` (severity="error"): Arabic number/range paired with a dose, lab,
      blood-pressure, or pill unit (`mg`, `mcg`, `µg`, `ml`, `IU`, `đơn vị`, `viên`, `g/dL`,
      `mmol/L`, `mmHg`, `U/L`, `miligam`, `gam`, etc.).
    - `number_without_claim` (severity="warning"): percentages (`%`, `phần trăm`), years
      (`19xx`/`20xx`), multipliers (`x lần`), ratios (`1/3`, `3 trong 10`), quantified
      clinical/duration/population counts (`6 ngày`, `2 lít`, `100 người`), or unmasked
      decimal/multi-digit numerals after removing matched dose spans.

    False-positive avoidance:
    - Natural Vietnamese prose without digits (`một`, `hai bước`, `mỗi ngày`) is never matched.
    - Bare single-digit labels/indices (`TERM 1`, `nhóm 2`) without units/ratios are ignored.
    - Alphanumeric compound names (`B12`, `D3`, `omega-3`, `COVID-19`), clock times
      (`7 giờ sáng`, `8h30`, `22:00`), ordinals/types (`thứ 2`, `týp 2`, `bước 1`),
      citation brackets (`[1]`), and structural counts (`3 bước`, `1 lượt like`) are ignored.
    """
    issues: list[QAIssue] = []
    dose_matches = list(_DOSE_RE.finditer(text))
    if dose_matches:
        unique_doses = list(dict.fromkeys(m.group(0).strip() for m in dose_matches))
        issues.append(
            QAIssue(
                code="dose_without_claim",
                line_id=line_id,
                message=f"liều/chỉ số không có claim_id: {', '.join(unique_doses)}",
                severity="error",
            )
        )
    # Mask matched dose spans and natural non-statistical expressions before scanning for numbers.
    masked = _DOSE_RE.sub(lambda m: " " * len(m.group(0)), text)
    masked = _IGNORED_NUMBER_RE.sub(lambda m: " " * len(m.group(0)), masked)
    number_matches = list(_MEANINGFUL_NUMBER_RE.finditer(masked))
    if number_matches:
        unique_numbers = list(dict.fromkeys(m.group(0).strip() for m in number_matches))
        issues.append(
            QAIssue(
                code="number_without_claim",
                line_id=line_id,
                message=f"số liệu không có claim_id: {', '.join(unique_numbers)}",
                severity="warning",
            )
        )
    return issues


def review_script(
    script: Script,
    claims: list[EvidenceClaim],
    forbidden_phrases: list[str],
    *,
    explainer: Explainer | None = None,
) -> list[QAIssue]:
    known = {claim.id for claim in claims}
    issues: list[QAIssue] = []
    for line in script.lines:
        lowered = line.text.casefold()
        for phrase in forbidden_phrases:
            if phrase.casefold() in lowered:
                issues.append(
                    QAIssue(
                        code="forbidden_phrase", line_id=line.id, message=phrase
                    )
                )
        if line.claim_id and line.claim_id not in known:
            issues.append(
                QAIssue(code="unknown_claim", line_id=line.id, message=line.claim_id)
            )
        if line.claim_id is None:
            issues.extend(_check_unclaimed_numbers(line.id, line.text))
        spoken_sentences = re.split(r"[.?!…]+", line.text)
        if any(
            len(sentence.split()) > 32
            for sentence in spoken_sentences
            if sentence.split()
        ):
            issues.append(
                QAIssue(
                    code="long_spoken_sentence",
                    line_id=line.id,
                    message="over 32 words",
                )
            )
    if script.format_profile == "explain_first_v1":
        issues.extend(_review_explain_first(script, explainer))
    return issues


# Spec §3; percentages of words on marked lines estimate duration, not actual timing.
_BEAT_RANGES = {1: (5, 10), 2: (10, 15), 3: (15, 20), 4: (20, 25),
                5: (10, 15), 6: (15, 20), 7: (5, 10)}


def _review_explain_first(script: Script, explainer: Explainer | None) -> list[QAIssue]:
    issues: list[QAIssue] = []
    if explainer is None:
        issues.append(QAIssue(
            code="missing_explainer", line_id="", message="explain_first_v1 requires explainer.yaml",
        ))
    layers = {layer.id: layer for layer in explainer.layers} if explainer else {}
    introduced: set[str] = set()
    previous: int | None = None
    words = dict.fromkeys(_BEAT_RANGES, 0)
    first_line: dict[int, str] = {}
    for line in script.lines:
        beat = line.arc_beat
        if beat is not None:
            if previous is not None and beat < previous and (previous, beat) != (6, 2):
                issues.append(QAIssue(
                    code="arc_beat_order", line_id=line.id,
                    message=f"beat {previous} -> {beat}: only 6 -> 2 may restart a chapter",
                ))
            previous = beat
            words[beat] += len(line.text.split())
            first_line.setdefault(beat, line.id)
        if line.explainer_layer_id is not None and line.explainer_layer_id not in layers:
            issues.append(QAIssue(
                code="unknown_explainer_layer", line_id=line.id,
                message=line.explainer_layer_id,
            ))
        lowered = line.text.casefold()
        for layer in layers.values():
            if layer.id not in introduced:
                for term in layer.terms_introduced:
                    if term.casefold() in lowered:
                        issues.append(QAIssue(
                            code="term_before_introduction", line_id=line.id,
                            message=f"{term}: layer {layer.id} must appear on an earlier line",
                        ))
        # The introducing line must precede dialogue that uses its terms.
        if line.explainer_layer_id in layers:
            introduced.add(line.explainer_layer_id)
    total = sum(words.values())
    for beat, count in words.items():
        low, high = _BEAT_RANGES[beat]
        if count and not low * total <= 100 * count <= high * total:
            issues.append(QAIssue(
                code="arc_beat_ratio", line_id=first_line[beat], severity="warning",
                message=f"beat {beat}: {100 * count / total:.1f}% of marked words; expected {low}–{high}%",
            ))
    return issues


def lint_project_script(project_dir: Path) -> list[QAIssue]:
    """Read the active script and its references without mutating project artifacts."""
    data = read_yaml(project_dir / "project.yaml")
    project = ProjectManifestV2.model_validate(data)
    revision = project_dir / "revisions" / project.active_revision
    script = Script.model_validate(read_yaml(revision / "script" / "script.yaml"))
    ledger = read_yaml(revision / "evidence" / "ledger.yaml")
    claims = [EvidenceClaim.model_validate(item) for item in ledger.get("claims", [])]
    explainer = None
    if script.format_profile == "explain_first_v1":
        path = revision / "explainer" / "explainer.yaml"
        if path.is_file():
            explainer = read_explainer(revision)
    return review_script(script, claims, [], explainer=explainer)
