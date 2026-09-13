import pytest
from pydantic import ValidationError

from healthvideo.domain.evidence import ChartDatum, EvidenceClaim
from healthvideo.visuals.charts import render_count_chart


def datum(**changes: object) -> ChartDatum:
    data = {
        "id": "bp-count",
        "source_id": "R01",
        "label": "Người có kết quả",
        "value": 12,
        "denominator": 40,
        "unit": "người",
        "ci_low": 10,
        "ci_high": 15,
    }
    data.update(changes)
    return ChartDatum.model_validate(data)


def test_count_chart_is_deterministic_and_displays_original_scale() -> None:
    first = render_count_chart(datum())
    assert first == render_count_chart(datum())
    svg = first.decode("utf-8")
    for label in ("Người có kết quả", "12", "N=40", "người", "Trục 0–40", "CI 10–15"):
        assert label in svg
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg
    assert "href=" not in svg and "<script" not in svg and "foreignObject" not in svg
    assert datum().kind == "count_of_total"


def test_svg_escapes_untrusted_label() -> None:
    assert "&lt;script&gt;" in render_count_chart(datum(label="<script>")).decode()


@pytest.mark.parametrize(
    "changes",
    [
        {"value": "NaN"},
        {"value": "Infinity"},
        {"value": -1},
        {"value": 41},
        {"value": 12.25},
        {"kind": "rate"},
        {"denominator": 0},
        {"unit": " "},
        {"source_id": ""},
        {"ci_low": 16, "ci_high": 15},
        {"ci_low": -1},
        {"ci_high": 41},
        {"ci_low": 10, "ci_high": None},
    ],
)
def test_invalid_or_unbound_datum_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        datum(**changes)


def test_chart_datum_retains_exact_count_without_inferred_percent() -> None:
    svg = render_count_chart(datum(ci_low=None, ci_high=None))
    assert b"12" in svg
    assert b"%" not in svg
    assert datum().value == 12


def test_claim_rejects_duplicate_chart_datum_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        EvidenceClaim(
            id="C01", text_public="Synthetic", text_technical="Synthetic",
            type="evidence", sources=["R01"], chart_data=[datum(), datum()],
        )
