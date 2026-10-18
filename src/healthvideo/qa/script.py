import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.explainer import Explainer
from healthvideo.domain.project import ProjectManifest
from healthvideo.domain.project_v2 import ProjectManifestV2
from healthvideo.domain.script import Script
from healthvideo.storage.explainer import read_explainer
from healthvideo.storage.files import read_yaml


class QAIssue(BaseModel):
    code: str
    line_id: str
    message: str
    severity: Literal["error", "warning"] = "error"


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
    if data.get("schema_version") == "2.0":
        project = ProjectManifestV2.model_validate(data)
        revision = project_dir / "revisions" / project.active_revision
    else:
        ProjectManifest.model_validate(data)
        revision = project_dir
    script = Script.model_validate(read_yaml(revision / "script" / "script.yaml"))
    ledger = read_yaml(revision / "evidence" / "ledger.yaml")
    claims = [EvidenceClaim.model_validate(item) for item in ledger.get("claims", [])]
    explainer = None
    if script.format_profile == "explain_first_v1":
        path = revision / "explainer" / "explainer.yaml"
        if path.is_file():
            explainer = read_explainer(revision)
    return review_script(script, claims, [], explainer=explainer)
