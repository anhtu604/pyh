from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.domain.explainer import Explainer
from healthvideo.domain.script import Delivery, Script, ScriptLine
from healthvideo.qa.script import review_script
from healthvideo.storage.explainer import write_explainer
from healthvideo.storage.files import write_yaml_atomic
from tests.domain.test_explainer import explainer_data


def line(beat: int | None, text: str = "Illustration", layer: str | None = None) -> ScriptLine:
    return ScriptLine(
        id="test-line", text=text, arc_beat=beat, explainer_layer_id=layer,
        delivery=Delivery(intent="illustrate"),
    )


def script(lines: list[ScriptLine], profile: str = "explain_first_v1") -> Script:
    return Script(title="Illustrative test only", format_profile=profile, lines=lines)


def review(lines: list[ScriptLine]):
    return review_script(script(lines), [], [], explainer=Explainer(**explainer_data()))


@pytest.mark.parametrize("beat", [1, 7, None])
def test_arc_fields_round_trip(beat: int | None) -> None:
    restored = ScriptLine.model_validate(line(beat, layer="L1").model_dump())
    assert restored.arc_beat == beat
    assert restored.explainer_layer_id == "L1"


@pytest.mark.parametrize("beat", [0, 8, -1])
def test_arc_beat_outside_range_is_rejected(beat: int) -> None:
    with pytest.raises(ValidationError, match="arc_beat"):
        line(beat)


@pytest.mark.parametrize(
    ("beats", "errors"),
    [([1, 2, 3, 4, 5, 6, 7], 0), ([2, 2, None, 3, 6, 2, 4, 6, 7], 0),
     ([4, 3], 1), ([5, 2], 1), ([6, 3], 1), ([7, 2], 1), ([6, None, 2], 0)],
)
def test_arc_order_and_only_six_to_two_chapter_restart(beats, errors) -> None:
    issues = review([line(beat) for beat in beats])
    assert sum(issue.code == "arc_beat_order" for issue in issues) == errors


def test_optional_layer_reference_must_resolve() -> None:
    issues = review([line(None), line(2, layer="L1"), line(3, layer="missing")])
    errors = [issue for issue in issues if issue.code == "unknown_explainer_layer"]
    assert len(errors) == 1
    assert errors[0].severity == "error"
    assert "missing" in errors[0].message


def test_explain_first_requires_explainer() -> None:
    issues = review_script(script([line(2)]), [], [])
    assert any(i.code == "missing_explainer" and i.severity == "error" for i in issues)


@pytest.mark.parametrize("profile", ["legacy", "hook_outro_v1"])
def test_old_profiles_do_not_run_new_lint(profile: str) -> None:
    old = script([line(6, "TEST TERM 1", "missing"), line(2)], profile)
    assert review_script(old, [], []) == []
    assert review_script(old, [], [], explainer=Explainer(**explainer_data())) == []
    old_line = ScriptLine(id="old", text="Illustration", delivery=Delivery(intent="test"))
    assert old_line.arc_beat is None
    assert old_line.explainer_layer_id is None


def test_term_requires_earlier_layer_line_and_matches_casefolded_substring() -> None:
    lines = [
        line(None, "prefixTEST TERM 2suffix"),
        line(2, "TEST TERM 1", "L1"),
        line(3, "Illustration", "L2"),
        line(4, "test term 1 and TEST TERM 2"),
    ]
    for index, item in enumerate(lines):
        item.id = f"S{index}"
    errors = [i for i in review(lines) if i.code == "term_before_introduction"]
    assert [(i.line_id, i.severity) for i in errors] == [("S0", "error"), ("S1", "error")]


def test_word_ratios_in_range_and_unmarked_words_ignored() -> None:
    # Hand-counted 100 marked words, all seven shares within spec §3.
    counts = [7, 12, 18, 24, 12, 19, 8]
    lines = [line(i, " ".join(["example"] * n)) for i, n in enumerate(counts, 1)]
    lines.append(line(None, ". ".join(["unmarked"] * 100)))
    assert review(lines) == []


@pytest.mark.parametrize("counts", [[5, 10, 20, 25, 10, 20, 10], [10, 15, 15, 20, 15, 15, 10]])
def test_ratio_bounds_are_inclusive(counts) -> None:
    assert review([line(i, " ".join(["example"] * n)) for i, n in enumerate(counts, 1)]) == []


def test_ratio_outliers_are_warnings_and_skipped_beats_do_not_warn() -> None:
    issues = review([line(2, "example example"), line(3, "example"), line(4, "")])
    assert [(i.code, i.severity) for i in issues] == [
        ("arc_beat_ratio", "warning"), ("arc_beat_ratio", "warning"),
    ]
    assert "2" in issues[0].message
    assert "3" in issues[1].message
    assert review([line(None), line(2, "")]) == []


@pytest.mark.parametrize("profile", ["legacy", "hook_outro_v1", "explain_first_v1"])
@pytest.mark.parametrize("revisioned", [False, True])
def test_cli_lint_loads_explainer_only_for_explain_first(tmp_path: Path, profile, revisioned) -> None:
    root = tmp_path
    write_yaml_atomic(root / "project.yaml", {
        "schema_version": "2.0" if revisioned else "1.0", "slug": "test-only",
    })
    revision = root / "revisions" / "001" if revisioned else root
    write_yaml_atomic(revision / "script/script.yaml", script([line(2)], profile).model_dump())
    write_yaml_atomic(revision / "evidence/ledger.yaml", {"claims": []})
    if profile != "explain_first_v1":
        # A malformed explainer must not be opened for an old script.
        write_yaml_atomic(revision / "explainer/explainer.yaml", {"invalid": True})
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = CliRunner().invoke(app, ["script", "lint", str(root)])
    assert result.exit_code == (1 if profile == "explain_first_v1" else 0), result.output
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
    if profile == "explain_first_v1":
        assert "missing_explainer" in result.output
        write_explainer(revision, Explainer(**explainer_data()))
        result = CliRunner().invoke(app, ["script", "lint", str(root)])
        assert result.exit_code == 0, result.output
        assert "warning" in result.output
        assert "arc_beat_ratio" in result.output
        write_yaml_atomic(revision / "script/script.yaml", script([line(4), line(3)]).model_dump())
        result = CliRunner().invoke(app, ["script", "lint", str(root)])
        assert result.exit_code == 1
        assert "arc_beat_order" in result.output
