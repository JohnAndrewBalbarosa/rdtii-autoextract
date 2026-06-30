"""Parsed-document domain entities — framework-agnostic, immutable.

The input to the deterministic structural extractor (Stage 1). A document is split,
by a parser outside the core, into ordered heading blocks. The extractor walks these
blocks, derives tags from the heading breadcrumb, and combines blocks that share the
same section scope into a single ConceptNode. No OCR/HTML library is imported here.
See docs/GRAPH_PIPELINE.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RawSection:
    """One heading block of a document: a title/subheading plus its body text.

    `level` is the outline depth (1 = document title, 2 = heading, 3 = subheading, ...).
    The extractor uses the running stack of levels to compute each block's breadcrumb,
    which becomes its multi-label tag set.
    """

    heading: str
    level: int
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    """An ordered list of heading blocks for one source document (Stage 1 input)."""

    document_url: str
    language: str  # ISO 639-1
    sections: tuple[RawSection, ...]
    tags: frozenset[str] = field(default_factory=frozenset)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CrawledDocument:
    """Raw input to the provision-extraction seam (Stage: crawl -> extract).

    A single fetched legal document, already reduced to plain text by the transport
    layer (HTML cleaned by ``DomCleaner`` or PDF text via ``PdfParser``). It is the
    minimal contract a ``ProvisionExtractor`` needs — deliberately free of any web/LLM
    type so the port stays import-clean and the mock and the real LLM extractor swap
    behind the same struct.
    """

    url: str
    economy: str  # country analysed, e.g. "Singapore"
    text: str  # plain document text (HTML-cleaned or PDF-extracted)
    is_pdf: bool = False
    language: str = "en"  # ISO 639-1


@dataclass(frozen=True)
class GuideDefinition:
    """A whole-document term definition supplied by the high-context guide model."""

    term: str
    meaning: str


@dataclass(frozen=True)
class GuideSectionHint:
    """Bounded guide context for one section packet."""

    section_id: str
    summary: str
    relevant_labels: frozenset[str] = field(default_factory=frozenset)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocumentGuide:
    """Whole-law context produced once by a high-context model.

    The guide can orient smaller tagging agents, but it is not evidence. Tags must still
    be supported by quotes from the original section text.
    """

    document_url: str
    language: str
    purpose: str
    jurisdiction_context: str = ""
    definitions: tuple[GuideDefinition, ...] = ()
    section_hints: tuple[GuideSectionHint, ...] = ()
    warnings: tuple[str, ...] = ()
    version: str = "v1"

    def excerpt_for(self, section_id: str) -> str:
        """Return the bounded guide text relevant to one section."""
        hint = next((item for item in self.section_hints if item.section_id == section_id), None)
        parts: list[str] = []
        if self.purpose:
            parts.append(f"Purpose: {self.purpose}")
        if self.jurisdiction_context:
            parts.append(f"Jurisdiction: {self.jurisdiction_context}")
        if hint:
            parts.append(f"Section hint: {hint.summary}")
            if hint.relevant_labels:
                parts.append("Likely labels: " + ", ".join(sorted(hint.relevant_labels)))
            if hint.warnings:
                parts.append("Section warnings: " + "; ".join(hint.warnings))
        if self.warnings:
            parts.append("Document warnings: " + "; ".join(self.warnings))
        return "\n".join(parts)

    def relevant_labels_for(self, section_id: str) -> frozenset[str]:
        """Return guide-suggested labels for a section, if any."""
        hint = next((item for item in self.section_hints if item.section_id == section_id), None)
        return hint.relevant_labels if hint else frozenset()


@dataclass(frozen=True)
class SectionTaggingTask:
    """A low-context work packet for one section tagging subagent."""

    section_id: str
    document_url: str
    language: str
    heading: str
    text: str
    caption: str
    guide_excerpt: str
    allowed_tags: frozenset[str]
    schema_version: str = "section-tagging-v1"


@dataclass(frozen=True)
class TagEvidence:
    """Source-text evidence for one proposed tag."""

    tag: str
    quote: str
    start: int | None = None
    end: int | None = None
    locator: str | None = None


@dataclass(frozen=True)
class SectionTaggingResult:
    """A low-context subagent output for one section."""

    section_id: str
    tags: frozenset[str]
    evidence: tuple[TagEvidence, ...]
    confidence: float
    abstain_reason: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaggingReviewItem:
    """Audit item emitted when a section output cannot be accepted automatically."""

    section_id: str
    reason: str
    detail: str


@dataclass(frozen=True)
class TaggingReconciliationResult:
    """Accepted graph nodes plus items that need human review."""

    nodes: tuple["ConceptNode", ...]
    review_items: tuple[TaggingReviewItem, ...] = ()
