"""Integration tests for run._crawl_one: legislative gating + dynamic retry (offline)."""

from __future__ import annotations

import logging

import run
from adapters.botting.l4_transport.fetch_result import FetchResult

_LOG = logging.getLogger("test.crawl")

_LANDING = (
    "<html><body><main><h1>Data Protection Department</h1>"
    "<p>Announcements. Job vacancy advertisement. Contact us for tenders and news.</p>"
    "</main></body></html>"
)
_STATUTE = (
    "<html><body><main>"
    "<h2 id='s26'>Section 26 Transfer</h2>"
    "<p>An organisation shall not transfer any personal data to a country or territory "
    "outside the country except in accordance with this Act. The Act creates offences.</p>"
    "<h2 id='s13'>Section 13 Consent</h2>"
    "<p>Consent is required before processing; subsection (2) prescribes exceptions.</p>"
    "</main></body></html>"
)


class _StaticOnly:
    def __init__(self, html: str) -> None:
        self._html = html

    def fetch_raw(self, url: str) -> FetchResult:
        return FetchResult(url=url, status=200, content_type="text/html; charset=utf-8",
                           body=self._html.encode("utf-8"))


class _StaticPlusDynamic(_StaticOnly):
    def __init__(self, static_html: str, dynamic_html: str) -> None:
        super().__init__(static_html)
        self._dyn = dynamic_html

    def fetch_raw_dynamic(self, url: str) -> FetchResult:
        return FetchResult(url=url, status=200, content_type="text/html; charset=utf-8",
                           body=self._dyn.encode("utf-8"))


_URL = "https://example.gov/page"  # matches no scaffold → neutral path


def test_non_legislative_html_is_skipped():
    doc = run._crawl_one(_URL, "Australia", _StaticOnly(_LANDING), _LOG)
    assert doc is None  # landing/news page gated out


def test_dynamic_retry_recovers_statute():
    fetcher = _StaticPlusDynamic(_LANDING, _STATUTE)
    doc = run._crawl_one(_URL, "Australia", fetcher, _LOG)
    assert doc is not None
    assert "transfer" in doc.text.lower()
    assert any(s.anchor == "s26" for s in doc.sections)


def test_legislative_static_kept_without_dynamic():
    doc = run._crawl_one(_URL, "Singapore", _StaticOnly(_STATUTE), _LOG)
    assert doc is not None
    assert doc.is_pdf is False
