"""Bridge the amortized AdaptiveDomainCrawler to the DocumentExtractorPort.

``ScraperOrchestrator`` depends on ``DocumentExtractorPort.scrape_url`` but the
deterministic, layout-caching ``AdaptiveDomainCrawler`` exposes ``crawl``/``scrape_page``.
This thin adapter holds ONE crawler so its learned-layout cache survives across calls:
the LLM learns a layout once, then every same-layout page is parsed by deterministic
rules with zero model tokens. It replaces the per-page-LLM ``PipelineAdapter`` as the
orchestrator's extractor. See memory: two-scrapers-cost-divergence.
"""

from __future__ import annotations

from adapters.botting.l7_application.adaptive_crawler import (
    AdaptiveDomainCrawler,
    ExtractionError,
)
from core.domain.document import ParsedDocument, RawSection
from core.ports import DocumentExtractorPort


class AdaptiveCrawlerAdapter(DocumentExtractorPort):
    """Single-page extraction over a shared, layout-caching crawler."""

    def __init__(self, crawler: AdaptiveDomainCrawler, *, language: str = "en") -> None:
        self._crawler = crawler
        self._language = language

    def scrape_url(self, url: str) -> ParsedDocument:
        try:
            page = self._crawler.scrape_page(url)
        except ExtractionError as exc:
            return ParsedDocument(
                document_url=url,
                language=self._language,
                sections=(),
                metadata={"extraction_error": exc.reason},
            )

        content = page.get("content", "")
        sections = (
            (RawSection(heading="", level=1, text=content),) if content.strip() else ()
        )
        return ParsedDocument(
            document_url=url,
            language=self._language,
            sections=sections,
            metadata={
                "discovered_links": page.get("discovered_links", []),
                "extraction_method": page.get("extraction_method", ""),
                "layout_id": page.get("layout_id", ""),
            },
        )
