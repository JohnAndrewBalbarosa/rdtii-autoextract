"""ConceptNode — the tagged law-section entity. Framework-agnostic, immutable.

A ConceptNode is what the structural/guided taggers emit and what the tags-only
set-trie index consumes. No graph library or edge/community concept is imported here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ConceptNode:
    """A law section turned into a tagged node, with multiple tags (Stage 1)."""

    section_id: str
    document_url: str
    text: str  # OCR'd section text
    caption: str  # SigLIP-style descriptor produced at OCR time; the BASIS for tags
    tags: frozenset[str]  # multi-label, derived from text + caption
    language: str

    def with_tags(self, tags: frozenset[str]) -> "ConceptNode":
        """Return a new node with replaced tags (no mutation)."""
        return replace(self, tags=tags)
