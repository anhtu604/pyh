"""Elsevier official API client: never touches the network, disk or logs with the key."""

import io
import json
import logging
import urllib.error
from types import SimpleNamespace

import pytest

from healthvideo.evidence.elsevier import ElsevierClient

KEY = 'sk-test-elsevier-0123456789'
TOKEN = 'inst-test-token-987'

SEARCH_BODY = {
    'search-results': {
        'entry': [
            {
                'dc:title': 'Urate-lowering therapy and gout flares',
                'prism:doi': '10.1016/j.example.2020.01.001',
                'prism:coverDate': '2020-03-01',
                'prism:publicationName': 'Example Journal',
                'citedby-count': '42',
                'eid': '2-s2.0-000000001',
            },
        ],
    },
}


class FakeHttp:
    """Stands in for the urllib package: records requests, answers from a queue."""

    def __init__(self, *responses):
        self.requests = []
        self.responses = list(responses)
        self.request = SimpleNamespace(urlopen=self._urlopen)

    def _urlopen(self, req, timeout=None):
        self.requests.append(req)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        body = response if isinstance(response, bytes) else json.dumps(response).encode()
        return io.BytesIO(body)


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        'https://api.elsevier.com/content/search/scopus', code, 'error', {}, io.BytesIO(b'{}'),
    )


def test_search_sends_key_header_never_logs_it(monkeypatch, caplog):
    monkeypatch.setenv('ELSEVIER_API_KEY', KEY)
    monkeypatch.setenv('ELSEVIER_INSTTOKEN', TOKEN)
    caplog.set_level(logging.DEBUG)
    http = FakeHttp(SEARCH_BODY)
    client = ElsevierClient(http=http)

    rows = client.search('gout AND urate', count=5)

    assert rows == [{
        'title': 'Urate-lowering therapy and gout flares',
        'doi': '10.1016/j.example.2020.01.001',
        'year': 2020,
        'journal': 'Example Journal',
        'cited_by': 42,
        'eid': '2-s2.0-000000001',
    }]
    req = http.requests[0]
    assert req.get_header('X-els-apikey') == KEY
    assert req.get_header('X-els-insttoken') == TOKEN
    assert req.full_url.startswith('https://api.elsevier.com/content/search/scopus?')
    assert KEY not in req.full_url and TOKEN not in req.full_url
    assert 'count=5' in req.full_url
    assert KEY not in caplog.text and TOKEN not in caplog.text
    assert KEY not in repr(client) and TOKEN not in repr(client)


def test_missing_key_unavailable(monkeypatch):
    monkeypatch.delenv('ELSEVIER_API_KEY', raising=False)
    monkeypatch.delenv('ELSEVIER_INSTTOKEN', raising=False)
    http = FakeHttp()
    client = ElsevierClient(http=http)

    assert client.available() is False
    with pytest.raises(ValueError, match='ELSEVIER_API_KEY'):
        client.search('gout')
    assert http.requests == []


def test_rate_limit_raises_vietnamese_error():
    client = ElsevierClient(KEY, http=FakeHttp(_http_error(429)))

    with pytest.raises(ValueError, match='quá giới hạn') as caught:
        client.search('gout')
    assert KEY not in str(caught.value)


@pytest.mark.parametrize('code', [401, 403])
def test_auth_errors_raise_vietnamese_error_without_key(code):
    client = ElsevierClient(KEY, http=FakeHttp(_http_error(code)))

    with pytest.raises(ValueError, match='Elsevier từ chối') as caught:
        client.abstract('10.1016/j.example.2020.01.001')
    assert KEY not in str(caught.value)


def test_abstract_reads_core_data():
    body = {'abstracts-retrieval-response': {'coredata': {
        'dc:title': 'Urate-lowering therapy and gout flares',
        'dc:description': 'Background: short synthetic abstract.',
        'prism:doi': '10.1016/j.example.2020.01.001',
    }}}
    http = FakeHttp(body)
    client = ElsevierClient(KEY, http=http)

    assert client.abstract('https://doi.org/10.1016/j.example.2020.01.001') == {
        'title': 'Urate-lowering therapy and gout flares',
        'abstract': 'Background: short synthetic abstract.',
        'doi': '10.1016/j.example.2020.01.001',
    }
    assert http.requests[0].full_url.startswith(
        'https://api.elsevier.com/content/abstract/doi/10.1016/j.example.2020.01.001')


def test_article_text_not_written_to_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    http = FakeHttp(b'Synthetic full text body, kept in memory only.')
    client = ElsevierClient(KEY, http=http)

    text = client.article_text('10.1016/j.example.2020.01.001')

    assert text == 'Synthetic full text body, kept in memory only.'
    assert http.requests[0].full_url.startswith(
        'https://api.elsevier.com/content/article/doi/10.1016/j.example.2020.01.001')
    assert list(tmp_path.rglob('*')) == []


def test_empty_search_result_is_empty_list():
    body = {'search-results': {'entry': [{'@_fa': 'true', 'error': 'Result set was empty'}]}}
    assert ElsevierClient(KEY, http=FakeHttp(body)).search('nothing') == []


def test_cli_search_without_key_explains(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from healthvideo.cli import app

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ELSEVIER_API_KEY', raising=False)
    monkeypatch.delenv('ELSEVIER_INSTTOKEN', raising=False)

    result = CliRunner().invoke(app, ['evidence', 'elsevier-search', 'gout'])

    assert result.exit_code == 1
    assert 'ELSEVIER_API_KEY' in result.output


def test_cli_search_prints_json(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from healthvideo import cli
    from healthvideo.evidence import elsevier

    monkeypatch.chdir(tmp_path)
    http = FakeHttp(SEARCH_BODY)
    monkeypatch.setattr(elsevier, 'ElsevierClient',
                        lambda: ElsevierClient(KEY, http=http))

    result = CliRunner().invoke(cli.app, ['evidence', 'elsevier-search', 'gout', '--count', '3'])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]['doi'] == '10.1016/j.example.2020.01.001'
    assert KEY not in result.output
