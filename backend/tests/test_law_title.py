"""Law-name fix: findings should use the detected Act title, not the first heading."""

from adapters.extraction.mock_provision_extractor import MockProvisionExtractor
from adapters.extraction.text_helpers import clean_law_title
from core.domain.document import CrawledDocument


def test_clean_law_title_strips_site_suffix():
    assert clean_law_title("Privacy Act 1988 - Federal Register of Legislation") == "Privacy Act 1988"
    assert clean_law_title("Personal Data Protection Act 2012 | SSO") == "Personal Data Protection Act 2012"
    assert clean_law_title("Some Act 2010") == "Some Act 2010"
    assert clean_law_title("") == ""


def test_extractor_prefers_detected_act_title():
    doc = CrawledDocument(
        url="https://www.legislation.gov.au/C2004A03712/latest/text",
        economy="Australia",
        text="1  Short title\nThis Act may be cited as the Privacy Act 1988.",
        title="Privacy Act 1988",
    )
    assert MockProvisionExtractor()._derive_title(doc) == "Privacy Act 1988"


def test_extractor_falls_back_when_no_title():
    doc = CrawledDocument(
        url="https://example.gov/privacy-act",
        economy="Australia",
        text="1  Short title\nbody",
    )
    # no detected title -> first substantive line (legacy behaviour preserved)
    assert MockProvisionExtractor()._derive_title(doc) == "1  Short title"
