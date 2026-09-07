from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.script import Delivery, Script, ScriptLine
from healthvideo.qa.script import review_script


def test_qa_rejects_unmapped_claim_and_machine_phrase() -> None:
    script = Script(
        title="Muối",
        lines=[
            ScriptLine(
                id="L01",
                text="Hãy cùng tìm hiểu: ăn mặn chắc chắn gây bệnh [1].",
                claim_id="C99",
                source_marker="[1]",
                delivery=Delivery(intent="problem"),
            )
        ],
    )
    issues = review_script(
        script,
        [
            EvidenceClaim(
                id="C01",
                text_public="Giảm muối giúp hạ huyết áp",
                text_technical="Reduced sodium lowers BP",
                type="evidence",
                sources=["R01"],
            )
        ],
        ["hãy cùng tìm hiểu"],
    )

    assert {issue.code for issue in issues} == {"forbidden_phrase", "unknown_claim"}


def test_qa_flags_a_line_that_is_too_long_to_read_aloud() -> None:
    script = Script(
        title="Muối",
        lines=[
            ScriptLine(
                id="L02",
                text=" ".join(["từ"] * 33),
                claim_id="C01",
                source_marker="[1]",
                delivery=Delivery(intent="evidence"),
            )
        ],
    )

    issues = review_script(
        script,
        [
            EvidenceClaim(
                id="C01",
                text_public="Giảm muối giúp hạ huyết áp",
                text_technical="Reduced sodium lowers BP",
                type="evidence",
                sources=["R01"],
            )
        ],
        [],
    )

    assert [(issue.code, issue.line_id) for issue in issues] == [
        ("long_spoken_sentence", "L02")
    ]
