import io
import json
import re
from urllib.parse import parse_qs, urlsplit

from tools.voice.list_voices import list_voices
from tools.voice.sample import sample_delivery


def test_voice_listing_filters_both_sources_and_paginates():
    paths = []

    def opener(request, **kwargs):
        url = urlsplit(request.full_url)
        query = parse_qs(url.query)
        paths.append(url.path)
        assert query["language"] == ["vi"]
        more = url.path == "/v2/voices" and "next_page_token" not in query
        response = {"voices": [{"voice_id": f"voice-{len(paths)}", "name": "Vietnamese",
                                "verified_languages": [{"language": "vi"}]}],
                    "has_more": more, "next_page_token": "next"}
        return io.BytesIO(json.dumps(response).encode())

    assert len(list_voices("key", opener=opener)) == 3
    assert paths == ["/v2/voices", "/v2/voices", "/v1/shared-voices"]


def test_voice_listing_excludes_english_and_unlabelled_account_voices():
    def opener(request, **kwargs):
        account = urlsplit(request.full_url).path == "/v2/voices"
        voices = [
            {"voice_id": "verified-vi", "verified_languages": [{"language": "vi"}]},
            {"voice_id": "labelled-vi", "labels": {"language": "Vietnamese"}},
            {"voice_id": "english", "labels": {"language": "en"}},
            {"voice_id": "verified-en", "verified_languages": [{"language": "en"}]},
            {"voice_id": "unknown-account"},
        ] if account else [
            {"voice_id": "shared-vi", "language": "vi"},
            {"voice_id": "shared-en", "language": "en"},
            {"voice_id": "filtered-shared-without-metadata"},
        ]
        return io.BytesIO(json.dumps({"voices": voices, "has_more": False}).encode())

    ids = {voice["voice_id"] for voice in list_voices("key", opener=opener)}
    assert ids == {"verified-vi", "labelled-vi", "shared-vi", "filtered-shared-without-metadata"}


def test_voice_samples_preserve_approved_text():
    for index, text in enumerate([
        "Khoan mở phiên tòa xét thực đơn.",
        "Cơn gout có thể rất đau.",
        "Hãy nhìn các chấm.",
        "Đừng đếm chấm để suy ra kết quả xét nghiệm.",
    ]):
        delivery = sample_delivery(text, index)
        assert " ".join(re.sub(r"\[[^]]+\]", "", delivery).split()) == text
