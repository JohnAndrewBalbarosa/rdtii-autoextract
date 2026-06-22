"""Pure text helpers shared by the deterministic extractors (no I/O, no model).

Title derivation, URL slugging, nearest article/section detection, and clause bounding —
all returning REAL substrings of their input so verbatim snippets stay audit-faithful.
"""

from __future__ import annotations

import re

_MAX_SNIPPET_CHARS = 300

# "Section 26", "Section 26A", "Article 12", "Art. 5", "s. 14".
_SECTION_RE = re.compile(r"\b(?:Section|Article|Art\.?|s\.)\s*\d+[A-Za-z]?\b", re.IGNORECASE)
# Sentence/clause terminators used to bound a verbatim clause.
_SENTENCE_BOUNDARY_RE = re.compile(r"[.;\n]")


def slug_from_url(url: str) -> str:
    """Human-readable law name from the last path segment of a URL."""
    if not url:
        return "Untitled Document"
    path = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    segment = path.rsplit("/", 1)[-1] if "/" in path else path
    segment = re.sub(r"\.(pdf|html?|aspx)$", "", segment, flags=re.IGNORECASE)
    slug = re.sub(r"[-_]+", " ", segment).strip()
    return slug.title() if slug else "Untitled Document"


def derive_title(text: str, url: str) -> str:
    """First substantive line of ``text`` (>=3 chars), else a slug from ``url``."""
    for line in (text or "").splitlines():
        stripped = line.strip()
        if len(stripped) >= 3:
            return stripped[:_MAX_SNIPPET_CHARS]
    return slug_from_url(url)


def nearest_section(text: str, index: int) -> str:
    """Closest "Section N"/"Article N" reference to ``index`` in ``text``, else ""."""
    best = ""
    best_distance: int | None = None
    for found in _SECTION_RE.finditer(text or ""):
        distance = abs(found.start() - index)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best = found.group(0)
    return re.sub(r"\s+", " ", best).strip()


def bounded_clause(text: str, index: int = 0, max_chars: int = _MAX_SNIPPET_CHARS) -> str:
    """Return the sentence/clause containing ``index``, capped at ``max_chars``.

    Always a literal slice of ``text`` (verbatim-safe). Bounds on the nearest sentence
    terminators around ``index``; clamps around the index if the clause is over the cap.
    """
    text = text or ""
    if not text:
        return ""
    index = max(0, min(index, len(text) - 1))
    left = 0
    for boundary in _SENTENCE_BOUNDARY_RE.finditer(text, 0, index):
        left = boundary.end()
    right_match = _SENTENCE_BOUNDARY_RE.search(text, index)
    right = right_match.start() if right_match else len(text)

    clause = text[left:right].strip()
    if len(clause) > max_chars:
        offset = index - left
        half = max_chars // 2
        start = max(0, offset - half)
        clause = clause[start : start + max_chars].strip()
    return clause
