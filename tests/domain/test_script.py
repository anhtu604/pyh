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


def test_delivery_must_match_text_without_tags() -> None:
    line = ScriptLine(id="L1", text="Gout, thật sao?", delivery="[curious] Gout , thật sao ?")
    assert line.tts_text() == "[curious] Gout , thật sao ?"
    assert line.tts_text(expressive=False) == "Gout , thật sao ?"
    with pytest.raises(ValidationError, match="delivery must match text"):
        ScriptLine(id="L1", text="Gout không phải vậy.", delivery="[sarcastic] Gout phải vậy.")


@pytest.mark.parametrize("delivery", ["[invented] Xin chào.", "[curious Xin chào."])
def test_delivery_rejects_unknown_or_unclosed_tags(delivery: str) -> None:
    with pytest.raises(ValidationError, match="tag"):
        ScriptLine(id="L1", text="Xin chào.", delivery=delivery)


def test_delivery_is_optional_and_preserves_legacy_metadata() -> None:
    plain = ScriptLine(id="L1", text="Xin chào.")
    assert plain.tts_text() == plain.text
    assert plain.delivery_beats() == ()
    legacy = ScriptLine(id="L2", text="Xin chào.", delivery=Delivery(intent="intro"))
    assert legacy.tts_text() == legacy.text
    assert legacy.delivery_beats() == (legacy.delivery.model_dump(mode="json"),)


def test_delivery_normalization_never_removes_words_or_diacritics() -> None:
    for changed in ("Gout hết?", "Gout không hêt?", "gout không hết?"):
        with pytest.raises(ValidationError):
            ScriptLine(id="L1", text="Gout không hết?", delivery=f"[curious] {changed}")


def test_delivery_allowed_tags_come_from_voice_profile(tmp_path, monkeypatch) -> None:
    from healthvideo.domain import script

    profile = tmp_path / "voice.yaml"
    profile.write_text("allowed_tags: [whispers]\n", encoding="utf-8")
    monkeypatch.setattr(script, "VOICE_PROFILE_PATH", profile)
    ScriptLine(id="L1", text="Xin chào.", delivery="[whispers] Xin chào.")
    with pytest.raises(ValidationError, match="not allowed"):
        ScriptLine(id="L1", text="Xin chào.", delivery="[sarcastic] Xin chào.")


@pytest.mark.parametrize(("text", "changed"), [
    ("Uống 1,5 mg.", "Uống 1 5 mg."),
    ("Uống 1-2 mg.", "Uống 1 2 mg."),
    ("Mức -5%.", "Mức 5%."),
    ("Mức 5%.", "Mức 5."),
    ("Uống 1,5 mg.", "Uống 1.5 mg."),
])
def test_delivery_preserves_numeric_punctuation(text: str, changed: str) -> None:
    with pytest.raises(ValidationError, match="delivery must match text"):
        ScriptLine(id="L1", text=text, delivery=f"[curious] {changed}")


@pytest.mark.parametrize("tag", ["Curious", " curious "])
def test_delivery_tags_match_provider_exactly(tag: str) -> None:
    with pytest.raises(ValidationError, match="not allowed"):
        ScriptLine(id="L1", text="Xin chào.", delivery=f"[{tag}] Xin chào.")
