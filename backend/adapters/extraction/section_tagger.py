"""Deterministic section tagging — text/heading → ``ConceptNode`` tags (no AI, no model).

Bridges the crawl output (``HtmlSection`` / PDF text) into the tagging substrate the
``SetTrieIndex`` matcher consumes. Tags come from two deterministic sources:

1. **Breadcrumb slugs** from the section's heading path (mirrors the slug logic in
   ``adapters/extraction/structural_extractor.py``) — structural context tags.
2. **Concept-vocabulary tags** from ``core/domain/indicator_definitions.CONCEPT_VOCAB`` —
   a case-insensitive substring scan of the section text.

Same input always yields the same tags (sorted, frozenset). No clock, RNG, network, or LLM.
"""

from __future__ import annotations

import re

from core.domain.concept_node import ConceptNode
from core.domain.indicator_definitions import CONCEPT_VOCAB

# Mirror of structural_extractor._slug (kept local to avoid importing a private symbol).
_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    """Normalise a heading into a stable tag slug (lowercase, hyphenated)."""
    return _SLUG_NON_ALNUM.sub("-", text.strip().lower()).strip("-")


def detect_concept_tags(text: str) -> set[str]:
    """Concept tags whose trigger phrases appear in ``text`` (case-insensitive)."""
    lowered = (text or "").lower()
    found: set[str] = set()
    for tag, phrases in CONCEPT_VOCAB.items():
        if any(phrase in lowered for phrase in phrases):
            found.add(tag)
    return found


def section_tags(heading: str, text: str, path: tuple[str, ...] = ()) -> frozenset[str]:
    """All tags for a section: breadcrumb slugs + heading slug + detected concept tags."""
    tags: set[str] = set(detect_concept_tags(f"{heading}\n{text}"))
    for crumb in path:
        slug = _slug(crumb)
        if slug:
            tags.add(slug)
    heading_slug = _slug(heading)
    if heading_slug:
        tags.add(heading_slug)
    return frozenset(tags)


def tag_section(
    *,
    section_id: str,
    document_url: str,
    heading: str,
    text: str,
    path: tuple[str, ...] = (),
    language: str = "en",
) -> ConceptNode:
    """Build a tagged ``ConceptNode`` for one section (caption == heading; no AI captioning)."""
    return ConceptNode(
        section_id=section_id,
        document_url=document_url,
        text=text,
        caption=heading,
        tags=section_tags(heading, text, path),
        language=language,
    )
