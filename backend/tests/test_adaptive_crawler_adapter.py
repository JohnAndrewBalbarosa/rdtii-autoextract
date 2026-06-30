"""AdaptiveCrawlerAdapter: orchestrator-compatible, amortized extraction.

The decisive test is `test_layout_is_learned_once_and_reused...`: it proves the cost
intent — the LLM learns a layout ONCE, then same-layout pages cost zero model calls.
This is what makes the deterministic pipeline ~10-100x cheaper than the per-page-LLM
PipelineAdapter at scale. See memory: two-scrapers-cost-divergence.
"""

from __future__ import annotations

from zetarix.crawling.adaptive_crawler import AdaptiveDomainCrawler, CrawlConfig
from zetarix.crawling.adaptive_crawler_adapter import AdaptiveCrawlerAdapter
from zetarix.domain.document import ParsedDocument
from zetarix.validation.document_validator import DocumentComplianceValidator
from zetarix.orchestration.scraper_orchestrator import ScraperOrchestrator


# Same layout family (identical landmarks/heading levels/main signature), different text.
LAW_A = """<html><body><main class='legal-content'><h1>Data Protection Act</h1>
<p>Personal data transfers require safeguards and documented accountability measures.</p>
</main><footer>All rights reserved</footer></body></html>"""

LAW_B = """<html><body><main class='legal-content'><h1>Privacy Regulation</h1>
<p>Organisations must protect personal data using reasonable security arrangements.</p>
</main><footer>All rights reserved</footer></body></html>"""


class FakeFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    def fetch(self, url: str) -> str:
        return self.pages[url]


class CountingLLM:
    """Counts only layout-learning/revision calls (the per-layout LLM cost)."""

    def __init__(self) -> None:
        self.layout_calls = 0

    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        if agent_profile in {"layout_rule_agent", "rule_revision_agent"}:
            self.layout_calls += 1
        return {
            "rules": [
                {"selector": "footer", "role": "ignore", "reason": "boilerplate"},
                {"selector": "main", "role": "extract_only", "reason": "primary content"},
            ],
            "include_url_patterns": [],
            "exclude_url_patterns": [],
            "confidence": 0.9,
            "warnings": [],
        }


def _adapter(pages: dict[str, str], llm: CountingLLM) -> AdaptiveCrawlerAdapter:
    crawler = AdaptiveDomainCrawler(
        FakeFetcher(pages),
        llm,
        robots_allowed=lambda _url, _agent: True,
        config=CrawlConfig(min_content_chars=20),
    )
    return AdaptiveCrawlerAdapter(crawler)


def test_scrape_url_returns_parsed_document_with_clean_content():
    url = "https://example.gov/a"
    doc = _adapter({url: LAW_A}, CountingLLM()).scrape_url(url)

    assert isinstance(doc, ParsedDocument)
    assert doc.document_url == url
    assert doc.sections
    assert "personal data" in doc.sections[0].text.lower()
    assert "All rights reserved" not in doc.sections[0].text  # footer ignored deterministically


def test_layout_is_learned_once_and_reused_across_same_layout_pages():
    pages = {"https://example.gov/a": LAW_A, "https://example.gov/b": LAW_B}
    llm = CountingLLM()
    adapter = _adapter(pages, llm)

    adapter.scrape_url("https://example.gov/a")
    adapter.scrape_url("https://example.gov/b")

    assert llm.layout_calls == 1  # second same-layout page costs zero model calls


def test_orchestrator_runs_end_to_end_through_the_adapter():
    pages = {"https://example.gov/a": LAW_A, "https://example.gov/b": LAW_B}
    orchestrator = ScraperOrchestrator(
        extractor=_adapter(pages, CountingLLM()),
        validator=DocumentComplianceValidator(),
    )

    docs = orchestrator.scrape_and_validate(list(pages))

    assert len(docs) == 2
    assert all(doc.sections for doc in docs)
