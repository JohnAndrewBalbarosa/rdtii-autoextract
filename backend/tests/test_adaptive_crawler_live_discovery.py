from __future__ import annotations

from zetarix.crawling.adaptive_crawler import AdaptiveDomainCrawler, CrawlConfig
from zetarix.transport.fetch_result import FetchResult


HOME = """
<html><body><nav>
  <a href="/laws">Laws and regulations</a>
  <a href="/news">News</a>
  <a href="/contact-us">Contact Us</a>
  <a href="/privacy-statement">Privacy Statement</a>
</nav>
<main>
  <h1>Ministry of Digital Affairs</h1>
  <a href="/docs/privacy-act.pdf">Privacy Act PDF</a>
  <a href="/docs/privacy-act.pdf?utm_source=portal">Privacy Act PDF duplicate</a>
</main>
</body></html>
"""

LAWS = """
<html><head>
  <meta property="og:title" content="Data Protection Laws" />
  <meta name="publication_date" content="2024-01-05" />
</head><body>
<main>
  <h1>Data Protection Laws</h1>
  <p>Official statutes and regulations.</p>
  <a href="/docs/privacy-act.pdf">Download Act</a>
  <a href="/laws/section-2">Section 2</a>
</main>
</body></html>
"""

SECTION = """
<html><body><main>
  <h1>Section 2</h1>
  <p>Personal data protection duties apply.</p>
</main></body></html>
"""

PDF_BYTES = b"%PDF-1.4 fake pdf bytes"
NOISE = """
<html><body><main><h1>Contact Us</h1><p>Phone and email details.</p></main></body></html>
"""


class FakeFetcher:
    pages = {
        "https://example.gov/": FetchResult(
            url="https://example.gov/",
            status=200,
            content_type="text/html; charset=utf-8",
            body=HOME.encode("utf-8"),
        ),
        "https://example.gov/laws": FetchResult(
            url="https://example.gov/laws",
            status=200,
            content_type="text/html; charset=utf-8",
            body=LAWS.encode("utf-8"),
        ),
        "https://example.gov/laws/section-2": FetchResult(
            url="https://example.gov/laws/section-2",
            status=200,
            content_type="text/html; charset=utf-8",
            body=SECTION.encode("utf-8"),
        ),
        "https://example.gov/docs/privacy-act.pdf": FetchResult(
            url="https://example.gov/docs/privacy-act.pdf",
            status=200,
            content_type="application/pdf",
            body=PDF_BYTES,
        ),
        "https://example.gov/contact-us": FetchResult(
            url="https://example.gov/contact-us",
            status=200,
            content_type="text/html; charset=utf-8",
            body=NOISE.encode("utf-8"),
        ),
        "https://example.gov/privacy-statement": FetchResult(
            url="https://example.gov/privacy-statement",
            status=200,
            content_type="text/html; charset=utf-8",
            body=NOISE.encode("utf-8"),
        ),
    }

    def fetch_raw(self, url: str) -> FetchResult:
        return self.pages[url]


class RaisingLLM:
    def complete(self, *args, **kwargs):
        raise RuntimeError("llm unavailable")


class StubPdfParser:
    def extract_text(self, pdf_bytes: bytes) -> str:
        assert pdf_bytes == PDF_BYTES
        return "Privacy Act 2024\nSection 1. A person must protect personal data."


def _crawler() -> AdaptiveDomainCrawler:
    return AdaptiveDomainCrawler(
        FakeFetcher(),
        RaisingLLM(),
        pdf_parser=StubPdfParser(),
        robots_allowed=lambda _url, _agent: True,
        config=CrawlConfig(max_depth=2, max_pages=6, min_content_chars=20),
    )


def test_crawler_discovers_real_sources_without_llm():
    result = _crawler().crawl("https://example.gov/")

    assert "https://example.gov/laws" in result["visited_urls"]
    assert "https://example.gov/docs/privacy-act.pdf" in result["visited_urls"]
    assert result["summary"]["document_source_count"] >= 1
    assert result["summary"]["discovered_source_count"] >= 3


def test_crawler_records_metadata_and_provenance():
    result = _crawler().crawl("https://example.gov/")

    by_url = {item["normalized_url"]: item for item in result["discovered_sources"]}
    law = by_url["https://example.gov/laws"]
    pdf = by_url["https://example.gov/docs/privacy-act.pdf"]

    assert law["title"] == "Data Protection Laws"
    assert law["publication_date"] == "2024-01-05"
    assert law["status"] == "fetched"
    assert pdf["document_type"] == "pdf"
    assert "https://example.gov/" in pdf["source_pages"] or "https://example.gov/laws" in pdf["source_pages"]


def test_crawler_result_structure_includes_fetches_and_pages():
    result = _crawler().crawl("https://example.gov/")

    assert result["successful_fetches"]
    assert result["extracted_pages"]
    page = result["extracted_pages"][0]
    assert "http_status" in page
    assert "content_type" in page
    assert "checksum" in page
    assert "crawl_depth" in page


def test_crawler_rejects_contact_and_privacy_statement_links():
    result = _crawler().crawl("https://example.gov/")

    discovered = {item["normalized_url"] for item in result["discovered_sources"]}
    visited = set(result["visited_urls"])

    assert "https://example.gov/contact-us" not in discovered
    assert "https://example.gov/privacy-statement" not in discovered
    assert "https://example.gov/contact-us" not in visited
    assert "https://example.gov/privacy-statement" not in visited
