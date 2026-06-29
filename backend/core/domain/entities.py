"""RDTII domain entities — framework-agnostic, immutable.

No imports from any web framework, LLM SDK, or storage library. This module is the
stable heart of the system (see docs/ARCHITECTURE.md). Traces: R4, R5, R7, R3, R18.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from enum import Enum


class Pillar(Enum):
    """RDTII pillars. 6 and 7 are mandatory (R7); others are bonus scope."""

    CROSS_BORDER_DATA_FLOWS = 6
    DOMESTIC_DATA_PROTECTION = 7


class ReviewStatus(Enum):
    """Drives the human-in-the-loop audit view (R3, R18)."""

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class DiscoveryTag(Enum):
    """Round-1 output flag: was this find independent (NEW) or from the sample kit (KNOWN)?

    Maps to the mandatory ``Discovery Tag`` column in the submission CSV (spec p.14).
    """

    NEW = "NEW"
    KNOWN = "KNOWN"


@dataclass(frozen=True)
class Article:
    """The atomic unit of analysis — a specific article in a specific document (R4)."""

    document_url: str
    article_number: str
    text: str
    language: str  # ISO 639-1; non-English supported (R19)


@dataclass(frozen=True)
class Finding:
    """An Article mapped to an RDTII indicator, with the 6 mandatory fields (R5).

    Immutable: state transitions return a new Finding (see coding-style: immutability).

    The fields below ``review_status`` back the Round-1 submission CSV/JSON schema
    (``docs/ROUND1_SUBMISSION_SPEC.md`` p.14). They are all defaulted so existing
    constructors stay valid. ``indicator`` carries the canonical ``P6-I1`` form.
    """

    # --- 6 mandatory fields ---
    title: str  # ↔ output "Law Name"
    last_update: date | None  # ↔ output "Last Amended"
    url: str  # ↔ output "Source URL"
    scope: str
    provisions: str
    impact: str
    # --- mapping metadata ---
    pillar: Pillar
    indicator: str  # canonical "P6-I1" form
    confidence: float
    review_status: ReviewStatus = ReviewStatus.PENDING
    # --- Round-1 submission fields (spec p.14) ---
    economy: str = ""  # country analysed
    law_number: str | None = None  # official act/law number ("Law Number / Ref")
    article_section: str = ""  # exact article + paragraph
    discovery_tag: DiscoveryTag = DiscoveryTag.KNOWN
    verbatim_snippet: str = ""  # exact quoted text — no paraphrasing (audit trail)
    mapping_rationale: str = ""  # why it maps here (intended ≤300 chars)
    location_ref: str | None = None  # PDF page no. | HTML Location Reference
    notes: str = ""  # OCR issues, partial doc, bilingual

    def with_review(self, status: ReviewStatus) -> "Finding":
        """Return a new Finding with an updated review status (no mutation)."""
        return replace(self, review_status=status)
