"""Tests for SPA UI-chrome filtering in DomCleaner.extract_sections.

Short nav/tab/dropdown blocks are dropped; substantial text is kept even under a
widget-like anchor (e.g. the legislation.gov.au text panel).
"""

from __future__ import annotations

from adapters.botting.l6_presentation.dom_cleaner import DomCleaner

_SPA_HTML = """
<html><body><main>
  <h2 id="textTab">Text</h2>
  <h2 id="CitationChangesDropdown">Citation change</h2>
  <h2 id="ngb-nav-1-panel">Legislation text</h2>
  <p>Section 16.—(1) A service provider must keep information for the prescribed period.
     (2) The provider shall not transfer the information overseas without authorisation.
     This Act creates offences for non-compliance and the regulations prescribe penalties
     so that the provisions of this section are enforced across the territory.</p>
</main></body></html>
"""


def test_short_nav_tabs_dropped():
    sections = DomCleaner().extract_sections(_SPA_HTML)
    headings = [s.heading for s in sections]
    assert "Text" not in headings  # short nav tab dropped
    assert "Citation change" not in headings  # short dropdown dropped


def test_substantial_panel_kept_under_widget_anchor():
    sections = DomCleaner().extract_sections(_SPA_HTML)
    kept = [s for s in sections if s.heading == "Legislation text"]
    assert kept, "the real text panel must be kept despite the ngb-nav-*-panel anchor"
    assert "service provider" in kept[0].text


def test_clean_statute_sections_unaffected():
    html = (
        '<html><body><main>'
        '<h2 id="s26">Section 26 Transfer</h2>'
        '<p>An organisation shall not transfer personal data outside the country.</p>'
        '</main></body></html>'
    )
    sections = DomCleaner().extract_sections(html)
    assert any(s.anchor == "s26" and "transfer" in s.text.lower() for s in sections)
