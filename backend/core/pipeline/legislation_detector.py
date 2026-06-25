"""Legislative-content detector — "is this page actually law, or page chrome?".

The HTML boundary problem: a government portal page may be the statute text, or a news /
landing / announcements page that merely *links* to laws. PDFs are bounded (the file is the
law); HTML is not. This pure, deterministic heuristic scores how strongly a block of text
reads like legislation, so the crawl path can reject non-statutory pages and avoid emitting
findings from job ads, menus, or press releases.

Signals (all model-free):
* **section markers** — "Section 26", "Article 12", "s. 14", "Part IV", "regulation 5", "§ 3";
* **numbered provisions** — line-leading "26.—(1)", "(1)", "13." enumerations;
* **legislative diction** — "shall", "offence", "subsection", "this Act", "pursuant to" …

No I/O, no model. Same text → same verdict.
"""

from __future__ import annotations

import re

_SECTION_MARKER_RE = re.compile(
    r"\b(?:section|article|art\.|s\.|§|part|regulation|reg\.|clause|paragraph|para\.)\s*\d+",
    re.IGNORECASE,
)
# Line-leading enumerations like "26.—(1)", "(1)", "13.", "(a)".
_NUMBERED_PROVISION_RE = re.compile(r"(?m)^\s*\(?\s*(?:\d+[A-Za-z]?|[ivxlc]+|[a-z])\s*\)?\s*[.—\-]")
_LEGAL_TERMS = (
    "shall", "must not", "is guilty", "offence", "offense", "subsection", "pursuant to",
    "in accordance with", "this act", "the act", "hereby", "provided that",
    "notwithstanding", "prescribed", "commencement", "interpretation", "whereas",
    "be it enacted", "regulations", "provisions of",
)

# Tunables (named — no magic numbers).
_MIN_SECTION_MARKERS = 2
_MIN_LEGAL_TERMS = 2


def _count(pattern: re.Pattern, text: str) -> int:
    return sum(1 for _ in pattern.finditer(text))


def legislative_signals(text: str) -> dict:
    """Raw signal counts for ``text`` (section markers, numbered provisions, legal terms)."""
    lowered = (text or "").lower()
    return {
        "section_markers": _count(_SECTION_MARKER_RE, text or ""),
        "numbered_provisions": _count(_NUMBERED_PROVISION_RE, text or ""),
        "legal_terms": sum(1 for term in _LEGAL_TERMS if term in lowered),
        "length": len(text or ""),
    }


def legislative_score(text: str) -> float:
    """A 0.0–1.0 confidence that ``text`` is legislative content (deterministic).

    Blends the three signals with diminishing returns so a long statute saturates near 1.0
    while a news page with one stray "section" stays low.
    """
    sig = legislative_signals(text)
    if sig["length"] < 40:
        return 0.0
    markers = min(sig["section_markers"], 8) / 8.0
    provisions = min(sig["numbered_provisions"], 12) / 12.0
    terms = min(sig["legal_terms"], 6) / 6.0
    # Weighted: section markers + legal diction dominate; numbered provisions corroborate.
    return round(0.45 * markers + 0.20 * provisions + 0.35 * terms, 4)


def is_legislative(text: str) -> bool:
    """True when ``text`` reads like statute/regulation, not page chrome or news.

    Requires both enough section markers AND enough legislative diction, so a landing page
    that merely mentions "section" once (or lists job vacancies) is rejected.
    """
    sig = legislative_signals(text)
    return (
        sig["section_markers"] >= _MIN_SECTION_MARKERS
        and sig["legal_terms"] >= _MIN_LEGAL_TERMS
    )
