"""Unit and workflow integration tests for Vietnamese script style linting."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.script import Script, ScriptLine
from healthvideo.domain.script_style import StyleIssue, lint_script_style
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.draft import submit_draft
from healthvideo.workflows.review_html import render_medical_packet
from tests.workflows.test_draft import SOURCE, _evidence_ready

RUNNER = CliRunner()


def _draft_ready_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    project = _evidence_ready(tmp_path)
    script = tmp_path / "script.yaml"
    shutil.copy2(SOURCE / "script/script.yaml", script)
    return (project, script, SOURCE / "storyboard/storyboard.yaml",
            SOURCE / "assets/asset-manifest.yaml")


def test_meta_visual_blocked() -> None:
    script = Script(
        title="Test meta visual",
        lines=[
            ScriptLine(
                id="L01",
                text="Ô vuông trên màn hình là một phần dịch",
                claim_id="C01",
            ),
        ],
    )
    issues = lint_script_style(script)
    assert any(
        issue.line_id == "L01"
        and issue.rule == "meta_visual"
        and issue.severity == "block"
        for issue in issues
    )
    assert StyleIssue(
        line_id="L01",
        rule="meta_visual",
        excerpt="trên màn hình",
        severity="block",
    ) in issues


def test_presenter_cliche_blocked() -> None:
    script = Script(
        title="Test presenter cliche",
        lines=[
            ScriptLine(
                id="L01",
                text="Video này bắt đầu từ khoảnh khắc dịch trong khớp bão hòa.",
                claim_id="C01",
            ),
            ScriptLine(
                id="L02",
                text="Điều cần giữ lại từ các nguồn là ba chuyện khác nhau.",
                claim_id="C01",
            ),
        ],
    )
    issues = lint_script_style(script)
    blocked_lines = {
        issue.line_id
        for issue in issues
        if issue.rule == "presenter_cliche" and issue.severity == "block"
    }
    assert blocked_lines == {"L01", "L02"}


def test_repeated_caveat_blocked() -> None:
    repeated_sentence_script = Script(
        title="Test repeated caveat sentence",
        lines=[
            ScriptLine(
                id="L01",
                text=(
                    "Urat vượt ngưỡng bão hòa sẽ kết tủa. "
                    "Mô hình này chưa cho biết nguy cơ của từng cá nhân."
                ),
                claim_id="C01",
            ),
            ScriptLine(
                id="L02",
                text=(
                    "Tinh thể có thể nằm yên trong khớp. "
                    "Mô hình này chưa cho biết nguy cơ của từng cá nhân."
                ),
                claim_id="C01",
            ),
        ],
    )
    issues_sentence = lint_script_style(repeated_sentence_script)
    assert any(
        issue.rule == "repeated_caveat" and issue.severity == "block"
        for issue in issues_sentence
    )

    repeated_phrase_script = Script(
        title="Test repeated caveat phrase across 3 lines",
        lines=[
            ScriptLine(
                id="L01",
                text="Kết quả đầu tiên quan sát từ thí nghiệm ngoài cơ thể.",
                claim_id="C01",
            ),
            ScriptLine(
                id="L02",
                text="Bước tạo mầm này cũng dựa vào thí nghiệm ngoài cơ thể.",
                claim_id="C01",
            ),
            ScriptLine(
                id="L03",
                text="Tốc độ lớn của kim được đo trong thí nghiệm ngoài cơ thể.",
                claim_id="C01",
            ),
        ],
    )
    issues_phrase = lint_script_style(repeated_phrase_script)
    assert any(
        issue.line_id == "L03"
        and issue.rule == "repeated_caveat"
        and issue.severity == "block"
        for issue in issues_phrase
    )


def test_new_style_sample_passes() -> None:
    script = Script(
        title="Gút cấp — vì sao dịch khớp kết tinh rồi bùng viêm?",
        format_profile="explain_first_v1",
        lines=[
            ScriptLine(
                id="L01",
                purpose="content",
                arc_beat=1,
                claim_id="M08",
                text=(
                    "Ai từng lên cơn gút thì sẽ nhớ mãi cái đau đó. Khớp sưng lên, "
                    "đau tới mức chạm nhẹ cũng thấy buốt. Còn người xung quanh thì "
                    "kiểu gì cũng hỏi đúng một câu: hôm qua ăn gì đấy?"
                ),
            ),
            ScriptLine(
                id="L03",
                purpose="content",
                arc_beat=2,
                claim_id="M01",
                text=(
                    "Nhân vật chính hôm nay tên là urat. Nhiều người quen gọi nó là "
                    "axit uric. Bình thường, urat nằm hòa tan trong dịch, giống đường "
                    "tan trong cốc nước, nhìn vào chẳng thấy gì."
                ),
            ),
            ScriptLine(
                id="L04",
                purpose="content",
                arc_beat=3,
                claim_id="M01",
                text=(
                    "Có điều cốc nước chỉ hòa được chừng ấy đường thôi. Bỏ thêm nữa "
                    "là đường không tan hết, lắng xuống đáy. Urat cũng vậy: dịch chỉ "
                    "giữ được một lượng urat nhất định ở dạng hòa tan."
                ),
            ),
            ScriptLine(
                id="L06",
                purpose="content",
                arc_beat=4,
                claim_id="M02",
                text=(
                    "Khi lượng urat vượt quá mức dịch giữ được, người ta gọi là quá "
                    "bão hòa. Lúc này urat bắt đầu túm lại thành những hạt rất nhỏ, "
                    "gọi là mầm tinh thể. Rồi mầm cứ thế lớn dần lên."
                ),
            ),
            ScriptLine(
                id="L08",
                purpose="content",
                arc_beat=4,
                claim_id="M04",
                text=(
                    "Nghe tới kim là nhiều người gật gù ngay: à, thì ra kim đâm vào "
                    "nên đau. Nghe rất hợp lý. Có điều nếu đúng như vậy thì có một "
                    "chuyện rất khó giải thích."
                ),
            ),
            ScriptLine(
                id="L09",
                purpose="content",
                arc_beat=5,
                claim_id="M05",
                text=(
                    "Tinh thể có thể nằm sẵn trong khớp mà người ta chẳng thấy gì cả. "
                    "Không sưng, không đau. Tinh thể vẫn ở đó, nhưng cơn gút chưa nổ ra."
                ),
            ),
            ScriptLine(
                id="L20",
                purpose="content",
                arc_beat=7,
                claim_id=None,
                text=(
                    "Video này chỉ để hiểu cơ chế thôi. Nó không thay được buổi khám, "
                    "và cũng đừng dựa vào nó để tự chọn hay đổi thuốc nhé."
                ),
            ),
            ScriptLine(
                id="L21",
                purpose="outro",
                arc_beat=7,
                claim_id=None,
                text=(
                    "Nếu mình có chỗ nào chưa đúng, hoặc bạn có câu hỏi, cứ để lại "
                    "bình luận. Cảm ơn bạn đã xem."
                ),
            ),
        ],
    )
    issues = lint_script_style(script)
    blocks = [issue for issue in issues if issue.severity == "block"]
    assert blocks == []


def test_old_gout_script_flags() -> None:
    script = Script(
        title="Old gout script sample",
        format_profile="explain_first_v1",
        lines=[
            ScriptLine(
                id="N03",
                claim_id="M01",
                text=(
                    "Ô vuông trên màn hình là một phần dịch được phóng đại để dễ nhìn. "
                    "Nó không phải hình cắt giải phẫu đầy đủ của khớp. Các chấm nhỏ "
                    "tượng trưng cho một chất đang hòa tan. Hãy nhìn cách chúng nằm "
                    "rải ra trong ô dịch. Chúng ta dùng cùng ô này suốt phần sau, để "
                    "thấy lúc nào chất còn hòa tan và lúc nào xuất hiện hạt rắn."
                ),
            ),
            ScriptLine(
                id="N04",
                claim_id="M01",
                text=(
                    "Chất đang nói tới là urat, tên sẽ được dùng từ đây. Câu hỏi "
                    "thường gọi là axit uric kết tinh; hình mô phỏng đang theo dõi "
                    "urat trong dịch. Mỗi chấm chỉ là ký hiệu để theo dõi câu chuyện. "
                    "Đừng đếm chấm để suy ra kết quả xét nghiệm. Hình này không mô tả "
                    "nguyên tử, không có thước đo và không cho biết nồng độ của một "
                    "người cụ thể."
                ),
            ),
            ScriptLine(
                id="N05",
                claim_id="M05",
                text=(
                    "Bây giờ đổi sang ô phóng đại tế bào. Màu xanh là ký hiệu cho "
                    "tế bào miễn dịch; vệt sáng nhỏ gợi một mảnh chất rắn ở gần nó. "
                    "Cảnh đang yên để nhắc một điều: lắng đọng có thể tồn tại mà chưa "
                    "có triệu chứng. Đây là sơ đồ quan hệ giữa các thành phần. Đường "
                    "viền và màu sắc không phải ảnh quan sát trực tiếp dưới kính hiển vi."
                ),
            ),
            ScriptLine(
                id="N09",
                claim_id="M05",
                text=(
                    "Có chuông chưa có nghĩa cả khu phố phải nghe báo động. Ở ô tế "
                    "bào, một mảnh lắng đọng không đủ để kết luận cơn viêm đang diễn "
                    "ra. Nhìn thấy nguyên liệu của câu chuyện khác với nhìn thấy cả "
                    "câu chuyện đã xảy ra. Ẩn dụ chuông nằm im có giới hạn: phản ứng "
                    "viêm cần những điều kiện sinh học cụ thể để khởi động. Tăng urat, "
                    "có lắng đọng và có cơn viêm đau cần được phân biệt."
                ),
            ),
        ],
    )
    issues = lint_script_style(script)
    for expected_line in ("N03", "N04", "N05", "N09"):
        line_blocks = [
            issue
            for issue in issues
            if issue.line_id == expected_line and issue.severity == "block"
        ]
        assert line_blocks, f"Expected at least one block on {expected_line}"


def test_warn_rules_detected() -> None:
    long_30_words = " ".join(["cơ chế sinh học diễn ra âm thầm"] * 7) + "."
    script = Script(
        title="Test warn rules",
        lines=[
            ScriptLine(
                id="L01",
                claim_id="C01",
                text=(
                    "Đó không phải là gai nhọn mà là tín hiệu. "
                    "Cũng không phải là va chạm mà là phản ứng. "
                    "Và không phải là trầy xước mà là báo động."
                ),
            ),
            ScriptLine(
                id="L02",
                claim_id="C01",
                text=(
                    "Nó gồm đại thực bào, bạch cầu và mô khớp. "
                    "Cần chú ý nhiệt độ, độ toan và nồng độ. "
                    "Ta phân biệt tăng urat, lắng đọng và cơn đau. "
                    "Hãy nhớ giải phẫu, sinh lý và bệnh học."
                ),
            ),
            ScriptLine(
                id="L03",
                claim_id="C01",
                text=(
                    f"{long_30_words} "
                    "Ẩn dụ cốc nước chỉ mở đầu. Ví dụ quả chuông giúp hình dung phần sau."
                ),
            ),
        ],
    )
    issues = lint_script_style(script)
    warn_rules = {issue.rule for issue in issues if issue.severity == "warn"}
    assert {"not_x_but_y", "triad", "long_sentence", "metaphor_disclaimer"} <= warn_rules


def test_draft_step_rejects_style_block(tmp_path: Path) -> None:
    project, script_path, storyboard_path, assets_path = _draft_ready_inputs(tmp_path)
    data = read_yaml(script_path)
    data["lines"][0]["text"] = (
        "Ô vuông trên màn hình là một phần dịch. " + data["lines"][0]["text"]
    )
    write_yaml_atomic(script_path, data)

    with pytest.raises(ValueError, match=r"script style block.*L01.*meta_visual"):
        submit_draft(project, script_path, storyboard_path, assets_path)

    cli_res = RUNNER.invoke(
        app,
        [
            "step",
            "draft",
            str(project),
            "--script",
            str(script_path),
            "--storyboard",
            str(storyboard_path),
            "--assets",
            str(assets_path),
        ],
    )
    assert cli_res.exit_code == 1
    assert "meta_visual" in cli_res.stdout
    assert "L01" in cli_res.stdout
    assert (
        ProjectManifestV2.model_validate(read_yaml(project / "project.yaml")).state
        is WorkflowState.EVIDENCE_READY
    )


def test_draft_step_records_style_warnings_in_packet(tmp_path: Path) -> None:
    project, script_path, storyboard_path, assets_path = _draft_ready_inputs(tmp_path)
    data = read_yaml(script_path)
    data["lines"][0]["text"] = (
        "Ẩn dụ cốc nước rất quen thuộc. Ví dụ chiếc chuông giúp hình dung dễ hơn. "
        + data["lines"][0]["text"]
    )
    write_yaml_atomic(script_path, data)
    board = read_yaml(storyboard_path)
    for scene in board["scenes"]:
        if scene.get("script_line_id") == data["lines"][0]["id"]:
            scene["narration"] = data["lines"][0]["text"]
    storyboard_path = tmp_path / "storyboard.yaml"
    write_yaml_atomic(storyboard_path, board)

    cli_res = RUNNER.invoke(
        app,
        [
            "step",
            "draft",
            str(project),
            "--script",
            str(script_path),
            "--storyboard",
            str(storyboard_path),
            "--assets",
            str(assets_path),
        ],
    )
    assert cli_res.exit_code == 0, cli_res.stdout
    assert "warn [L01] (metaphor_disclaimer)" in cli_res.stdout
    style_lint = project / "revisions/001/reviews/style-lint.json"
    assert style_lint.is_file()
    html = render_medical_packet(project / "revisions/001")
    assert "<h2>Văn phong</h2>" in html
    assert "metaphor_disclaimer" in html


def _rules(*texts: str) -> set[tuple[str, str]]:
    script = Script(title="AI signs", lines=[
        ScriptLine(id=f"L{index:02}", text=text, claim_id="C01")
        for index, text in enumerate(texts, start=1)
    ])
    return {(issue.rule, issue.severity) for issue in lint_script_style(script)}


def test_ai_writing_signs_block_chatbot_summaries_and_markup() -> None:
    assert ("ai_chatbot", "block") in _rules("Tóm lại, urat lắng trong khớp.")
    assert ("ai_chatbot", "block") in _rules("Câu hỏi hay đấy, vì sao lại đau?")
    assert ("ai_markup", "block") in _rules("Urat **kết tinh** ở khớp lạnh.")
    assert ("ai_markup", "block") in _rules("Urat kết tinh [chèn số liệu].")


def test_ai_writing_signs_warn_puffery_vocab_dash_and_parallelism() -> None:
    assert ("ai_puffery", "warn") in _rules("Urat đóng vai trò then chốt trong cơn đau.")
    assert ("ai_puffery", "warn") in _rules("Nhiều nghiên cứu cho thấy khớp lạnh dễ kết tinh.")
    assert ("ai_em_dash", "warn") in _rules("Urat — chất thải của purin — lắng xuống.")
    vocab = ["Một hành trình thực sự sâu sắc.", "Chìa khóa vô cùng toàn diện."]
    assert ("ai_vocab", "warn") in _rules(*vocab)
    assert ("ai_vocab", "warn") not in _rules("Chuyện này thực sự lạ.")
    assert ("not_x_but_y", "warn") in _rules(
        "Không chỉ đau mà còn sưng.", "Do viêm chứ không phải kim đâm.",
        "Không phải kim mà là viêm.")


def test_plain_human_sentence_passes_ai_rules() -> None:
    rules = _rules("Urat là chất thải khi cơ thể phân giải purin. Máu có quá nhiều thì nó kết tinh.")
    assert not {rule for rule, _ in rules if rule.startswith("ai_")}
