"""Pure logic for the live visual debugger ("scrape walkthrough").

The headed driver in ``tools.inspect_dom`` walks the kept blocks one by one, drawing a
floating overlay over each and updating a debug panel — so you literally *see* what the
scraper reads, in order, the way a DevTools inspector highlights elements. The browser
work lives in the driver; the addressable manifest and the injected JS are built here so
they stay deterministic and unit-testable without launching Chrome.

Single source of truth: blocks come from ``DomCleaner.annotate_html`` (``data-zx-keep``),
the exact same keep/drop logic the headless production pipeline uses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from bs4 import BeautifulSoup

_HEADING_TAGS = {"h1", "h2", "h3", "h4"}
_PREVIEW_CHARS = 90


@dataclass(frozen=True)
class KeptBlock:
    """One element the scraper reads, addressable in the browser via ``data-zx-idx``."""

    idx: int
    tag: str
    heading: str  # nearest breadcrumb/path label, or the block's own heading text
    char_count: int  # full visible-text length
    anchor: str | None  # in-page anchor id, when known
    path: str  # " › "-joined heading breadcrumb, or ""
    preview: str  # short human-readable excerpt


def index_kept_blocks(annotated_html: str) -> tuple[str, list[KeptBlock]]:
    """Tag each kept block with a sequential ``data-zx-idx`` and return (html, manifest).

    Indexing follows document order so the walkthrough advances top-to-bottom, matching
    the order the AI reads sections. Dropped/boilerplate elements are never indexed.
    """
    soup = BeautifulSoup(annotated_html, "html.parser")
    manifest: list[KeptBlock] = []

    for idx, element in enumerate(soup.select("[data-zx-keep]")):
        element["data-zx-idx"] = str(idx)
        text = element.get_text(" ", strip=True)
        tag = (element.name or "").lower()
        path = element.get("data-zx-path") or ""
        heading = text if tag in _HEADING_TAGS else path
        manifest.append(
            KeptBlock(
                idx=idx,
                tag=tag,
                heading=heading,
                char_count=len(text),
                anchor=element.get("data-zx-anchor"),
                path=path,
                preview=_preview(text),
            )
        )

    return str(soup), manifest


def _preview(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= _PREVIEW_CHARS:
        return text
    return text[:_PREVIEW_CHARS].rstrip() + "…"


def build_walkthrough_css() -> str:
    """Styles for the floating overlay box and the side debug panel."""
    return """
#zx-overlay{
  position:fixed; z-index:2147483646; pointer-events:none;
  border:3px solid #dc2626; background:rgba(220,38,38,.12);
  border-radius:4px; box-shadow:0 0 0 9999px rgba(2,6,23,.04);
  transition:all .18s ease;
}
#zx-debug-panel{
  position:fixed; top:12px; right:12px; z-index:2147483647; width:300px;
  font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; color:#0f172a;
  background:#fff; border:1px solid #cbd5e1; border-radius:10px;
  box-shadow:0 8px 24px rgba(2,6,23,.18); padding:12px 14px;
}
#zx-debug-panel h4{ margin:0 0 8px; font:600 13px system-ui,sans-serif; }
#zx-debug-panel .row{ display:flex; justify-content:space-between; gap:8px; }
#zx-debug-panel .row span:last-child{ font-variant-numeric:tabular-nums; color:#1d4ed8; }
#zx-debug-panel .status{ margin-top:8px; padding-top:8px; border-top:1px solid #e2e8f0; }
#zx-debug-panel .preview{ margin-top:6px; color:#475569; font-size:11px;
  max-height:48px; overflow:hidden; }
"""


_PANEL_HTML = """
<div id="zx-debug-panel">
  <h4>Zetarix Scrape Debugger</h4>
  <div class="row"><span>Source</span><span id="zx-src"></span></div>
  <div class="row"><span>Block</span><span id="zx-current"></span></div>
  <div class="row"><span>Chars</span><span id="zx-chars"></span></div>
  <div class="row"><span>Heading</span><span id="zx-heading"></span></div>
  <div class="status"><strong id="zx-status"></strong></div>
  <div class="status"><span>Next: </span><span id="zx-next"></span></div>
  <div class="preview" id="zx-preview"></div>
</div>
"""


def panel_html() -> str:
    """The debug-panel markup injected once before the walkthrough starts."""
    return _PANEL_HTML


def build_walkthrough_html(annotated_indexed_html: str, *, source_url: str = "") -> str:
    """Wrap the (full, non-pruned) annotated+indexed page with the overlay + debug panel.

    Unlike ``build_inspector_html``, nothing is deleted: the operator sees the real page
    and watches the highlight box jump from one scraped block to the next while the panel
    narrates. ``data-zx-idx`` addresses each kept block for ``build_overlay_script``.
    """
    soup = BeautifulSoup(annotated_indexed_html, "html.parser")

    html_tag = soup.find("html")
    head = soup.find("head")
    if head is None:
        head = soup.new_tag("head")
        (html_tag or soup).insert(0, head)
    body = soup.find("body")
    if body is None:
        body = soup.new_tag("body")
        (html_tag or soup).append(body)

    style = soup.new_tag("style")
    style.string = build_walkthrough_css()
    head.append(style)

    overlay = soup.new_tag("div", id="zx-overlay")
    body.append(overlay)
    body.append(BeautifulSoup(panel_html(), "html.parser"))
    if source_url:
        body.append(BeautifulSoup(f'<div data-zx-src="{source_url}" hidden></div>', "html.parser"))
    return str(soup)


def build_overlay_script(idx: int, state: dict) -> str:
    """JS that positions the overlay over ``[data-zx-idx=idx]`` and refreshes the panel.

    Uses ``getBoundingClientRect`` to place a floating box (an overlay layer) rather than
    mutating the target element's own styles, so the page layout is never disturbed.
    State values are JSON-encoded, which safely escapes quotes and backslashes.
    """
    s = json.dumps(
        {
            "src": str(state.get("src", "")),
            "current": f"{state.get('current', '?')} / {state.get('total', '?')}",
            "chars": str(state.get("char_count", "")),
            "heading": str(state.get("heading", "")),
            "status": str(state.get("status", "")),
            "next": str(state.get("next_action", "")),
            "preview": str(state.get("preview", "")),
        }
    )
    return f"""(() => {{
  const S = {s};
  const set = (id, v) => {{ const e = document.getElementById(id); if (e) e.textContent = v; }};
  set('zx-src', S.src); set('zx-current', S.current); set('zx-chars', S.chars);
  set('zx-heading', S.heading); set('zx-status', S.status); set('zx-next', S.next);
  set('zx-preview', S.preview);
  const el = document.querySelector('[data-zx-idx="{idx}"]');
  const ov = document.getElementById('zx-overlay');
  if (el && ov) {{
    el.scrollIntoView({{behavior:'smooth', block:'center'}});
    const r = el.getBoundingClientRect();
    ov.style.left = r.left + 'px'; ov.style.top = r.top + 'px';
    ov.style.width = r.width + 'px'; ov.style.height = r.height + 'px';
  }}
}})();"""
