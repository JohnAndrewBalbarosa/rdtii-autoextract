"""Tests for PDF-safe fetch and PDF routing in the scrape pipeline."""
from __future__ import annotations

import io
import gzip
import pytest
from unittest.mock import MagicMock, patch

from adapters.botting.l4_transport.fetch_result import FetchResult, _is_text_content_type, _charset_from_content_type
from adapters.botting.l4_transport.http_client import HttpClient
from adapters.botting.l4_transport.factory import TransportFactory
from adapters.botting.l4_transport.pdf_parser import PdfParser
from adapters.botting.l6_presentation.dom_cleaner import DomCleaner
from adapters.botting.l7_application.pipeline_adapter import PipelineAdapter
from core.ports import LLMProvider, HtmlFetcherPort


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

MINIMAL_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"%%EOF"
)

HTML_BYTES = b"<html><body><h1>Hello</h1></body></html>"


class MockLLMProvider(LLMProvider):
    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        if agent_profile == "extraction_agent":
            return {"markdown_content": "# Section\n\nSome text."}
        if agent_profile == "structuring_agent":
            return {"sections": [{"heading": "Section", "level": 1, "text": "Some text."}]}
        return {"is_valid": True}


class BinaryFetcher(HtmlFetcherPort):
    """Stub that always returns a PDF FetchResult via fetch_raw."""

    def __init__(self, pdf_bytes: bytes, url: str = "https://example.com/doc.pdf"):
        self._pdf_bytes = pdf_bytes
        self._url = url

    def fetch_raw(self, url: str) -> FetchResult:
        return FetchResult(
            url=url,
            status=200,
            content_type="application/pdf",
            body=self._pdf_bytes,
        )

    def fetch(self, url: str) -> str:
        # Satisfies HtmlFetcherPort; not called in PDF path
        return ""


class HtmlFetcherStub(HtmlFetcherPort):
    """Stub that returns HTML via fetch_raw."""

    def fetch_raw(self, url: str) -> FetchResult:
        return FetchResult(
            url=url,
            status=200,
            content_type="text/html; charset=utf-8",
            body=HTML_BYTES,
        )

    def fetch(self, url: str) -> str:
        return HTML_BYTES.decode("utf-8")


# ---------------------------------------------------------------------------
# FetchResult unit tests
# ---------------------------------------------------------------------------

class TestFetchResult:
    def test_text_content_type_detection(self):
        assert _is_text_content_type("text/html; charset=utf-8") is True
        assert _is_text_content_type("text/plain") is True
        assert _is_text_content_type("application/json") is True
        assert _is_text_content_type("application/pdf") is False
        assert _is_text_content_type("application/octet-stream") is False

    def test_charset_extraction(self):
        assert _charset_from_content_type("text/html; charset=ISO-8859-1") == "ISO-8859-1"
        assert _charset_from_content_type("text/html") == "utf-8"

    def test_pdf_fetch_result_does_not_crash(self):
        """BUG 1 regression: binary PDF bytes must not raise on construction."""
        result = FetchResult(
            url="https://example.com/law.pdf",
            status=200,
            content_type="application/pdf",
            body=MINIMAL_PDF_BYTES,
        )
        assert result.body == MINIMAL_PDF_BYTES
        assert result.is_pdf is True

    def test_pdf_text_property_raises_valueerror(self):
        """Accessing .text on a PDF FetchResult should raise ValueError, not crash silently."""
        result = FetchResult(
            url="https://example.com/law.pdf",
            status=200,
            content_type="application/pdf",
            body=MINIMAL_PDF_BYTES,
        )
        with pytest.raises(ValueError, match="non-text"):
            _ = result.text

    def test_html_fetch_result_text_decodes(self):
        result = FetchResult(
            url="https://example.com/",
            status=200,
            content_type="text/html; charset=utf-8",
            body=HTML_BYTES,
        )
        assert result.text == HTML_BYTES.decode("utf-8")
        assert result.is_pdf is False

    def test_is_pdf_by_url_extension(self):
        result = FetchResult(
            url="https://example.com/report.pdf",
            status=200,
            content_type="application/octet-stream",
            body=MINIMAL_PDF_BYTES,
        )
        assert result.is_pdf is True


# ---------------------------------------------------------------------------
# HttpClient.fetch() must not crash on PDF responses
# ---------------------------------------------------------------------------

