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
