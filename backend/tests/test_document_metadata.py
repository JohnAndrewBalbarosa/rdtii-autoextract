"""Tests for document metadata extraction."""

from __future__ import annotations

from datetime import date

from zetarix.extraction.document_metadata import (
    extract_act_title,
    extract_document_metadata,
    extract_last_update,
)


def test_skips_home_chrome_title():
    text = "Home\n\nPersonal Data Protection Act 2012\n\nSection 26 Transfer"
    assert extract_act_title(text) == "Personal Data Protection Act 2012"


def test_extracts_caps_act_heading():
    text = "Home\nCOMPANIES ACT 1967\nAn Act relating to companies"
    assert "Companies Act 1967" in extract_act_title(text) or "COMPANIES ACT 1967" in extract_act_title(text)


def test_extract_last_update_from_amendment_phrase():
    text = "Privacy Act 1988\nSince December 1988, last amended on 1 October 2024\nSection 1"
    assert extract_last_update(text) == date(2024, 10, 1)


def test_metadata_bundle():
    text = (
        "Personal Data Protection Act 2012\n"
        "Last amended on 1 February 2021\n"
        "Section 26 Transfer limitation obligation\n"
        "An organisation must not transfer personal data outside Singapore."
    )
    meta = extract_document_metadata(text, url="https://sso.agc.gov.sg/Act/PDPA2012")
    assert "Personal Data Protection Act 2012" in meta.act_title
    assert meta.last_update is not None
    assert meta.last_update.year == 2021
