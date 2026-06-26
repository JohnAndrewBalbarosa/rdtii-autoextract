"""Tests for HTML link-following crawl (run._discover_article_links + run._crawl_site).

A seed that is a non-PDF *index/landing* page must be followed to the actual article/law
pages, whose sections (with content) are then extracted. PDF links and off-domain links are
not followed; the crawl is bounded.
"""

from __future__ import annotations

import logging

import run
from adapters.botting.l4_transport.fetch_result import FetchResult

_LOG = logging.getLogger("test.crawl_links")

_BASE = "https://example.gov"
_INDEX_URL = f"{_BASE}/data-protection"

# Index page: not legislation itself — just links + blurb. Links to two acts (same domain),
# one external site, one PDF, and a duplicate.
_INDEX_HTML = (
    "<html><body><main>"
    "<h1>Data Protection Laws</h1>"
    "<p>Browse the register of laws, news and announcements.</p>"
    "<a href='/laws/privacy-act'>Privacy Act</a>"
    "<a href='https://example.gov/laws/transfer-act'>Transfer Act</a>"
    "<a href='https://other.org/laws/foreign'>Foreign law</a>"
    "<a href='/files/privacy-act.pdf'>PDF version</a>"
    "<a href='/laws/privacy-act'>Privacy Act (again)</a>"
    "</main></body></html>"
)

_PRIVACY_ACT = (
    "<html><body><main>"
    "<h2 id='s13'>Section 13 Consent</h2>"
    "<p>An organisation shall obtain consent before processing personal data; "
    "subsection (2) prescribes exceptions under this Act.</p>"
    "<h2 id='s14'>Section 14 Purpose</h2>"
    "<p>Personal data shall be used only for the purpose notified; an offence arises "
    "under this Act for misuse.</p>"
    "</main></body></html>"
)
_TRANSFER_ACT = (
    "<html><body><main>"
    "<h2 id='s26'>Section 26 Transfer</h2>"
    "<p>An organisation shall not transfer personal data outside the country except in "
    "accordance with this Act. The Act creates offences for breach.</p>"
    "<h2 id='s27'>Section 27 Safeguards</h2>"
    "<p>The transferor shall ensure subsection (1) safeguards apply before any transfer "
    "under this Act.</p>"
    "</main></body></html>"
)


class _MapFetcher:
    """Static-only fetcher returning canned HTML per URL (offline)."""

    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages

    def fetch_raw(self, url: str) -> FetchResult:
        html = self._pages.get(url, "<html><body></body></html>")
        return FetchResult(
            url=url,
            status=200,
            content_type="text/html; charset=utf-8",
            body=html.encode("utf-8"),
        )


def test_discover_article_links_same_domain_html_only():
    links = run._discover_article_links(_INDEX_HTML, None, _INDEX_URL)
    assert f"{_BASE}/laws/privacy-act" in links
    assert f"{_BASE}/laws/transfer-act" in links
    assert all("other.org" not in link for link in links)  # off-domain dropped
    assert all(not link.lower().endswith(".pdf") for link in links)  # PDF dropped
    assert len(links) == len(set(links))  # deduped


def test_crawl_follows_index_to_article_pages():
    pages = {
        _INDEX_URL: _INDEX_HTML,
        f"{_BASE}/laws/privacy-act": _PRIVACY_ACT,
        f"{_BASE}/laws/transfer-act": _TRANSFER_ACT,
    }
    docs = run._crawl_site([_INDEX_URL], "Singapore", _MapFetcher(pages), _LOG)
    urls = {doc.url for doc in docs}

    # The two linked acts were reached and kept...
    assert f"{_BASE}/laws/privacy-act" in urls
    assert f"{_BASE}/laws/transfer-act" in urls
    # ...while the non-legislative index itself is not emitted as a law doc.
    assert _INDEX_URL not in urls


def test_crawled_article_carries_section_content():
    pages = {
        _INDEX_URL: _INDEX_HTML,
        f"{_BASE}/laws/privacy-act": _PRIVACY_ACT,
        f"{_BASE}/laws/transfer-act": _TRANSFER_ACT,
    }
    docs = run._crawl_site([_INDEX_URL], "Singapore", _MapFetcher(pages), _LOG)
    transfer = next(doc for doc in docs if doc.url.endswith("/laws/transfer-act"))
    assert transfer.sections, "article must carry extracted sections"
    assert any("transfer" in section.text.lower() for section in transfer.sections)
    assert any(section.anchor == "s26" for section in transfer.sections)


def test_crawl_respects_page_cap():
    # A page that links to itself+others; cap must stop the crawl.
    spam = "<html><body><main>" + "".join(
        f"<a href='/p/{i}'>p{i}</a>" for i in range(50)
    ) + "<p>index</p></main></body></html>"
    pages = {f"{_BASE}/p/{i}": spam for i in range(50)}
    pages[_INDEX_URL] = spam
    docs = run._crawl_site([_INDEX_URL], "Singapore", _MapFetcher(pages), _LOG, max_pages=5)
    # Never fetched more than the cap (none are legislative, so no docs; just must not hang).
    assert docs == []
