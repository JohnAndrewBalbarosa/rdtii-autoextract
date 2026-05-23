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
    """

    # --- 6 mandatory fields ---
    title: str
    last_update: date | None
    url: str
    scope: str
    provisions: str
    impact: str
    # --- mapping metadata ---
    pillar: Pillar
    indicator: str
    confidence: float
    review_status: ReviewStatus = ReviewStatus.PENDING

    def with_review(self, status: ReviewStatus) -> "Finding":
        """Return a new Finding with an updated review status (no mutation)."""
        return replace(self, review_status=status)
