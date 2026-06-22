"""MockProvisionExtractor — deterministic reference adapter for the extraction seam.

This is the *plumbing* implementation of the ``ProvisionExtractor`` port. Its job is NOT
accuracy: it exists to prove the ``crawl -> extract -> tag -> emit`` flow end-to-end
offline and to emit REAL verbatim snippets taken from the actual document text. A real
LLM extractor swaps in later behind the same port with no core changes.

How it works (fully deterministic — same input yields identical output):

1. ``title`` is derived from the document: the first substantive line of ``doc.text``,
   else a human-readable slug from the URL path.
2. For the requested ``pillar``, a small, documented keyword table maps each keyword to a
   golden-DB indicator id (``6.1`` ...). The first occurrence of each keyword (scanned in
   a stable, declared order) yields one ``Finding``.
3. ``verbatim_snippet`` is a REAL substring of ``doc.text``: the sentence/clause that
   contains the matched keyword, bounded to a maximum length.
4. ``article_section`` is regexed from text near the match ("Section 26", "Article 12"),
   else "".
5. ``mapping_rationale`` is a templated string (<=300 chars) naming the matched keyword
   and the resolved indicator. ``confidence`` is a fixed 0.5. ``discovery_tag`` is left at
   its default (run.py stamps NEW/KNOWN).

No clock, no randomness, no network, no LLM — stdlib only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.domain.document import CrawledDocument
from core.domain.entities import DiscoveryTag, Finding, Pillar
from core.domain.indicator_codes import to_canonical

# --- Tunables (named constants — no magic numbers) ---------------------------

MOCK_CONFIDENCE = 0.5  # fixed deterministic confidence for every mock finding
_MAX_SNIPPET_CHARS = 300  # bound on the verbatim clause length
_MAX_RATIONALE_CHARS = 300  # spec cap on mapping_rationale


# --- Keyword -> indicator tables ---------------------------------------------
#
# Each entry is (keyword, golden-DB indicator id). Keywords are lower-cased and matched
# on word boundaries against the document text. Order is significant and stable: it is
# the scan order, so a document mentioning several keywords yields findings in this
# declared order (determinism). The mapping is intentionally coarse — it proves the seam,
# not legal accuracy.

_PILLAR_KEYWORDS: dict[int, tuple[tuple[str, str], ...]] = {
    # Pillar 6 — Cross-border data flows
    6: (
        ("cross-border", "6.1"),
        ("transfer", "6.1"),
        ("overseas", "6.1"),
        ("localisation", "6.2"),
        ("localization", "6.2"),
        ("data residency", "6.2"),
        ("adequacy", "6.3"),
    ),
    # Pillar 7 — Domestic data protection
    7: (
        ("consent", "7.1"),
        ("breach", "7.2"),
        ("data subject", "7.3"),
        ("personal data", "7.4"),
        ("processing", "7.5"),
    ),
}

# "Section 26", "Section 26A", "Article 12", "Art. 5", "s. 14" near a match.
_SECTION_RE = re.compile(
    r"\b(?:Section|Article|Art\.?|s\.)\s*\d+[A-Za-z]?\b",
    re.IGNORECASE,
)

# Sentence terminators used to bound a verbatim clause around a keyword match.
_SENTENCE_BOUNDARY_RE = re.compile(r"[.;\n]")


@dataclass(frozen=True)
class _Match:
    """One keyword hit in the document text (internal, deterministic)."""

    keyword: str
    indicator_db: str
    start: int
    end: int


class MockProvisionExtractor:
    """Deterministic reference ``ProvisionExtractor`` (see module docstring)."""

    def extract(self, doc: CrawledDocument, pillar: int) -> list[Finding]:
        """Produce 1+ deterministic ``Finding``s from ``doc`` for the requested pillar.

        Returns an empty list only if no keyword for ``pillar`` appears in the text.
        Ordering follows the declared keyword scan order so output is stable.
        """
        keywords = _PILLAR_KEYWORDS.get(pillar, ())
        if not keywords:
            return []

        text = doc.text or ""
        title = self._derive_title(doc)
        pillar_enum = Pillar(pillar)

        findings: list[Finding] = []
        for keyword, indicator_db in keywords:
            match = self._first_match(text, keyword, indicator_db)
            if match is None:
                continue
            findings.append(
                self._build_finding(doc, title, pillar_enum, match)
            )
        return findings

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _first_match(self, text: str, keyword: str, indicator_db: str) -> _Match | None:
        """First word-boundary occurrence of ``keyword`` (case-insensitive)."""
        pattern = re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)
        hit = pattern.search(text)
        if hit is None:
            return None
        return _Match(
            keyword=keyword,
            indicator_db=indicator_db,
            start=hit.start(),
            end=hit.end(),
        )

    def _build_finding(
        self,
        doc: CrawledDocument,
        title: str,
        pillar: Pillar,
        match: _Match,
    ) -> Finding:
        indicator = to_canonical(match.indicator_db)
        snippet = self._verbatim_clause(doc.text or "", match)
        article_section = self._nearest_section(doc.text or "", match)
        rationale = self._rationale(match.keyword, indicator)
        notes = "Extracted from PDF text." if doc.is_pdf else ""
        return Finding(
            title=title,
            last_update=None,
            url=doc.url,
            scope="",
            provisions=snippet,
            impact="",
            pillar=pillar,
            indicator=indicator,
            confidence=MOCK_CONFIDENCE,
            economy=doc.economy,
            law_number=None,
            article_section=article_section,
            discovery_tag=DiscoveryTag.KNOWN,  # run.py re-stamps NEW/KNOWN
            verbatim_snippet=snippet,
            mapping_rationale=rationale,
            location_ref=doc.url or None,
            notes=notes,
        )

    def _verbatim_clause(self, text: str, match: _Match) -> str:
        """Return a REAL substring of ``text``: the clause containing the keyword.

        Bounded by the nearest sentence terminators on each side and capped at
        ``_MAX_SNIPPET_CHARS``. The result is always a literal slice of ``text``.
        """
        left = 0
        for boundary in _SENTENCE_BOUNDARY_RE.finditer(text, 0, match.start):
            left = boundary.end()
        right_match = _SENTENCE_BOUNDARY_RE.search(text, match.end)
        right = right_match.start() if right_match else len(text)

        clause = text[left:right].strip()
        if len(clause) > _MAX_SNIPPET_CHARS:
            # Keep the keyword visible: clamp around the match, still a real substring.
            kw_offset = match.start - left
            half = _MAX_SNIPPET_CHARS // 2
            window_start = max(0, kw_offset - half)
            clause = clause[window_start : window_start + _MAX_SNIPPET_CHARS].strip()
        return clause

    def _nearest_section(self, text: str, match: _Match) -> str:
        """Closest "Section N"/"Article N" reference to the match, else ""."""
        best: str = ""
        best_distance: int | None = None
        for found in _SECTION_RE.finditer(text):
            distance = abs(found.start() - match.start)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best = found.group(0)
        # Normalise internal whitespace ("Section   26" -> "Section 26").
        return re.sub(r"\s+", " ", best).strip()

    def _rationale(self, keyword: str, indicator: str) -> str:
        """Templated, deterministic, <=300 chars."""
        rationale = (
            f"Matched keyword '{keyword}' in document text; mapped to indicator "
            f"{indicator} by the deterministic mock keyword table."
        )
        return rationale[:_MAX_RATIONALE_CHARS]

    def _derive_title(self, doc: CrawledDocument) -> str:
        """First substantive line of the text, else a slug from the URL path."""
        for line in (doc.text or "").splitlines():
            stripped = line.strip()
            if len(stripped) >= 3:
                return stripped[:_MAX_SNIPPET_CHARS]
        return self._slug_from_url(doc.url)

    def _slug_from_url(self, url: str) -> str:
        """Human-readable law name from the last path segment of a URL."""
        if not url:
            return "Untitled Document"
        path = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        segment = path.rsplit("/", 1)[-1] if "/" in path else path
        segment = re.sub(r"\.(pdf|html?|aspx)$", "", segment, flags=re.IGNORECASE)
        slug = re.sub(r"[-_]+", " ", segment).strip()
        return slug.title() if slug else "Untitled Document"
