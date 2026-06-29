from typing import Any, Optional

from core.ports import LLMProvider, DocumentExtractorPort, HtmlFetcherPort
from core.domain.document import ParsedDocument, RawSection
from adapters.llm.prompt_contracts import (
    MARKDOWN_EXTRACTION_SCHEMA,
    STRUCTURED_SECTIONS_SCHEMA,
    build_markdown_extraction_prompt,
    build_structured_sections_prompt,
)
from adapters.botting.l4_transport.fetch_result import FetchResult
from adapters.botting.l4_transport.pdf_parser import PdfParser
from adapters.botting.l6_presentation.dom_cleaner import DomCleaner
from adapters.botting.scaffolds.scaffold_registry import ScaffoldRegistry


class PipelineAdapter(DocumentExtractorPort):
    """OSI Layer 7 (Application): Task-Specific Pipeline coordinating L4, L6, Scaffolds, and AI."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        fetcher: HtmlFetcherPort,
        cleaner: DomCleaner,
        scaffold_registry: Optional[ScaffoldRegistry] = None,
        pdf_parser: Optional[PdfParser] = None,
    ):
        self._llm = llm_provider
        self._fetcher = fetcher
        self._cleaner = cleaner
        self._scaffold_registry = scaffold_registry
        # PdfParser is optional; created on demand if not injected
        self._pdf_parser = pdf_parser or PdfParser()

    def scrape_url(self, url: str) -> ParsedDocument:
        # Check for site-specific scaffold
        scaffold = self._scaffold_registry.get_scaffold_for_url(url) if self._scaffold_registry else None
        custom_selectors = scaffold.get_custom_selectors() if scaffold else {}
        keywords = scaffold.get_keywords() if scaffold else []

        # Step 1: L4 Transport (Fetch) — use fetch_raw if available for binary-safe routing
        if hasattr(self._fetcher, "fetch_raw"):
            result: FetchResult = self._fetcher.fetch_raw(url)
            is_pdf = result.is_pdf
        else:
            # Fallback for fetchers that only implement HtmlFetcherPort.fetch()
            raw_html = self._fetcher.fetch(url)
            is_pdf = url.lower().endswith(".pdf")
            result = None  # type: ignore[assignment]

        # Step 2: Route by content type — PDF → PdfParser, HTML → DomCleaner
        if is_pdf:
            pdf_bytes = result.body if result is not None else self._pdf_parser.download_pdf(url)
            cleaned_text = self._pdf_parser.extract_text(pdf_bytes)
            discovered_links: list[str] = []
        else:
            raw_html = result.text if result is not None else raw_html  # type: ignore[assignment]
            cleaned_text = self._cleaner.clean_html(raw_html, custom_selectors)
            discovered_links = self._cleaner.discover_links(raw_html, custom_selectors)

        # Step 3: The Extraction Sub-Agent (Small Model)
        extracted_markdown = self._extract_markdown_with_llm(cleaned_text)

        # Step 4: The Structuring Sub-Agent (Small Model)
        structured_data = self._structure_json_with_llm(extracted_markdown)

        # Map to domain entities
        sections = []
        for section in structured_data.get("sections", []):
            sections.append(
                RawSection(
                    heading=section.get("heading", ""),
                    level=section.get("level", 1),
                    text=section.get("text", ""),
                )
            )

        # Keyword-based relevance check
        tags = set()
        if keywords:
            text_to_check = cleaned_text.lower()
            if any(keyword.lower() in text_to_check for keyword in keywords):
                tags.add("legal-priority")

        return ParsedDocument(
            document_url=url,
            language="en",
            sections=tuple(sections),
            tags=frozenset(tags),
            metadata={"discovered_links": discovered_links},
        )

    def _extract_markdown_with_llm(self, text: str) -> str:
        """Use the Extraction Agent to find legal headers and clauses."""
        response = self._llm.complete(
            build_markdown_extraction_prompt(text),
            MARKDOWN_EXTRACTION_SCHEMA,
            agent_profile="extraction_agent",
        )
        return response.get("markdown_content", "")

    def _structure_json_with_llm(self, markdown_text: str) -> dict[str, Any]:
        """Use the Structuring Agent to enforce JSON schema."""
        return self._llm.complete(
            build_structured_sections_prompt(markdown_text),
            STRUCTURED_SECTIONS_SCHEMA,
            agent_profile="structuring_agent",
        )
