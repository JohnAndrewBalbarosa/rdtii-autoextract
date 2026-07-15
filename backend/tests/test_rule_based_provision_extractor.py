from __future__ import annotations

from zetarix.domain.document import CrawledDocument
from zetarix.extraction.rule_based_provision_extractor import RuleBasedProvisionExtractor


_TEXT = (
    "Personal Data Protection Act 2012\n"
    "Section 26. An organisation shall not transfer any personal data to a country "
    "or territory outside Singapore except in accordance with this Act.\n"
    "Section 27. This section concerns administrative matters.\n"
    "Section 28. Consent of the individual is required before collecting personal data."
)


def _doc() -> CrawledDocument:
    return CrawledDocument(
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        economy="Singapore",
        text=_TEXT,
    )


def test_rule_based_extractor_returns_section_aware_findings():
    findings = RuleBasedProvisionExtractor().extract(_doc(), pillar=6)

    assert findings
    transfer = next(f for f in findings if f.indicator == "P6-I1")
    assert transfer.article_section == "Section 26"
    assert "cross-border transfer" in transfer.scope.lower()
    assert "keyword" not in transfer.mapping_rationale.lower()
    assert "detected" not in transfer.impact.lower()
    assert transfer.provisions.startswith("An organisation shall not transfer")
    assert transfer.verbatim_snippet in _TEXT
    assert transfer.notes.startswith("Verify")


def test_rule_based_extractor_is_deterministic():
    extractor = RuleBasedProvisionExtractor()
    first = extractor.extract(_doc(), pillar=6)
    second = extractor.extract(_doc(), pillar=6)
    assert first == second


def test_rule_based_extractor_recognises_bare_section_headers():
    doc = CrawledDocument(
        url="https://www.legislation.gov.au/C2004A03712/latest/text/original/document_1.html",
        economy="Australia",
        text=(
            "Privacy Act 1988\n"
            "13D Overseas act required by foreign law\n"
            "An act done overseas is not an interference with privacy if required by foreign law.\n"
            "16C Acts and practices of overseas recipients of personal information\n"
            "If an APP entity discloses personal information to an overseas recipient, it remains accountable.\n"
        ),
    )

    findings = RuleBasedProvisionExtractor().extract(doc, pillar=6)

    sections = {finding.article_section for finding in findings}
    assert "section 13D" in sections
    assert "section 16C" in sections


def test_rule_based_extractor_recognises_inline_section_headers_from_live_html_cleaning():
    doc = CrawledDocument(
        url="https://example.gov/privacy/text/original/document_1.html",
        economy="Australia",
        text=(
            "Privacy Act 1988 13D Overseas act required by foreign law "
            "An act or practice done overseas is not an interference with privacy if it is "
            "required by an applicable foreign law. "
            "16C Acts and practices of overseas recipients of personal information "
            "If an APP entity discloses personal information to an overseas recipient, the "
            "organisation remains accountable for the handling of that personal information."
        ),
    )

    findings = RuleBasedProvisionExtractor().extract(doc, pillar=6)

    assert findings
    assert any(f.article_section == "section 13D" for f in findings)
    assert any("overseas recipients of personal information" in f.provisions.lower() for f in findings)


def test_rule_based_extractor_rejects_definition_only_cross_border_section():
    doc = CrawledDocument(
        url="https://www.legislation.gov.au/example/privacy-act",
        economy="Australia",
        text=(
            "Privacy Act 1988\n"
            "Section 6 Interpretation\n"
            "In this Act, overseas recipient, in relation to personal information, has the meaning given by Australian Privacy Principle 8.\n"
            "Section 16C Acts and practices of overseas recipients of personal information\n"
            "If an APP entity discloses personal information to an overseas recipient, the entity remains accountable for the handling of that information.\n"
        ),
    )

    findings = RuleBasedProvisionExtractor().extract(doc, pillar=6)

    assert findings
    sections = {f.article_section.lower() for f in findings}
    assert "section 6" not in sections
    assert "section 16c" in sections


def test_rule_based_extractor_rejects_generic_personal_data_reference_without_rule():
    doc = CrawledDocument(
        url="https://example.gov/privacy-overview",
        economy="Singapore",
        text=(
            "Personal Data Protection Act 2012\n"
            "Section 2 Overview\n"
            "This Part provides a general overview of personal data protection and explains the policy background for organisations.\n"
            "Section 26 Transfer Limitation Obligation\n"
            "An organisation must not transfer personal data outside Singapore unless it provides a comparable standard of protection.\n"
        ),
    )

    findings = RuleBasedProvisionExtractor().extract(doc, pillar=6)

    sections = {f.article_section for f in findings}
    assert "Section 2" not in sections
    assert "Section 26" in sections


def test_rule_based_extractor_ranks_substantive_sections_ahead_of_weaker_context():
    doc = CrawledDocument(
        url="https://example.gov/privacy-live",
        economy="Australia",
        text=(
            "Privacy Act 1988\n"
            "Section 5B Overseas application\n"
            "This Act applies to acts done outside Australia in some circumstances.\n"
            "Section 16C Acts and practices of overseas recipients of personal information\n"
            "If an APP entity discloses personal information to an overseas recipient, it remains accountable for the handling of that information.\n"
        ),
    )

    findings = RuleBasedProvisionExtractor().extract(doc, pillar=6)

    assert findings[0].article_section == "Section 16C"


def test_rule_based_extractor_drops_placeholder_sections_instead_of_falling_back():
    doc = CrawledDocument(
        url="https://...",
        economy="Singapore",
        text=(
            "Personal Data Protection Act 2012\n"
            "Section 26. [exact section text here]\n"
            "[1–2 lines before and after]"
        ),
    )

    findings = RuleBasedProvisionExtractor().extract(doc, pillar=6)

    assert findings == []


def test_rule_based_extractor_requires_section_structure_for_live_findings():
    doc = CrawledDocument(
        url="https://example.gov/homepage",
        economy="Singapore",
        text=(
            "Personal Data Protection Commission overview. Personal data may be transferred in some cases. "
            "This page explains the legislation and provides general guidance for organisations."
        ),
    )

    findings = RuleBasedProvisionExtractor().extract(doc, pillar=6)

    assert findings == []
