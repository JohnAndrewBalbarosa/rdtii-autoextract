"""TagMatchProvisionExtractor — the documented tag→SetTrie provision→indicator matcher.

This is the real, deterministic extraction substrate the megathread (§9) describes, now
wired to live crawled data. For each section of a ``CrawledDocument`` it:

1. derives the section's tags (``section_tagger.section_tags`` — breadcrumb + concept vocab),
2. queries a ``SetTrieIndex`` of indicator definitions with ``query_subsets`` — an indicator
   matches iff all its defining tags are present in the section (subset rule),
3. emits one ``Finding`` per (section, matched indicator) with a real verbatim snippet, the
   nearest article/section reference, and an anchored HTML ``Location Reference``.

Deterministic: same ``doc`` + ``pillar`` yields identical, stably-ordered findings. No clock,
no RNG, no network, no LLM. Implements the ``ProvisionExtractor`` port
(``extract(doc, pillar) -> list[Finding]``). When a document yields no tag matches the caller
(``run.py``) falls back to the keyword ``MockProvisionExtractor``.
"""

from __future__ import annotations

from dataclasses import dataclass

from adapters.botting.l6_presentation.html_sections import _section_text, format_location_ref
from adapters.extraction import section_tagger
from adapters.extraction.text_helpers import bounded_clause, derive_title, nearest_section
from core.domain.document import CrawledDocument, HtmlSection
from core.domain.entities import DiscoveryTag, Finding, Pillar
from core.domain.indicator_definitions import indicators_for_pillar
from core.pipeline.set_trie import SetTrieIndex

_MAX_RATIONALE_CHARS = 300
_BASE_CONFIDENCE = 0.5
_PER_TAG_CONFIDENCE = 0.1  # richer (more-tag) definitions score a touch higher


@dataclass(frozen=True)
class _Block:
    """A unit of analysis: one section's heading/text/anchor/path."""

    section_id: str
    heading: str
    text: str
    anchor: str | None
    path: tuple[str, ...]


class TagMatchProvisionExtractor:
    """Deterministic ``ProvisionExtractor`` using tag definitions + a set-trie matcher."""

    def __init__(self) -> None:
        # One trie over all indicator definitions; queries are filtered to the pillar.
        from core.domain.indicator_definitions import INDICATOR_TAGS

        self._trie = SetTrieIndex(
            tuple((code, tags) for code, tags in INDICATOR_TAGS.items())
        )

    def extract(self, doc: CrawledDocument, pillar: int) -> list[Finding]:
        pillar_defs = indicators_for_pillar(pillar)
        if not pillar_defs:
            return []

        title = (getattr(doc, "title", "") or "").strip() or derive_title(doc.text, doc.url)
        pillar_enum = Pillar(pillar)
        blocks = self._blocks(doc)

        findings: list[Finding] = []
        for block in blocks:
            tags = section_tagger.section_tags(block.heading, block.text, block.path)
            matched = [code for code in self._trie.query_subsets(tags) if code in pillar_defs]
            for code in matched:
                findings.append(
                    self._build_finding(doc, title, pillar_enum, block, code, pillar_defs[code])
                )
        return findings

    # ------------------------------------------------------------------ internals

    def _blocks(self, doc: CrawledDocument) -> list[_Block]:
        """One block per HTML section; a single whole-text block for PDF/sectionless docs."""
        if doc.sections:
            blocks: list[_Block] = []
            for index, section in enumerate(doc.sections):
                blocks.append(
                    _Block(
                        section_id=section.anchor or f"sec-{index}",
                        heading=section.heading,
                        text=section.text,
                        anchor=section.anchor,
                        path=section.path,
                    )
                )
            return blocks
        return [_Block(section_id="doc", heading="", text=doc.text or "", anchor=None, path=())]

    def _build_finding(
        self,
        doc: CrawledDocument,
        title: str,
        pillar: Pillar,
        block: _Block,
        code: str,
        def_tags: frozenset[str],
    ) -> Finding:
        section = HtmlSection(
            heading=block.heading, text=block.text, anchor=block.anchor, path=block.path
        )
        # Verbatim snippet is the provision body (not the heading); the article reference is
        # detected across heading + body (the section number usually lives in the heading).
        snippet = bounded_clause(block.text, 0) or bounded_clause(_section_text(section), 0)
        article = nearest_section(f"{block.heading}\n{block.text}", 0)
        location = format_location_ref(section, base_url=doc.url) or doc.url or None
        confidence = min(0.9, _BASE_CONFIDENCE + _PER_TAG_CONFIDENCE * len(def_tags))
        return Finding(
            title=title,
            last_update=None,
            url=doc.url,
            scope="",
            provisions=snippet,
            impact="",
            pillar=pillar,
            indicator=code,
            confidence=confidence,
            economy=doc.economy,
            law_number=None,
            article_section=article,
            discovery_tag=DiscoveryTag.KNOWN,  # run.py re-stamps NEW/KNOWN
            verbatim_snippet=snippet,
            mapping_rationale=self._rationale(code, def_tags),
            location_ref=location,
            notes="Extracted from PDF text." if doc.is_pdf else "",
        )

    def _rationale(self, code: str, def_tags: frozenset[str]) -> str:
        tags = ", ".join(sorted(def_tags))
        rationale = (
            f"Section carries the defining concepts ({tags}); maps to {code} because all "
            f"are present (set-trie subset match)."
        )
        return rationale[:_MAX_RATIONALE_CHARS]
