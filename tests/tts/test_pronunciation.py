import pytest

from healthvideo.domain.pronunciation import PronunciationLexicon
from healthvideo.tts.pronunciation import apply_pronunciation, pronunciation_hash


def test_literal_longest_complete_occurrence() -> None:
    lexicon = PronunciationLexicon(
        schema_version="1.0", language="vi", version="test-1",
        entries=[
            {"written": "AB", "spoken": "a bê"},
            {"written": "AB CD", "spoken": "a bê xê đê"},
        ],
    )
    source = "AB CD, AB; XAB ABX"
    assert apply_pronunciation(source, lexicon) == "a bê xê đê, a bê; XAB ABX"
    assert source == "AB CD, AB; XAB ABX"
    assert pronunciation_hash(lexicon) != pronunciation_hash(
        lexicon.model_copy(update={"version": "test-2"})
    )


@pytest.mark.parametrize("field", ["version", "written", "spoken"])
def test_rejects_blank_values(field: str) -> None:
    payload = {"schema_version": "1.0", "language": "vi", "version": "test",
               "entries": [{"written": "AB", "spoken": "a bê"}]}
    if field == "version":
        payload["version"] = "  "
    else:
        payload["entries"][0][field] = "  "
    with pytest.raises(ValueError):
        PronunciationLexicon.model_validate(payload)


def test_rejects_duplicate_normalized_written_terms() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        PronunciationLexicon(
            schema_version="1.0", language="vi", version="test",
            entries=[{"written": "AB", "spoken": "a bê"},
                     {"written": " ab ", "spoken": "a bê khác"}],
        )
