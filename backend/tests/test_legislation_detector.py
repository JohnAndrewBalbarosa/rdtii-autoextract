"""Tests for the legislative-content detector (HTML boundary guard)."""

from __future__ import annotations

from core.pipeline.legislation_detector import (
    is_legislative,
    legislative_score,
    legislative_signals,
)

_STATUTE = (
    "Section 26.—(1) An organisation shall not transfer any personal data to a country or "
    "territory outside Singapore except in accordance with requirements prescribed under "
    "this Act. (2) Subsection (1) does not apply where the individual consents. "
    "Section 24. An organisation must protect personal data. The Act creates offences."
)
_LANDING = (
    "Personal Data Protection Department. Announcements. Job vacancy advertisement for "
    "MySTEP personnel. Re-advertisement of quotation for rental services. Contact us."
)
_NEWS = (
    "The Minister announced a new strategy today. Read more about our cyber security work "
    "and the latest updates on this page. Contact us for further details."
)


def test_statute_is_legislative():
    assert is_legislative(_STATUTE) is True
    assert legislative_score(_STATUTE) > 0.3


def test_landing_page_rejected():
    assert is_legislative(_LANDING) is False
    assert legislative_score(_LANDING) < 0.2


def test_news_page_rejected():
    assert is_legislative(_NEWS) is False


def test_empty_text_not_legislative():
    assert is_legislative("") is False
    assert legislative_score("") == 0.0


def test_signals_counts_section_markers():
    sig = legislative_signals(_STATUTE)
    assert sig["section_markers"] >= 2
    assert sig["legal_terms"] >= 2


def test_single_stray_section_mention_not_enough():
    # "section" once + no legislative diction → not legislative.
    text = "Visit the careers section of our website for current openings."
    assert is_legislative(text) is False
