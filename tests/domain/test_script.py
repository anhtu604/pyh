import pytest
from pydantic import ValidationError

from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.script import Delivery, Script, ScriptLine


def test_script_keeps_spoken_delivery_metadata_and_vietnamese_defaults() -> None:
    script = Script(
        title="Muối và huyết áp",
        lines=[
            ScriptLine(
                id="L01",
                text="Giảm muối có thể giúp hạ huyết áp.",
                claim_id="C01",
                source_marker="[1]",
                delivery=Delivery(intent="evidence", pause_after_ms=400),
            )
        ],
    )

    assert script.language == "vi"
    assert script.lines[0].delivery.pace == "normal"
    assert script.lines[0].delivery.pause_after_ms == 400


def test_evidence_claim_accepts_only_declared_claim_types() -> None:
    claim = EvidenceClaim(
        id="C01",
        text_public="Giảm muối giúp hạ huyết áp",
        text_technical="Reduced sodium lowers blood pressure",
        type="evidence",
        sources=["R01"],
    )

    assert claim.schema_version == "1.0"
    assert SourceRecord(id="R01", title="Synthetic record").schema_version == "1.0"
    with pytest.raises(ValidationError):
        EvidenceClaim(
            id="C02",
            text_public="Không hợp lệ",
            text_technical="Invalid",
            type="fact",
            sources=["R01"],
        )
