"""Tests for the tag→set-trie provision→indicator matcher and its section tagger.

Proves the documented §9 chain on synthetic-but-realistic sections: deterministic tagging,
subset matching to the right indicators, anchored HTML location refs, verbatim snippets that
are real substrings, pillar filtering, and the keyword-mock fallback composition.
"""

from __future__ import annotations

from adapters.botting.l6_presentation.html_sections import join_section_text
from adapters.extraction.fallback_provision_extractor import FallbackProvisionExtractor
from adapters.extraction.mock_provision_extractor import MockProvisionExtractor
from adapters.extraction.section_tagger import detect_concept_tags, section_tags
from adapters.extraction.tagmatch_provision_extractor import TagMatchProvisionExtractor
from core.domain.document import CrawledDocument, HtmlSection

_TRANSFER = HtmlSection(
    heading="Section 26 Transfer of personal data",
    text=(
        "An organisation shall not transfer any personal data to a country or territory "
        "outside Singapore unless the individual has given consent."
    ),
    anchor="s26",
    path=("Part VI", "Section 26"),
)
_BREACH = HtmlSection(
    heading="Section 26D Notification of data breach",
    text="An organisation must notify the Commissioner of a notifiable data breach.",
    anchor="s26d",
    path=("Part VIA", "Section 26D"),
)


def _doc(*sections: HtmlSection) -> CrawledDocument:
    return CrawledDocument(
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        economy="Singapore",
        text="Personal Data Protection Act 2012",
        is_pdf=False,
        sections=tuple(sections),
    )


def test_cross_border_section_maps_to_p6_i1_and_i4():
    findings = TagMatchProvisionExtractor().extract(_doc(_TRANSFER), pillar=6)
    indicators = {f.indicator for f in findings}
    assert "P6-I1" in indicators  # cross-border + restriction
    assert "P6-I4" in indicators  # cross-border + consent


def test_location_ref_uses_section_anchor():
    findings = TagMatchProvisionExtractor().extract(_doc(_TRANSFER), pillar=6)
    assert findings
    assert all(f.location_ref.endswith("#s26") for f in findings)


def test_verbatim_snippet_is_real_substring_of_source():
    doc = _doc(_TRANSFER)
    source = join_section_text(doc.sections)
    findings = TagMatchProvisionExtractor().extract(doc, pillar=6)
    for finding in findings:
        assert finding.verbatim_snippet
        assert finding.verbatim_snippet in source


def test_pillar_filter_excludes_other_pillar():
    # The transfer section carries P6 concepts; a P7 query must not return P6 codes.
    findings = TagMatchProvisionExtractor().extract(_doc(_TRANSFER), pillar=7)
    assert all(f.indicator.startswith("P7-") for f in findings)


def test_breach_section_maps_to_p7_i4():
    findings = TagMatchProvisionExtractor().extract(_doc(_BREACH), pillar=7)
    assert any(f.indicator == "P7-I4" for f in findings)


def test_no_concept_tags_yields_no_findings():
    plain = HtmlSection(heading="Short title", text="This Act may be cited as the X Act.", anchor="s1")
    assert TagMatchProvisionExtractor().extract(_doc(plain), pillar=6) == []


def test_deterministic_same_input_same_output():
    extractor = TagMatchProvisionExtractor()
    doc = _doc(_TRANSFER, _BREACH)
    assert extractor.extract(doc, 6) == extractor.extract(doc, 6)


def test_pdf_without_sections_falls_back_to_url_location():
    doc = CrawledDocument(
        url="https://example.gov/act.pdf",
        economy="Australia",
        text=(
            "Section 16 An organisation shall not transfer personal data to a country "
            "outside Australia without consent."
        ),
        is_pdf=True,
    )
    findings = TagMatchProvisionExtractor().extract(doc, pillar=6)
    assert findings
    assert all(f.location_ref == "https://example.gov/act.pdf" for f in findings)
    assert all(f.notes == "Extracted from PDF text." for f in findings)


# --- section tagger ---------------------------------------------------------------------


def test_detect_concept_tags_finds_cross_border_and_consent():
    tags = detect_concept_tags(_TRANSFER.text)
    assert "cross-border" in tags
    assert "consent" in tags
    assert "restriction" in tags


def test_section_tags_include_breadcrumb_slugs():
    tags = section_tags(_TRANSFER.heading, _TRANSFER.text, _TRANSFER.path)
    assert "part-vi" in tags
    assert "section-26" in tags


# --- fallback composition ---------------------------------------------------------------


def test_fallback_used_when_primary_empty():
    # "Short title" has no tag-match concepts; the keyword mock also finds nothing here,
    # but a section the mock CAN match proves the fallback path runs.
    doc = _doc(HtmlSection(heading="Collection", text="Consent is required before collecting personal data.", anchor="s13"))
    composite = FallbackProvisionExtractor(TagMatchProvisionExtractor(), MockProvisionExtractor())
    primary = TagMatchProvisionExtractor().extract(doc, pillar=7)
    result = composite.extract(doc, pillar=7)
    # Whatever the primary returns, the composite returns it; if empty, mock fills in.
    assert result == primary if primary else result == MockProvisionExtractor().extract(doc, 7)