class TestHttpClientBinaryPDF:
    def test_fetch_returns_empty_string_for_pdf_content_type(self):
        """BUG 1 regression: fetch() on a PDF URL must not raise UnicodeDecodeError."""
        client = HttpClient()

        # Patch urlopen to return a fake PDF response
        fake_response = MagicMock()
        fake_response.__enter__ = MagicMock(return_value=fake_response)
        fake_response.__exit__ = MagicMock(return_value=False)
        fake_response.read.return_value = MINIMAL_PDF_BYTES
        fake_response.headers.get.return_value = "application/pdf"
        fake_response.status = 200

        with patch("adapters.botting.l4_transport.http_client.urlopen", return_value=fake_response):
            result = client.fetch("https://example.com/doc.pdf")

        # Must not raise; returns empty string for binary
        assert isinstance(result, str)

    def test_fetch_raw_returns_fetchresult_for_pdf(self):
        client = HttpClient()

        fake_response = MagicMock()
        fake_response.__enter__ = MagicMock(return_value=fake_response)
        fake_response.__exit__ = MagicMock(return_value=False)
        fake_response.read.return_value = MINIMAL_PDF_BYTES
        fake_response.headers.get.return_value = "application/pdf"
        fake_response.status = 200

        with patch("adapters.botting.l4_transport.http_client.urlopen", return_value=fake_response):
            result = client.fetch_raw("https://example.com/doc.pdf")

        assert isinstance(result, FetchResult)
        assert result.body == MINIMAL_PDF_BYTES
        assert result.is_pdf is True
        assert result.status == 200

    def test_fetch_raw_decodes_gzip_html_response(self):
        client = HttpClient()

        fake_response = MagicMock()
        fake_response.__enter__ = MagicMock(return_value=fake_response)
        fake_response.__exit__ = MagicMock(return_value=False)
        fake_response.read.return_value = gzip.compress(HTML_BYTES)
        fake_response.headers.get.side_effect = lambda key, default=None: {
            "Content-Type": "text/html; charset=utf-8",
            "Content-Encoding": "gzip",
        }.get(key, default)
        fake_response.status = 200

        with patch("adapters.botting.l4_transport.http_client.urlopen", return_value=fake_response):
            result = client.fetch_raw("https://example.com/page")

        assert result.text == HTML_BYTES.decode("utf-8")


# ---------------------------------------------------------------------------
# PipelineAdapter PDF routing
# ---------------------------------------------------------------------------

class TestPipelineAdapterPdfRouting:
    def _make_pipeline(self, fetcher: HtmlFetcherPort, extracted_text: str = "Extracted PDF text.") -> PipelineAdapter:
        llm = MockLLMProvider()
        cleaner = DomCleaner()

        pdf_parser = MagicMock(spec=PdfParser)
        pdf_parser.extract_text.return_value = extracted_text
        pdf_parser.download_pdf.return_value = MINIMAL_PDF_BYTES

        return PipelineAdapter(llm, fetcher, cleaner, pdf_parser=pdf_parser)

    def test_pdf_url_routed_to_pdf_parser(self):
        """BUG 2 regression: .pdf URL must go through PdfParser, not DomCleaner."""
        pdf_bytes = MINIMAL_PDF_BYTES
        fetcher = BinaryFetcher(pdf_bytes)
        llm = MockLLMProvider()
        cleaner = MagicMock(spec=DomCleaner)

        pdf_parser = MagicMock(spec=PdfParser)
        pdf_parser.extract_text.return_value = "Computer Crime Act extracted text."

        pipeline = PipelineAdapter(llm, fetcher, cleaner, pdf_parser=pdf_parser)
        doc = pipeline.scrape_url("https://example.com/law.pdf")

        # PdfParser.extract_text should have been called with the PDF bytes
        pdf_parser.extract_text.assert_called_once_with(pdf_bytes)
        # DomCleaner must NOT have been called
        cleaner.clean_html.assert_not_called()
        # Document returned successfully
        assert doc.document_url == "https://example.com/law.pdf"
        assert len(doc.sections) > 0

    def test_html_url_routed_to_dom_cleaner(self):
        """HTML URLs must still go through DomCleaner (no regression)."""
        fetcher = HtmlFetcherStub()
        llm = MockLLMProvider()
        cleaner = MagicMock(spec=DomCleaner)
        cleaner.clean_html.return_value = "Cleaned HTML text."
        cleaner.discover_links.return_value = []

        pdf_parser = MagicMock(spec=PdfParser)

        pipeline = PipelineAdapter(llm, fetcher, cleaner, pdf_parser=pdf_parser)
        doc = pipeline.scrape_url("https://example.com/page")

        cleaner.clean_html.assert_called_once()
        pdf_parser.extract_text.assert_not_called()
        assert doc.document_url == "https://example.com/page"

    def test_pdf_scrape_produces_sections(self):
        """Scraping a PDF URL must produce at least one section (end-to-end smoke)."""
        pdf_bytes = MINIMAL_PDF_BYTES
        fetcher = BinaryFetcher(pdf_bytes)
        pipeline = self._make_pipeline(fetcher, extracted_text="Section 1. This is the law.")
        doc = pipeline.scrape_url("https://example.com/law.pdf")
        assert isinstance(doc.sections, tuple)
        assert len(doc.sections) >= 1
