"""Parsed-document domain entities — framework-agnostic, immutable.

The input to the deterministic structural extractor (Stage 1). A document is split,
by a parser outside the core, into ordered heading blocks. The extractor walks these
blocks, derives tags from the heading breadcrumb, and combines blocks that share the
same section scope into a single ConceptNode. No OCR/HTML library is imported here.
See docs/GRAPH_PIPELINE.md.
"""

from __future__ import annotations

from dataclasses import dataclass


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
