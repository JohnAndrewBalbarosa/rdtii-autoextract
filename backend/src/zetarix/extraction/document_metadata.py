"""Extract legal-document metadata from crawled text and source URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

_CHROME_LOWER = frozenset(
    {
        "home",
        "laws of malaysia",
        "the statutes of the republic of singapore",
        "the st a tutes of the republic of singapore",
        "guide to",
        "privacy",
        "legislation",
        "search",
        "menu",
        "contents",
        "navigation",
        "skip to content",
        "australian government",
        "federal register of legislation",
    }
)

_ACT_HEADING_RE = re.compile(
    r"^[\s\*]*(.{8,220}?\b(?:Act|Ordinance|Code|Regulations?|Decree|Statute|Order)\b.{0,120}?\d{4}.{0,40}?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_CAPS_ACT_RE = re.compile(
    r"^([A-Z][A-Z0-9\s,\.\-\(\)']{8,120}\bACT\b[A-Z0-9\s,\.\-\(\)']{0,60}\d{4}[A-Z0-9\s,\.\-\(\)']{0,20})\s*$",
    re.MULTILINE,
)
_AMENDMENT_DATE_RE = re.compile(
    r"(?:"
    r"last\s+amended(?:\s+on)?|commenced(?:\s+on)?|as\s+at|revised(?:\s+on)?|"
    r"in\s+force(?:\s+from)?|effective(?:\s+from)?|gazetted(?:\s+on)?"
    r")\s*[:\-]?\s*"
    r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})",
    re.IGNORECASE,
)
_HEADER_SCAN_CHARS = 4000


@dataclass(frozen=True)
class DocumentMetadata:
    act_title: str
    last_update: date | None


def _normalize_title(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _is_chrome(line: str) -> bool:
    cleaned = _normalize_title(line).lower()
    if not cleaned or len(cleaned) < 3:
        return True
    if cleaned in _CHROME_LOWER:
        return True
    if cleaned.startswith("skip to main"):
        return True
    if "sign in to my account" in cleaned:
        return True
    if "help and resources" in cleaned:
        return True
    if cleaned.startswith("the statutes of the republic"):
        return True
    return False


def _clean_candidate_title(text: str) -> str:
    candidate = _normalize_title(text)
    for marker in (
        " Compilation No.",
        " Compilation date:",
        " Includes amendments:",
        " About this compilation",
        " About this Compilation",
    ):
        if marker in candidate:
            candidate = candidate.split(marker, 1)[0].strip()
    return candidate


def _title_from_url(url: str) -> str | None:
    if not url:
        return None
    segment = url.rstrip("/").split("?")[0].split("#")[0].rsplit("/", 1)[-1]
    if not segment or segment.lower() in {"act", "latest", "text", "versions", "details"}:
        return None
    if re.fullmatch(r"[A-Z]\d{4}[A-Z]\d{5,}", segment, re.I):
        return None
    slug = re.sub(r"\.(pdf|html?|aspx)$", "", segment, flags=re.I)
    slug = re.sub(r"[-_+%]+", " ", slug).strip()
    if len(slug) < 6:
        return None
    return _normalize_title(slug.title())


def extract_act_title(text: str, *, url: str = "") -> str:
    if not text or not text.strip():
        fallback = _title_from_url(url)
        return fallback or "Untitled Document"

    header = text[:_HEADER_SCAN_CHARS]

    for pattern in (_ACT_HEADING_RE, _CAPS_ACT_RE):
        for match in pattern.finditer(header):
            candidate = _normalize_title(match.group(1))
            candidate = _clean_candidate_title(candidate)
            if not _is_chrome(candidate) and len(candidate) >= 10:
                return candidate[:300]

    for line in header.splitlines():
        stripped = _normalize_title(line)
        if _is_chrome(stripped) or len(stripped) < 10:
            continue
        if re.search(r"\b(Act|Ordinance|Code|Regulations?)\b", stripped, re.I):
            return _clean_candidate_title(stripped)[:300]
        if re.search(r"\b(Act|PDPA|Protection)\b", stripped, re.I) and _YEAR_RE.search(stripped):
            return _clean_candidate_title(stripped)[:300]

    fallback = _title_from_url(url)
    return fallback or "Untitled Document"


def extract_last_update(text: str) -> date | None:
    if not text:
        return None

    header = text[:_HEADER_SCAN_CHARS]
    candidates: list[date] = []

    for match in _AMENDMENT_DATE_RE.finditer(header):
        parsed = _parse_textual_date(match.group(1))
        if parsed is not None:
            candidates.append(parsed)

    for match in re.finditer(
        r"(?:last\s+amended|commenced|as\s+at|revised|in\s+force)[^\n]{0,80}?(\d{4})",
        header,
        re.I,
    ):
        year = int(match.group(1))
        if 1900 <= year <= 2100:
            candidates.append(date(year, 1, 1))

    for match in re.finditer(
        r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b",
        header[:1500],
        re.I,
    ):
        parsed = _parse_textual_date(match.group(1))
        if parsed is not None:
            candidates.append(parsed)

    if not candidates:
        return None
    return max(candidates)


def _parse_textual_date(text: str) -> date | None:
    cleaned = text.strip().replace(",", "")
    for fmt in ("%d %B %Y", "%B %d %Y", "%d %b %Y", "%b %d %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    years = [int(y.group()) for y in _YEAR_RE.finditer(cleaned)]
    if len(years) == 1:
        return date(years[0], 1, 1)
    return None


def extract_document_metadata(text: str, *, url: str = "") -> DocumentMetadata:
    return DocumentMetadata(
        act_title=extract_act_title(text, url=url),
        last_update=extract_last_update(text),
    )
