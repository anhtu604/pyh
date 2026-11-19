from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.explainer import Explainer
from healthvideo.domain.script import Delivery, Script, ScriptLine
from healthvideo.qa.script import review_script
from tests.domain.test_explainer import explainer_data


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
        explainer=Explainer.model_validate(explainer_data()),
    )

    assert {issue.code for issue in issues} == {"forbidden_phrase", "unknown_claim"}


def test_qa_does_not_flag_two_20_word_sentences_in_one_line() -> None:
    first_sentence = " ".join(["từ"] * 20)
    second_sentence = " ".join(["khác"] * 20)
    script = Script(
        title="Muối",
        lines=[
            ScriptLine(
                id="L02",
                text=f"{first_sentence}. {second_sentence}.",
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
        explainer=Explainer.model_validate(explainer_data()),
    )

    assert issues == []


def test_qa_ignores_empty_segments_between_sentence_terminators() -> None:
    first_sentence = " ".join(["từ"] * 20)
    second_sentence = " ".join(["khác"] * 20)
    script = Script(
        title="Muối",
        lines=[
            ScriptLine(
                id="L03",
                text=f"... {first_sentence}…!? {second_sentence}?! ...",
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
        explainer=Explainer.model_validate(explainer_data()),
    )

    assert issues == []


def test_qa_flags_one_unpunctuated_33_word_sentence() -> None:
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
        explainer=Explainer.model_validate(explainer_data()),
    )

    assert [(issue.code, issue.line_id) for issue in issues] == [
        ("long_spoken_sentence", "L02")
    ]


def test_qa_blocks_unclaimed_dose_and_warns_unclaimed_numbers() -> None:
    script = Script(
        title="Vitamin C",
        lines=[
            ScriptLine(id="L01", text="Uống 500 mg mỗi ngày để tăng sức đề kháng."),
            ScriptLine(id="L02", text="Huyết áp đo được 140/90 mmHg và đường huyết 7,2 mmol/L."),
            ScriptLine(id="L03", text="Mỗi sáng uống 2 viên hoặc 1000 IU vitamin D."),
            ScriptLine(id="L04", text="Tỷ lệ giảm 20% theo nghiên cứu năm 2024 và tăng 3 lần nguy cơ."),
            ScriptLine(id="L05", text="Nguy cơ tăng khoảng 40 đến 60 phần trăm."),
        ],
    )
    issues = review_script(
        script,
        [],
        [],
        explainer=Explainer.model_validate(explainer_data()),
    )

    by_line = [(issue.line_id, issue.code, issue.severity) for issue in issues]
    assert ("L01", "dose_without_claim", "error") in by_line
    assert ("L02", "dose_without_claim", "error") in by_line
    assert ("L03", "dose_without_claim", "error") in by_line
    assert ("L04", "number_without_claim", "warning") in by_line
    assert ("L05", "number_without_claim", "warning") in by_line
    # Matched doses should not also produce duplicate number_without_claim warnings.
    assert ("L01", "number_without_claim", "warning") not in by_line
    assert ("L02", "number_without_claim", "warning") not in by_line
    assert ("L03", "number_without_claim", "warning") not in by_line


def test_qa_allows_doses_and_numbers_when_claim_id_is_present() -> None:
    script = Script(
        title="Vitamin C",
        lines=[
            ScriptLine(
                id="L01",
                text="Uống 1000 miligam mỗi ngày tăng 19% nguy cơ trong nghiên cứu năm 2023.",
                claim_id="C01",
                source_marker="[1]",
            )
        ],
    )
    issues = review_script(
        script,
        [
            EvidenceClaim(
                id="C01",
                text_public="Liều cao vitamin C liên quan tăng nguy cơ sỏi thận.",
                text_technical="High-dose vitamin C associated with kidney stones.",
                type="evidence",
                sources=["R01"],
            )
        ],
        [],
        explainer=Explainer.model_validate(explainer_data()),
    )

    assert issues == []


def test_qa_ignores_natural_counts_and_general_times_without_claim() -> None:
    script = Script(
        title="Thói quen",
        lines=[
            ScriptLine(id="L01", text="Hãy thử làm theo 3 bước đơn giản mỗi ngày."),
            ScriptLine(id="L02", text="Chỉ cần một cốc nước và hai bước nhẹ nhàng buổi sáng."),
            ScriptLine(id="L03", text="Ngủ trước 22:00 và thức dậy lúc 7 giờ sáng hoặc 8h30."),
            ScriptLine(id="L04", text="Đái tháo đường týp 2 và omega-3 hay vitamin B12."),
            ScriptLine(
                id="L05",
                purpose="outro",
                text="Nếu thấy hay, hãy để lại 1 lượt like và subscribe cho chúng mình.",
            ),
        ],
    )
    issues = review_script(
        script,
        [],
        [],
        explainer=Explainer.model_validate(explainer_data()),
    )

    assert issues == []
