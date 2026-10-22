import json
from urllib.parse import parse_qs, urlparse

import pytest

from healthvideo.evidence.clients import PubMedClient


def test_count_uses_total_matches_without_downloading_ids():
    def transport(request):
        params = parse_qs(urlparse(request.full_url).query)
        assert params["term"] == ["salt blood pressure"]
        assert params["retmax"] == ["0"]
        assert params["api_key"] == ["fake-key"]
        return json.dumps({"esearchresult": {"count": "12345", "idlist": []}}).encode()
    assert PubMedClient(transport=transport, api_key="fake-key").count("salt blood pressure") == 12345


@pytest.mark.parametrize("payload", [{}, {"esearchresult": {"count": "bad"}}, {"esearchresult": {"count": -1}}])
def test_count_rejects_missing_or_invalid_count(payload):
    client = PubMedClient(transport=lambda request: json.dumps(payload).encode())
    with pytest.raises((ValueError, KeyError)):
        client.count("salt")
