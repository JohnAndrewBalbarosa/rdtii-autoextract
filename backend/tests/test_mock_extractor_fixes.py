"""Regression tests for the three MockProvisionExtractor weakness fixes.

1. dedup — at most one Finding per indicator per document;
2. 6.4 / 6.5 coverage — contractual-safeguards and other-lawful-basis now emit;
3. context guard — a bare "transfer" with no cross-border qualifier does not fire P6-I1.
"""

from __future__ import annotations

from adapters.extraction.mock_provision_extractor import MockProvisionExtractor
from core.domain.document import CrawledDocument


def _doc(text: str, *, is_pdf: bool = False) -> CrawledDocument:
    return CrawledDocument(url="https://gov.example/act", economy="Singapore", text=text, is_pdf=is_pdf)


def test_dedup_one_finding_per_indicator():
    # "cross-border", "transfer", "overseas" all map to 6.1 — must yield ONE P6-I1 row.
    text = (
        "Cross-border transfer of personal data overseas is restricted. "
        "Any transfer to a country outside Singapore needs consent."
    )
    findings = MockProvisionExtractor().extract(_doc(text), pillar=6)
    p6_i1 = [f for f in findings if f.indicator == "P6-I1"]
    assert len(p6_i1) == 1


def test_indicator_6_4_contractual_safeguards_emitted():
    text = "Transfer is permitted where standard contractual clauses are in place for the country."
    findings = MockProvisionExtractor().extract(_doc(text), pillar=6)
    assert any(f.indicator == "P6-I4" for f in findings)


def test_indicator_6_5_other_lawful_basis_emitted():
    text = "A transfer outside the country may proceed where it is in the public interest."
    findings = MockProvisionExtractor().extract(_doc(text), pillar=6)
    assert any(f.indicator == "P6-I5" for f in findings)


def test_context_guard_suppresses_bare_transfer():
    # "technology transfer" with no cross-border context must NOT fire P6-I1.
    text = "This section concerns technology transfer between internal research departments."
    findings = MockProvisionExtractor().extract(_doc(text), pillar=6)
    assert all(f.indicator != "P6-I1" for f in findings)


def test_context_guard_allows_qualified_transfer():
    text = "An organisation shall not transfer personal data to a country outside Singapore."
    findings = MockProvisionExtractor().extract(_doc(text), pillar=6)
    assert any(f.indicator == "P6-I1" for f in findings)
