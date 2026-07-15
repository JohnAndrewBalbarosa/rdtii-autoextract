"""Ports — the stable interfaces the core depends on.

Every concrete tool (LLM, OCR, vector store, crawler, storage) implements one of these
Protocols and is wired in at the edge (adapters/). The core NEVER imports a concrete
adapter, which is what makes the whole system swappable (R12, R13, R16).

A "swap" = registering a different implementation; no core code changes.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from zetarix.domain.document import CrawledDocument, ParsedDocument
from zetarix.domain.entities import Article, Finding


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


class ProvisionExtractor(Protocol):
    """Turns one crawled legal document into article-level ``Finding``s (R4, R5, R14).

    The injectable extraction seam: a deterministic mock proves the plumbing today; a
    real LLM extractor swaps in later behind this exact signature with no core changes.
    Implementations must be pure with respect to their input — same ``doc`` + ``pillar``
    yields the same findings (stable ordering, no clock/randomness in the mock).
    """

    def extract(self, doc: CrawledDocument, pillar: int) -> list[Finding]: ...


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
    def replace_all(self, findings: Sequence[Finding], metadata: dict | None = None) -> None: ...
    def list_all(self) -> list[Finding]: ...
    def get(self, finding_id: str) -> Finding | None: ...
    def update(self, finding_id: str, changes: dict) -> Finding | None: ...
    def list_pending(self) -> list[Finding]: ...
