"""Tests for the live-walkthrough pure logic (tools/inspector_walkthrough.py).

The live visual debugger drives a browser, but the addressable manifest and the
injected JS are built by pure functions so they stay deterministic and unit-testable
without launching Chrome. These guard the contract the headed driver relies on.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from adapters.botting.l6_presentation.dom_cleaner import DomCleaner
from tools.inspector_walkthrough import (
    KeptBlock,
    build_autoplay_html,
    build_interactive_html,
    build_overlay_script,
    build_walkthrough_css,
    build_walkthrough_html,
    index_kept_blocks,
)

_STATUTE_HTML = (
    "<html><body><main>"
    '<h2 id="s26">Section 26 Transfer</h2>'
    "<p>An organisation shall not transfer personal data outside the country "
    "unless the prescribed safeguards apply under this Act and its regulations.</p>"
    '<h2 id="s27">Section 27 Retention</h2>'
    "<p>The provider shall keep the personal information only for the prescribed "
    "period and shall destroy it once the purpose has been fulfilled under the Act.</p>"
    "</main></body></html>"
)


def _annotated(html: str = _STATUTE_HTML) -> str:
    return DomCleaner().annotate_html(html)


def test_index_assigns_sequential_idx_to_kept_only():
    html, manifest = index_kept_blocks(_annotated())
    soup = BeautifulSoup(html, "html.parser")

    indexed = soup.select("[data-zx-idx]")
    # Every indexed element is a kept block, and nothing dropped got an index.
    assert all(el.get("data-zx-keep") == "1" for el in indexed)
    assert soup.select("[data-zx-drop][data-zx-idx]") == []

    idxs = [int(el["data-zx-idx"]) for el in indexed]
    assert idxs == list(range(len(idxs)))  # sequential, document order
    assert [b.idx for b in manifest] == idxs


def test_manifest_reports_char_count_and_preview():
    _, manifest = index_kept_blocks(_annotated())
    assert manifest, "expected at least one kept block"
    para = next(b for b in manifest if b.tag == "p")
    assert isinstance(para, KeptBlock)
    # char_count is the full text length; preview is a (possibly truncated) excerpt of it.
    assert para.char_count >= len(para.preview.rstrip("…"))
    assert para.char_count > 50  # the statute paragraph is substantial
    assert para.preview.strip()  # non-empty human preview


def test_manifest_carries_anchor_and_path_when_present():
    _, manifest = index_kept_blocks(_annotated())
    headings = [b for b in manifest if b.tag in {"h1", "h2", "h3", "h4"}]
    assert headings, "expected heading blocks"
    assert any(b.anchor for b in headings)


def test_overlay_script_targets_idx_and_updates_panel():
    state = {
        "status": "Reading block",
        "next_action": "Next block",
        "current": 3,
        "total": 10,
        "heading": "Section 26 Transfer",
        "char_count": 142,
    }
    js = build_overlay_script(3, state)
    assert 'data-zx-idx="3"' in js or "data-zx-idx='3'" in js
    # Panel must surface the live state the operator watches.
    assert "Reading block" in js
    assert "Next block" in js
    assert "Section 26 Transfer" in js
    # Overlay uses a floating rect (getBoundingClientRect), not element mutation.
    assert "getBoundingClientRect" in js


def test_overlay_script_escapes_quotes_in_state():
    js = build_overlay_script(0, {"status": 'He said "stop"', "heading": "A's law"})
    # Must not break out of the JS string literal.
    assert "He said" in js
    assert "\\" in js  # some escaping happened


def test_walkthrough_css_has_panel_and_overlay():
    css = build_walkthrough_css()
    assert "#zx-debug-panel" in css
    assert "#zx-overlay" in css


def test_build_autoplay_html_embeds_all_states_and_stepper():
    indexed_html, manifest = index_kept_blocks(_annotated())
    doc = build_autoplay_html(indexed_html, manifest, source_url="https://x.test", step_ms=500)
    # In-page stepper present and self-contained (no Python driver needed).
    assert "setInterval" in doc
    assert "ZX_STATES" in doc
    assert "getBoundingClientRect" in doc
    # Every scraped block has a state to play.
    assert doc.count('"idx"') == len(manifest)
    # Chrome from the base walkthrough is retained.
    soup = BeautifulSoup(doc, "html.parser")
    assert soup.select_one("#zx-debug-panel") is not None
    assert soup.select_one("#zx-overlay") is not None


def test_build_interactive_html_color_codes_and_click_inspects():
    annotated = DomCleaner().annotate_html(_STATUTE_HTML)
    doc = build_interactive_html(annotated, source_url="https://x.test/law")
    soup = BeautifulSoup(doc, "html.parser")

    # DevTools-style click handler + info panel, no narrating sidebar.
    assert soup.select_one("#zx-info") is not None
    assert soup.select_one("#zx-legend") is not None
    assert soup.select_one("#zx-debug-panel") is None
    assert "addEventListener('click'" in doc
    assert "data-zx-drop" in doc  # handler reads the skip reason
    # Keep/skip styling is present.
    assert "[data-zx-keep]" in doc
    assert "[data-zx-drop]" in doc
    # Page content preserved (you inspect the real page, kept blocks still marked).
    assert soup.select_one("[data-zx-keep]") is not None
    assert "transfer personal data" in soup.get_text()


def test_build_interactive_html_renders_correctly_offsite():
    """<base href> for relative assets; site scripts stripped so the SPA can't clobber."""
    html = (
        "<html><head><link rel='stylesheet' href='/app.css'></head><body><main>"
        '<h2 id="s1">Section 1</h2>'
        "<p>An organisation shall not transfer personal data outside the country "
        "unless the prescribed safeguards apply under this Act and its regulations.</p>"
        "<script>window.__spa_boot()</script>"
        "</main></body></html>"
    )
    annotated = DomCleaner().annotate_html(html)
    doc = build_interactive_html(annotated, source_url="https://gov.test/law/1")
    soup = BeautifulSoup(doc, "html.parser")

    base = soup.find("base")
    assert base is not None and base.get("href") == "https://gov.test/law/1"
    # The site stylesheet is kept (so it renders), the site script is gone.
    assert soup.find("link", attrs={"rel": "stylesheet"}) is not None
    assert "__spa_boot" not in doc
    # Only our own inspector script remains.
    assert len(soup.find_all("script")) == 1


def test_build_walkthrough_html_keeps_full_page_and_injects_chrome():
    indexed_html, _ = index_kept_blocks(_annotated())
    doc = build_walkthrough_html(indexed_html, source_url="https://example.test/law")
    soup = BeautifulSoup(doc, "html.parser")

    # Nothing deleted — the real page (incl. its content) is preserved for context.
    assert "transfer personal data" in soup.get_text()
    # Debugger chrome is injected.
    assert soup.select_one("#zx-overlay") is not None
    assert soup.select_one("#zx-debug-panel") is not None
    assert soup.select_one("[data-zx-idx]") is not None
