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


def build_autoplay_html(
    annotated_indexed_html: str,
    manifest: list[KeptBlock],
    *,
    source_url: str = "",
    step_ms: int = 700,
) -> str:
    """Self-contained walkthrough that auto-steps in the browser (no Python driver).

    Embeds the per-block states + an in-page stepper so the file can be opened directly
    (or served headless) and the red overlay walks every scraped block on a loop while the
    debug panel narrates. Same overlay/panel chrome as the live driver.
    """
    doc = build_walkthrough_html(annotated_indexed_html, source_url=source_url)
    soup = BeautifulSoup(doc, "html.parser")
    body = soup.find("body")

    total = len(manifest)
    states = [
        {
            "idx": b.idx,
            "src": source_url,
            "current": f"{b.idx + 1} / {total}",
            "chars": str(b.char_count),
            "heading": b.heading or f"<{b.tag}>",
            "status": f"Reading block {b.idx + 1}/{total}",
            "next": "Next block" if b.idx + 1 < total else "Loop restart",
            "preview": b.preview,
        }
        for b in manifest
    ]
    script = soup.new_tag("script")
    script.string = f"""
const ZX_STATES = {json.dumps(states)};
const ZX_STEP = {int(step_ms)};
(() => {{
  const set = (id, v) => {{ const e = document.getElementById(id); if (e) e.textContent = v; }};
  let i = 0;
  const tick = () => {{
    if (!ZX_STATES.length) return;
    const S = ZX_STATES[i % ZX_STATES.length];
    set('zx-src', S.src); set('zx-current', S.current); set('zx-chars', S.chars);
    set('zx-heading', S.heading); set('zx-status', S.status); set('zx-next', S.next);
    set('zx-preview', S.preview);
    const el = document.querySelector('[data-zx-idx="' + S.idx + '"]');
    const ov = document.getElementById('zx-overlay');
    if (el && ov) {{
      el.scrollIntoView({{behavior:'smooth', block:'center'}});
      const r = el.getBoundingClientRect();
      ov.style.left = r.left + 'px'; ov.style.top = r.top + 'px';
      ov.style.width = r.width + 'px'; ov.style.height = r.height + 'px';
    }}
    i++;
  }};
  tick();
  setInterval(tick, ZX_STEP);
}})();
"""
    body.append(script)
    return str(soup)


_INTERACTIVE_CSS = """
[data-zx-keep]{ outline:2px solid #16a34a !important; background:rgba(22,163,74,.08) !important;
  cursor:pointer; }
[data-zx-keep]:hover{ outline-width:3px !important; background:rgba(22,163,74,.20) !important; }
[data-zx-drop]{ opacity:.4; outline:1px dashed #ef4444 !important; cursor:pointer; }
[data-zx-drop]:hover{ opacity:.9; }
#zx-info{ position:fixed; z-index:2147483647; display:none; max-width:340px;
  font:12px/1.5 ui-monospace,Menlo,monospace; color:#0f172a; background:#fff;
  border:1px solid #cbd5e1; border-radius:8px; box-shadow:0 8px 24px rgba(2,6,23,.22);
  padding:10px 12px; }
#zx-info .v{ font-weight:600; }
#zx-info .kept{ color:#16a34a; } #zx-info .skip{ color:#dc2626; }
#zx-legend{ position:fixed; top:12px; left:12px; z-index:2147483647;
  font:12px/1.4 system-ui,sans-serif; color:#0f172a; background:#fff; border:1px solid #cbd5e1;
  border-radius:8px; box-shadow:0 4px 14px rgba(2,6,23,.16); padding:8px 10px; }
#zx-legend b{ display:block; margin-bottom:4px; }
#zx-legend .g{ color:#16a34a; } #zx-legend .r{ color:#dc2626; }
"""

_INTERACTIVE_JS = """
(() => {
  const box = document.getElementById('zx-info');
  const REASONS = {
    'boilerplate': 'boilerplate — nav / footer / script / form',
    'chrome': 'short UI chrome — tab / dropdown / menu',
    'outside-content': 'outside the legal content area',
  };
  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-zx-keep],[data-zx-drop]');
    if (!el) { box.style.display = 'none'; return; }
    e.preventDefault(); e.stopPropagation();
    const kept = el.hasAttribute('data-zx-keep');
    const reason = el.getAttribute('data-zx-drop') || '';
    const len = (el.innerText || '').trim().length;
    const path = el.getAttribute('data-zx-path') || '';
    const anchor = el.getAttribute('data-zx-anchor') || '';
    const tag = el.tagName.toLowerCase();
    let h = kept
      ? '<div class="v kept">\\u2713 SCRAPED</div>'
      : '<div class="v skip">\\u2717 SKIPPED</div><div>' + (REASONS[reason] || reason) + '</div>';
    h += '<div>&lt;' + tag + '&gt; \\u00b7 ' + len + ' chars</div>';
    if (kept && path) h += '<div>Path: ' + path + '</div>';
    if (kept && anchor) h += '<div>Anchor: #' + anchor + '</div>';
    box.innerHTML = h;
    const x = Math.min(e.clientX + 12, window.innerWidth - 360);
    const y = Math.min(e.clientY + 12, window.innerHeight - 120);
    box.style.left = x + 'px'; box.style.top = y + 'px'; box.style.display = 'block';
  }, true);
})();
"""


def build_interactive_html(annotated_html: str, *, source_url: str = "") -> str:
    """DevTools-style click-to-inspect view: click any element to see scraped vs skipped.

    Every block is colour-coded from ``DomCleaner.annotate_html``: kept blocks get a green
    outline, skipped blocks are dimmed with a red dashed outline. Clicking a block pops a
    small info box (like the DevTools element panel) stating SCRAPED, or SKIPPED + the
    reason — so you see exactly which divs the scraper checks and which it drops. No
    narrating sidebar; just a legend and the on-click panel.
    """
    soup = BeautifulSoup(annotated_html, "html.parser")

    # Drop the site's own scripts so the SPA can't re-render over our annotations; the
    # rendered DOM + stylesheets stay, so the page still looks like itself.
    for script_tag in soup.find_all("script"):
        script_tag.decompose()

    html_tag = soup.find("html")
    head = soup.find("head")
    if head is None:
        head = soup.new_tag("head")
        (html_tag or soup).insert(0, head)
    body = soup.find("body")
    if body is None:
        body = soup.new_tag("body")
        (html_tag or soup).append(body)

    # A <base href> makes the page's relative CSS/font/image URLs resolve against the real
    # origin, so it renders correctly whether opened live or as a saved file.
    if source_url:
        head.insert(0, soup.new_tag("base", href=source_url))

    style = soup.new_tag("style")
    style.string = _INTERACTIVE_CSS
    head.append(style)

    legend = (
        '<div id="zx-legend"><b>Zetarix · click any block</b>'
        '<span class="g">█ scraped</span> &nbsp; <span class="r">█ skipped</span>'
        + (f"<div>{source_url}</div>" if source_url else "")
        + "</div>"
    )
    body.append(BeautifulSoup(legend, "html.parser"))
    body.append(BeautifulSoup('<div id="zx-info"></div>', "html.parser"))

    script = soup.new_tag("script")
    script.string = _INTERACTIVE_JS
    body.append(script)
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
