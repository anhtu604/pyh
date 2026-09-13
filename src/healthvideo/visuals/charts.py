"""Static count chart SVG from an explicit evidence-ledger datum."""

from html import escape

from healthvideo.domain.evidence import ChartDatum


def render_count_chart(datum: ChartDatum) -> bytes:
    """Show exact recorded values; geometry alone is quantized to SVG pixels."""
    width = round(760 * datum.value / datum.denominator)
    ci = (
        f'<text x="90" y="570">CI {datum.ci_low}–{datum.ci_high} '
        f"{escape(datum.unit)}</text>"
        if datum.ci_low is not None
        else ""
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 800" role="img">'
        f"<title>{escape(datum.label)}</title>"
        '<rect width="1080" height="800" fill="#fffdf7"/>'
        f'<text x="90" y="145">{escape(datum.label)}</text>'
        f'<text x="90" y="240">{datum.value} {escape(datum.unit)}; N={datum.denominator}</text>'
        '<rect x="90" y="320" width="760" height="100" fill="#e7e7e7"/>'
        f'<rect x="90" y="320" width="{width}" height="100" fill="#202124"/>'
        f'<text x="90" y="490">Trục 0–{datum.denominator} {escape(datum.unit)}</text>'
        f"{ci}</svg>\n"
    )
    return svg.encode("utf-8")
