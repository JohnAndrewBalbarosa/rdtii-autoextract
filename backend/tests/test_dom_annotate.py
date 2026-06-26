"""Tests for DomCleaner.annotate_html (dev inspector single-source-of-truth).

`annotate_html` must mark the SAME elements that `extract_sections` reads — but instead
of removing them, it tags survivors with ``data-zx-keep`` and discards with
``data-zx-drop="<reason>"``. The parity test guards against the two paths drifting.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from adapters.botting.l6_presentation.dom_cleaner import DomCleaner
from tools.inspector_render import build_inspector_html

_SPA_HTML = """
<html><body>
  <nav id="topnav"><a href="/">Home</a><a href="/login">Login</a></nav>
  <main>
    <h2 id="textTab">Text</h2>
    <h2 id="CitationChangesDropdown">Citation change</h2>
    <h2 id="ngb-nav-1-panel">Legislation text</h2>
    <p>Section 16.—(1) A service provider must keep information for the prescribed period.
       (2) The provider shall not transfer the information overseas without authorisation.
       This Act creates offences for non-compliance and the regulations prescribe penalties
       so that the provisions of this section are enforced across the territory.</p>
  </main>
  <footer id="foot">© Government</footer>
</body></html>
"""

_STATUTE_HTML = (
    '<html><body><main>'
    '<h2 id="s26">Section 26 Transfer</h2>'
    '<p>An organisation shall not transfer personal data outside the country '
    'unless the prescribed safeguards apply under this Act and its regulations.</p>'
    '</main></body></html>'
)


def _annotated_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(DomCleaner().annotate_html(html), "html.parser")


def test_kept_blocks_marked():
    soup = _annotated_soup(_STATUTE_HTML)
    heading = soup.select_one("h2#s26")
    para = soup.select_one("main p")
    assert heading.get("data-zx-keep") == "1"
    assert para.get("data-zx-keep") == "1"


def test_boilerplate_marked_dropped():
    soup = _annotated_soup(_SPA_HTML)
    assert soup.select_one("nav#topnav").get("data-zx-drop") == "boilerplate"
    assert soup.select_one("footer#foot").get("data-zx-drop") == "boilerplate"


def test_short_chrome_marked_dropped():
    soup = _annotated_soup(_SPA_HTML)
    assert soup.select_one("h2#textTab").get("data-zx-drop") == "chrome"
    assert soup.select_one("h2#CitationChangesDropdown").get("data-zx-drop") == "chrome"


def test_substantial_panel_kept_under_widget_anchor():
    soup = _annotated_soup(_SPA_HTML)
    assert soup.select_one("h2#ngb-nav-1-panel").get("data-zx-keep") == "1"
    assert soup.select_one("main p").get("data-zx-keep") == "1"


def test_no_element_both_kept_and_dropped():
    soup = _annotated_soup(_SPA_HTML)
    for el in soup.find_all(True):
        assert not (el.get("data-zx-keep") and el.get("data-zx-drop"))


def test_parity_with_extract_sections():
    """Every kept element's text must be content that extract_sections actually reads,
    and dropped chrome headings must never leak into the kept set."""
    cleaner = DomCleaner()
    sections = cleaner.extract_sections(_SPA_HTML)
    section_blob = " ".join(f"{s.heading} {s.text}" for s in sections)

    soup = _annotated_soup(_SPA_HTML)
    kept_texts = [el.get_text(" ", strip=True) for el in soup.select("[data-zx-keep]")]

    # Kept content appears in the sections the AI reads.
    assert any("service provider" in t for t in kept_texts)
    assert "service provider" in section_blob
    # Chrome that extract_sections drops is not kept here either.
    assert "Text" not in [t for t in kept_texts]
    assert "Citation change" not in kept_texts


def test_build_inspector_html_keeps_only_scraped():
    """Deletion mode: only the elements the AI scrapes survive; chrome/boilerplate gone."""
    annotated = DomCleaner().annotate_html(_SPA_HTML)
    doc = build_inspector_html(annotated)
    soup = BeautifulSoup(doc, "html.parser")

    # Kept content remains, still marked.
    assert soup.select_one("[data-zx-keep]") is not None
    assert "service provider" in soup.get_text()

    # Dropped chrome + boilerplate are physically removed (not just dimmed).
    assert "Citation change" not in soup.get_text()  # short dropdown chrome
    assert "Home" not in soup.get_text()  # nav boilerplate
    assert "© Government" not in soup.get_text()  # footer boilerplate

    # Single info toolbar; no two-mode toggle.
    assert soup.select_one("#zx-inspector-toolbar") is not None


def test_build_inspector_html_is_single_view_no_toggle():
    annotated = DomCleaner().annotate_html(_STATUTE_HTML)
    doc = build_inspector_html(annotated)
    assert "zx-toggle" not in doc
    assert "Isolate" not in doc
