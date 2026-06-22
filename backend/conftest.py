"""Test bootstrap: put backend/ on sys.path and share deterministic fixtures.

Lets `from core...` / `from adapters...` resolve when running `pytest` from backend/.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pytest

from core.domain.document import ParsedDocument, RawSection


@pytest.fixture
def parsed_document() -> ParsedDocument:
    """A small, nested legal document spanning two RDTII pillars (6 and 7)."""
    return ParsedDocument(
        document_url="https://example.gov/data-protection-act",
        language="en",
        sections=(
            RawSection("Data Protection Act", 1, "An act respecting data protection."),
            RawSection("Cross-Border Data Flows", 2, "Rules on transferring data abroad."),
            RawSection("Adequacy Decisions", 3, "Transfers to adequate jurisdictions."),
            RawSection("Standard Contractual Clauses", 3, "Transfers via approved clauses."),
            RawSection("Domestic Data Protection", 2, "Rules for processing within the country."),
            RawSection("Consent Requirements", 3, "Lawful basis through consent."),
            RawSection("Data Subject Rights", 3, "Access, rectification, and erasure."),
        ),
    )
