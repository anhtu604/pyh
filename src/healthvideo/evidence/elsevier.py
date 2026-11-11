"""Elsevier official APIs (Scopus Search, Abstract Retrieval, ScienceDirect Article Retrieval).

This is the only sanctioned route to Elsevier content (spec 2026-11-08 §5.8); automated
scraping stays forbidden (``clients.check_scopus_policy``). The API key travels only in request
headers: it is never put in URLs, messages, logs or prompts. Full text is returned in memory
and never written to disk (CLAUDE.md rule 3).
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from types import ModuleType
from typing import Any

logger = logging.getLogger(__name__)

BASE_URL = 'https://api.elsevier.com/content'
TIMEOUT_SECONDS = 20
NO_KEY = 'Chưa có ELSEVIER_API_KEY trong .env; chuyên gia dùng PubMed/PMC như hiện tại.'
_HTTP_ERRORS = {
    401: 'Elsevier từ chối khoá API (401): kiểm tra ELSEVIER_API_KEY trong .env.',
    403: 'Elsevier từ chối quyền truy cập (403): khoá hoặc mạng cơ quan chưa được cấp quyền '
         'cho tài liệu này (thử ELSEVIER_INSTTOKEN hoặc mạng của trường).',
    429: 'Elsevier báo quá giới hạn lượt gọi (429): đợi rồi thử lại, giảm số truy vấn.',
}


def _clean_doi(doi: str) -> str:
    clean = doi.strip()
    for prefix in ('https://doi.org/', 'http://doi.org/', 'https://dx.doi.org/',
                   'http://dx.doi.org/', 'doi:'):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):]
    if not clean.startswith('10.'):
        raise ValueError(f'DOI không hợp lệ: {doi!r}')
    return clean


def _year(cover_date: Any) -> int | None:
    match = re.match(r'(\d{4})', str(cover_date or ''))
    return int(match.group(1)) if match else None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class ElsevierClient:
    """Thin client for the Elsevier APIs; ``http`` is the urllib package or a test fake."""

    def __init__(
        self,
        api_key: str | None = None,
        insttoken: str | None = None,
        *,
        http: ModuleType | Any = urllib,
    ) -> None:
        self._api_key = (api_key if api_key is not None
                         else os.environ.get('ELSEVIER_API_KEY', '')).strip() or None
        self._insttoken = (insttoken if insttoken is not None
                           else os.environ.get('ELSEVIER_INSTTOKEN', '')).strip() or None
        self._http = http

    def __repr__(self) -> str:
        return f'ElsevierClient(available={self.available()}, insttoken={self._insttoken is not None})'

    def available(self) -> bool:
        return self._api_key is not None

    def _get(self, path: str, params: dict[str, str], accept: str) -> bytes:
        if not self._api_key:
            raise ValueError(NO_KEY)
        query = f'?{urllib.parse.urlencode(params)}' if params else ''
        headers = {'X-ELS-APIKey': self._api_key, 'Accept': accept}
        if self._insttoken:
            headers['X-ELS-Insttoken'] = self._insttoken
        request = urllib.request.Request(f'{BASE_URL}{path}{query}', headers=headers)
        logger.debug('Elsevier GET %s', path)
        try:
            with self._http.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            message = _HTTP_ERRORS.get(exc.code, f'Elsevier trả lỗi HTTP {exc.code}.')
            raise ValueError(message) from None
        except urllib.error.URLError as exc:
            raise ValueError(f'Không kết nối được Elsevier: {exc.reason}') from None

    def _json(self, path: str, params: dict[str, str]) -> dict:
        raw = self._get(path, params, 'application/json')
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError('Elsevier trả về dữ liệu không phải JSON.') from None
        if not isinstance(data, dict):
            raise ValueError('Elsevier trả về JSON không đúng dạng.')  # noqa: TRY004 — callers catch ValueError
        return data

    def search(self, query: str, count: int = 25) -> list[dict]:
        """Scopus Search: metadata only (title, doi, year, journal, cited_by, eid)."""
        if not query.strip():
            raise ValueError('Cần truy vấn tìm kiếm.')
        count = max(1, min(int(count), 25))
        data = self._json('/search/scopus', {'query': query, 'count': str(count)})
        entries = (data.get('search-results') or {}).get('entry') or []
        rows = []
        for entry in entries:
            if not isinstance(entry, dict) or 'error' in entry:
                continue  # Scopus reports an empty result as a single error entry
            rows.append({
                'title': entry.get('dc:title', ''),
                'doi': entry.get('prism:doi'),
                'year': _year(entry.get('prism:coverDate')),
                'journal': entry.get('prism:publicationName', ''),
                'cited_by': _int(entry.get('citedby-count')),
                'eid': entry.get('eid'),
            })
        return rows

    def abstract(self, doi: str) -> dict:
        """Abstract Retrieval by DOI: title, abstract, doi."""
        clean = _clean_doi(doi)
        data = self._json(f'/abstract/doi/{urllib.parse.quote(clean, safe="/")}', {})
        core = (data.get('abstracts-retrieval-response') or {}).get('coredata') or {}
        abstract = core.get('dc:description') or ''
        if not isinstance(abstract, str):
            abstract = json.dumps(abstract, ensure_ascii=False)
        return {
            'title': core.get('dc:title', ''),
            'abstract': abstract.strip(),
            'doi': core.get('prism:doi') or clean,
        }

    def article_text(self, doi: str) -> str:
        """ScienceDirect full text as plain text, in memory only; callers must not save it."""
        clean = _clean_doi(doi)
        raw = self._get(f'/article/doi/{urllib.parse.quote(clean, safe="/")}', {}, 'text/plain')
        return raw.decode('utf-8', errors='replace')
