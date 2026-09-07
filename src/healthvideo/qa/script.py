import re

from pydantic import BaseModel

from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.script import Script


class QAIssue(BaseModel):
    code: str
    line_id: str
    message: str


def review_script(
    script: Script,
    claims: list[EvidenceClaim],
    forbidden_phrases: list[str],
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
    return issues
