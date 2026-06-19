"""Ports — the stable interfaces the core depends on.

Every concrete tool (LLM, OCR, vector store, crawler, storage) implements one of these
Protocols and is wired in at the edge (adapters/). The core NEVER imports a concrete
adapter, which is what makes the whole system swappable (R12, R13, R16).

A "swap" = registering a different implementation; no core code changes.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from core.domain.document import ParsedDocument
from core.domain.entities import Article, Finding


class DocumentSource(Protocol):
    """Discovers and fetches official regulatory documents (R8, R19, R20)."""

    def discover(self, jurisdiction: str, pillars: Sequence[int]) -> list[str]: ...
    def fetch(self, url: str) -> bytes: ...  # raw bytes; may be a scanned PDF


class OCREngine(Protocol):
    """Extracts text from raw documents at < 5% CER (R17)."""

    def extract(self, raw: bytes) -> str: ...


class Chunker(Protocol):
    """Splits document text into article-level chunks (R4, R14)."""

    def by_article(self, text: str, document_url: str, language: str) -> list[Article]: ...


class VectorStore(Protocol):
    """RAG retrieval over article chunks (R14)."""

    def upsert(self, articles: Sequence[Article]) -> None: ...
    def search(self, query: str, k: int = 8) -> list[Article]: ...


class DocumentExtractorPort(Protocol):
    """Extracts structured document entities from a given URL (R7, OSI L7 Application)."""

    def scrape_url(self, url: str) -> ParsedDocument: ...


class HtmlFetcherPort(Protocol):
    """Fetches raw HTTP text content from a URL (OSI L4 Transport)."""

    def fetch(self, url: str) -> str: ...


class LLMProvider(Protocol):
    """Structured extraction/verification. Paid in dev, open-weight in prod (R12)."""

    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict: ...


class IndicatorClassifier(Protocol):
    """Small classifier + LLM verification → RDTII indicators (R14)."""

    def classify(self, article: Article) -> list[str]: ...


class FindingRepository(Protocol):
    """Persists findings and powers the audit view / review queue (R3, R18)."""

    def save(self, finding: Finding) -> None: ...
    def list_pending(self) -> list[Finding]: ...
