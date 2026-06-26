"""Pure deletion renderer for the dev DOM inspector ("scrape view").

Takes HTML already annotated by ``DomCleaner.annotate_html`` (the elements the AI reads
carry ``data-zx-keep``) and **removes everything else** — every node that is neither a
kept element, an ancestor of one, nor a descendant of one. What remains, rendered in a
real Chrome window, is exactly what the scraper extracts: one thing to look at, no toggle,
no mental filtering.

Pruning happens in Python (BeautifulSoup), so the result is deterministic and unit-testable
without launching a browser, and a saved ``--out`` file is already the pruned scrape.
"""

from __future__ import annotations

from bs4 import BeautifulSoup
from bs4.element import Tag

# Faint outline just to delineate the surviving blocks; everything else is already gone.
_VIEW_CSS = """
[data-zx-keep]{ outline:1px solid rgba(22,163,74,.45) !important; }
#zx-inspector-toolbar{
  position:fixed; top:12px; right:12px; z-index:2147483647;
  font:13px/1.4 system-ui,sans-serif; color:#0f172a;
  background:#fff; border:1px solid #cbd5e1; border-radius:10px;
  box-shadow:0 8px 24px rgba(2,6,23,.18); padding:12px 14px; max-width:320px;
}
#zx-inspector-toolbar strong{ display:block; margin-bottom:6px; }
#zx-counts{ display:block; font-variant-numeric:tabular-nums; }
#zx-legend{ display:block; margin-top:4px; font-size:11px; color:#64748b; }
"""


def _prune_to_kept(soup: BeautifulSoup) -> int:
    """Remove every node outside the kept set; return the kept-block count.

    Kept = elements marked ``data-zx-keep``, their ancestor chain (so they still render),
    and their descendants (the text itself). Everything else is decomposed.
    """
    kept_blocks = soup.select("[data-zx-keep]")

    preserved: set[int] = set()
    for element in kept_blocks:
        node: Tag | None = element
        while node is not None:
            preserved.add(id(node))
            node = node.parent

    for element in list(soup.find_all(True)):
        if id(element) in preserved:
            continue
        if element.find_parent(attrs={"data-zx-keep": True}) is not None:
            continue
        element.decompose()

    return len(kept_blocks)


def build_inspector_html(annotated_html: str, *, source_url: str = "") -> str:
    """Prune annotated HTML down to the scraped content and add a small info toolbar.

    Args:
        annotated_html: HTML whose AI-read elements carry ``data-zx-keep``.
        source_url: optional label shown in the toolbar.

    Returns:
        A complete HTML document containing only what the scraper extracts.
    """
    soup = BeautifulSoup(annotated_html, "html.parser")

    body = soup.find("body")
    if body is None:
        skeleton = BeautifulSoup("<html><head></head><body></body></html>", "html.parser")
        skeleton.body.append(soup)
        soup = skeleton
        body = soup.find("body")

    html_tag = soup.find("html")
    head = soup.find("head")
    if head is None:
        head = soup.new_tag("head")
        (html_tag or soup).insert(0, head)

    kept_count = _prune_to_kept(soup)

    style = soup.new_tag("style")
    style.string = _VIEW_CSS
    head.append(style)

    toolbar = soup.new_tag("div", id="zx-inspector-toolbar")
    title = soup.new_tag("strong")
    title.string = "Zetarix Scrape View"
    toolbar.append(title)
    counts = soup.new_tag("span", id="zx-counts")
    counts.string = f"scraped {kept_count} block(s) — everything else removed"
    toolbar.append(counts)
    legend = soup.new_tag("span", id="zx-legend")
    legend.string = source_url or "only what the AI scrapes remains"
    toolbar.append(legend)
    body.append(toolbar)

    return str(soup)
