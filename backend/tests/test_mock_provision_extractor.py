"""Deterministic unit tests for the MockProvisionExtractor reference adapter.

These prove the extraction-seam plumbing without any network/LLM: a known legal text
yields the expected indicator, a verbatim snippet that IS a real substring of the input,
an ``article_section`` like "Section 26", and identical output across repeated runs.
"""

from __future__ import annotations

from adapters.extraction.mock_provision_extractor import (
    MOCK_CONFIDENCE,
    MockProvisionExtractor,
)
from core.domain.document import CrawledDocument

# A small, realistic legal text. "transfer" -> P6-I1; "Section 26" sits next to it.
_SAMPLE_P6_TEXT = (
    "Personal Data Protection Act 2012\n"
    "Section 26. An organisation shall not transfer any personal data to a country "
    "or territory outside Singapore except in accordance with requirements prescribed "
    "under this Act.\n"
    "Section 27. This section concerns unrelated matters."
)

_SAMPLE_P7_TEXT = (
    "Privacy Act\n"
    "Section 11. An organisation must obtain the consent of the individual before "
    "collecting personal data.\n"
    "Section 12. A data breach must be notified to the Commissioner."
)


def _doc(text: str) -> CrawledDocument:
    return CrawledDocument(
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        economy="Singapore",
        text=text,
        is_pdf=False,
    )


def test_transfer_keyword_maps_to_p6_i1():
    findings = MockProvisionExtractor().extract(_doc(_SAMPLE_P6_TEXT), pillar=6)

    assert findings, "expected at least one finding for the P6 sample"
    transfer = next(f for f in findings if f.indicator == "P6-I1")
    # verbatim_snippet MUST be a real substring of the source text.
    assert transfer.verbatim_snippet
    assert transfer.verbatim_snippet in _SAMPLE_P6_TEXT
    assert "transfer" in transfer.verbatim_snippet.lower()
    # article_section regexed near the match.
    assert transfer.article_section == "Section 26"
    assert transfer.economy == "Singapore"
    assert transfer.url == "https://sso.agc.gov.sg/Act/PDPA2012"
    assert transfer.confidence == MOCK_CONFIDENCE
    assert transfer.mapping_rationale and len(transfer.mapping_rationale) <= 300


def test_title_derived_from_first_line():
    findings = MockProvisionExtractor().extract(_doc(_SAMPLE_P6_TEXT), pillar=6)
    assert all(f.title == "Personal Data Protection Act 2012" for f in findings)


def test_pillar_7_consent_and_breach():
    findings = MockProvisionExtractor().extract(_doc(_SAMPLE_P7_TEXT), pillar=7)
    indicators = {f.indicator for f in findings}
    assert "P7-I1" in indicators  # consent
    assert "P7-I2" in indicators  # breach
    for finding in findings:
        assert finding.verbatim_snippet in _SAMPLE_P7_TEXT


def test_deterministic_same_input_same_output():
    extractor = MockProvisionExtractor()
    doc = _doc(_SAMPLE_P6_TEXT)
    first = extractor.extract(doc, pillar=6)
    second = extractor.extract(doc, pillar=6)
    assert first == second  # frozen dataclasses compare by value


def test_snippet_is_bounded():
    long_clause = "Section 5. " + ("data " * 200) + "transfer of records abroad"
    findings = MockProvisionExtractor().extract(_doc(long_clause), pillar=6)
    transfer = next(f for f in findings if f.indicator == "P6-I1")
    assert transfer.verbatim_snippet in long_clause
    assert len(transfer.verbatim_snippet) <= 300


def test_no_keyword_yields_no_findings():
    findings = MockProvisionExtractor().extract(
        _doc("This document talks about agriculture and weather only."), pillar=6
    )
    assert findings == []


def test_url_slug_title_when_no_text_heading():
    doc = CrawledDocument(
        url="https://example.gov/laws/data-transfer-act.pdf",
        economy="Australia",
        text="A clause mentioning transfer of personal data overseas.",
        is_pdf=True,
    )
    findings = MockProvisionExtractor().extract(doc, pillar=6)
    assert findings
    # First substantive line is the clause itself; title falls back to it (>=3 chars).
    assert findings[0].title  # non-empty
    assert findings[0].notes == "Extracted from PDF text."
