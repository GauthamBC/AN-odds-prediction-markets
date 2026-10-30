"""Read-only TPM v1 API integration. No network requests happen on import.

Official docs: https://thepredictionmarkets.com/api/docs/reference
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import time
import requests

BASE = 'https://api.thepredictionmarkets.com/api/public/v1'

class TPMError(Exception):
    pass

@dataclass
class CatalogueResult:
    events: list[dict]
    pages: int
    complete: bool
    api_calls: int

class TPMClient:
    def __init__(self, key: str, session=None, pause_seconds=0.12):
        if not str(key or '').strip():
            raise TPMError('TPM_API_KEY is missing from Streamlit Secrets.')
        self.session = session or requests.Session()
        self.key = key.strip()
        self.pause_seconds = pause_seconds
        self.calls = 0

    def get(self, endpoint, params=None):
        path = endpoint if endpoint.startswith('/') else '/' + endpoint
        url = BASE + path
        for attempt in range(4):
            try:
                response = self.session.get(url, headers={'X-API-Key': self.key, 'Accept': 'application/json'},
                                            params=params, timeout=(8, 30))
            except requests.RequestException as exc:
                if attempt < 3:
                    time.sleep(min(2**attempt, 5))
                    continue
                raise TPMError(f'Network error contacting TPM: {exc}') from exc
            self.calls += 1
            if response.status_code == 429 and attempt < 3:
                try:
                    delay = float(response.headers.get('Retry-After', '2'))
                except (TypeError, ValueError):
                    delay = 2.0
                time.sleep(max(.5, min(15, delay)))
                continue
            if not response.ok:
                try:
                    info = response.json().get('error', {})
                    message = info.get('message', response.text[:300])
                except ValueError:
                    message = response.text[:300]
                raise TPMError(f'TPM HTTP {response.status_code}: {message}')
            try:
                return response.json()
            except ValueError as exc:
                raise TPMError('TPM returned invalid JSON.') from exc
        raise TPMError('TPM rate limit: all retries exhausted.')

    def catalogue(self, *, on_page: Callable | None = None, max_pages=1000):
        """Fetch EVERY page. If an API error or page cap occurs, caller must not publish a partial snapshot."""
        events, cursor, seen = [], None, set()
        page = 0
        while True:
            if page >= max_pages:
                raise TPMError(f'Safety limit of {max_pages} pages reached; old snapshot preserved.')
            params = {'status':'trading','limit':200,'sort':'trending','order':'desc'}
            if cursor:
                params['cursor'] = cursor
            result = self.get('/events', params)
            items = result.get('data')
            if not isinstance(items, list):
                raise TPMError('Unexpected /events format (missing data array).')
            for row in items:
                if not isinstance(row, dict) or not row.get('slug'):
                    continue
                if row.get('status') not in (None, 'active', 'trading'):
                    continue
                slug = str(row['slug'])
                if slug not in seen:
                    seen.add(slug)
                    events.append(row)
            page += 1
            if on_page:
                on_page(page, len(events))
            pg = result.get('pagination') or {}
            if not pg.get('has_more'):
                return CatalogueResult(events=events, pages=page, complete=True, api_calls=self.calls)
            nxt = pg.get('next_cursor')
            if not nxt or nxt == cursor:
                raise TPMError('Pagination cursor missing or repeated; old snapshot preserved.')
            cursor = nxt
            if self.pause_seconds:
                time.sleep(self.pause_seconds)

    def detail(self, slug: str, *, max_outcomes: int | None = None):
        import re
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,200}', str(slug)):
            raise TPMError('Invalid event slug.')
        params = {'max_outcomes':max_outcomes} if max_outcomes else None
        data = self.get(f'/events/{slug}', params).get('data')
        if not isinstance(data, dict) or not data.get('markets'):
            raise TPMError('Event details unavailable.')
        return data

    def quota(self):
        return self.get('/rate-limit')
