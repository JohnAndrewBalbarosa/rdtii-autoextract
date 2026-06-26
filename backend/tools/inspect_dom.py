"""Developer-only full DOM scraper view — see exactly what the AI scrapes, in real Chrome.

Opens an actual **Chrome** window (channel="chrome", with DevTools so you can poke around
like a debugger), runs the real fetch + expand + clean pipeline, then **deletes everything
on the page except the content the AI scrapes**. What's left rendered in the window is the
literal scrape output — one view, nothing to filter.

The keep/delete decision comes from ``DomCleaner.annotate_html`` — the SAME logic the
headless production pipeline runs — so what you verify here is exactly what ships. Once it
looks right, production already runs headless; nothing to convert.

Usage:
    cd backend
    python -m tools.inspect_dom --url "https://www.legislation.gov.au/..."
    python -m tools.inspect_dom --url "<url>" --headless --out scrape.html   # no window
    python -m tools.inspect_dom --url "<url>" --no-scaffold                  # generic cleaning

This module is NOT imported by the production pipeline.
"""

from __future__ import annotations

import argparse
import sys

from adapters.botting.l4_transport.playwright_client import PlaywrightClient
from adapters.botting.l4_transport.scroll_settle import settle_page
from adapters.botting.l6_presentation.dom_cleaner import DomCleaner
from adapters.botting.scaffolds.scaffold_registry import ScaffoldRegistry
from tools.inspector_render import build_inspector_html
from tools.inspector_walkthrough import (
    build_overlay_script,
    build_walkthrough_html,
    index_kept_blocks,
)


def _resolve_selectors(url: str, use_scaffold: bool) -> tuple[str, dict | None]:
    """Return (fetch_url, selectors) using the matching scaffold, if any."""
    if not use_scaffold:
        return url, None
    scaffold = ScaffoldRegistry().get_scaffold_for_url(url)
    if scaffold is None:
        return url, None
    selectors = dict(scaffold.get_custom_selectors())
    boilerplate = scaffold.get_boilerplate_selectors()
    if boilerplate:
        selectors["boilerplate"] = boilerplate
    return scaffold.get_fetch_url(url), (selectors or None)


def _launch_chrome(p, headless: bool):
    """Prefer the real installed Chrome (with DevTools when visible); fall back to bundled."""
    try:
        return p.chromium.launch(headless=headless, channel="chrome", devtools=not headless)
    except Exception as exc:
        print(f"[inspector] real Chrome unavailable ({exc}); using bundled Chromium", file=sys.stderr)
        return p.chromium.launch(headless=headless)


def _build_inspector(
    url: str,
    *,
    use_scaffold: bool,
    headless: bool,
    walkthrough: bool = False,
    step_ms: int = 700,
) -> str:
    """Fetch + render + clean, then render the scrape view.

    Two views share one keep/drop logic (``DomCleaner.annotate_html``):
    - default: prune to ONLY the scraped content (static snapshot).
    - ``walkthrough``: keep the full page and step a highlight overlay through each
      scraped block while a debug panel narrates (live visual debugger).

    Lazy SPA content is loaded with condition-based scroll-settling (scroll/expand until
    the visible text stops growing) instead of a fixed timeout.
    """
    from playwright.sync_api import sync_playwright

    fetch_url, selectors = _resolve_selectors(url, use_scaffold)
    if not fetch_url.lower().startswith(("http://", "https://")):
        raise SystemExit("inspect_dom: only http/https URLs are supported")

    out_html = ""
    cleaner = DomCleaner()
    with sync_playwright() as p:
        browser = _launch_chrome(p, headless)
        try:
            page = browser.new_page()
            page.goto(fetch_url, wait_until="networkidle", timeout=30000)

            # Condition-based settle: scroll + expand until lazy provision text plateaus.
            lengths = settle_page(
                page,
                on_round=lambda r, n: print(
                    f"[inspector] settle round {r}: innerText {n}", flush=True
                ),
            )
            if lengths:
                print(
                    f"[inspector] settled at {lengths[-1]} chars after {len(lengths)} round(s)",
                    flush=True,
                )

            rendered_html = page.content()
            sections = cleaner.extract_sections(rendered_html, selectors)
            total_chars = sum(len(s.text) for s in sections)
            print(
                f"[inspector] scraped {len(sections)} section(s), {total_chars} chars "
                f"from {fetch_url}",
                flush=True,
            )

            annotated = cleaner.annotate_html(rendered_html, selectors)

            if walkthrough:
                out_html = _run_walkthrough(
                    page, annotated, fetch_url, headless=headless, step_ms=step_ms
                )
            else:
                out_html = build_inspector_html(annotated, source_url=fetch_url)
                page.set_content(out_html, wait_until="domcontentloaded")
                if not headless:
                    print(
                        "[inspector] Showing ONLY what the AI scrapes (everything else deleted).\n"
                        "[inspector] DevTools is open. Press Enter here to close...",
                        flush=True,
                    )
                    _wait_for_enter()
        finally:
            browser.close()

    return out_html


def _run_walkthrough(page, annotated: str, fetch_url: str, *, headless: bool, step_ms: int) -> str:
    """Repaint the full page with debugger chrome and step the overlay block by block."""
    indexed_html, manifest = index_kept_blocks(annotated)
    doc = build_walkthrough_html(indexed_html, source_url=fetch_url)
    page.set_content(doc, wait_until="domcontentloaded")

    total = len(manifest)
    print(f"[inspector] walkthrough: {total} scraped block(s) — highlighting each.", flush=True)
    for block in manifest:
        state = {
            "src": fetch_url,
            "current": block.idx + 1,
            "total": total,
            "char_count": block.char_count,
            "heading": block.heading or f"<{block.tag}>",
            "status": f"Reading block {block.idx + 1}/{total}",
            "next_action": "Next block" if block.idx + 1 < total else "Done",
            "preview": block.preview,
        }
        try:
            page.evaluate(build_overlay_script(block.idx, state))
            page.wait_for_timeout(step_ms)
        except Exception as exc:
            print(f"[inspector] walkthrough stopped at block {block.idx}: {exc}", file=sys.stderr)
            break

    if not headless:
        print(
            "[inspector] Walkthrough complete. The red box marked each scraped block.\n"
            "[inspector] DevTools is open. Press Enter here to close...",
            flush=True,
        )
        _wait_for_enter()
    return doc


def _wait_for_enter() -> None:
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="inspect_dom",
        description="Dev-only full scraper view in real Chrome: shows only what the AI scrapes.",
    )
    parser.add_argument("--url", required=True, help="Page URL to scrape and inspect.")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless (no window). Pair with --out to capture the pruned scrape HTML.",
    )
    parser.add_argument(
        "--no-scaffold",
        dest="use_scaffold",
        action="store_false",
        help="Ignore site-specific scaffold selectors; use generic cleaning only.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write the scrape-view HTML to this file.",
    )
    parser.add_argument(
        "--walkthrough",
        action="store_true",
        help="Live visual debugger: keep the full page and step a highlight overlay "
        "through each scraped block with a debug panel (instead of pruning).",
    )
    parser.add_argument(
        "--step-ms",
        type=int,
        default=700,
        help="Pause between highlighted blocks in --walkthrough mode (default 700ms).",
    )
    args = parser.parse_args(argv)

    inspector_html = _build_inspector(
        args.url,
        use_scaffold=args.use_scaffold,
        headless=args.headless,
        walkthrough=args.walkthrough,
        step_ms=args.step_ms,
    )

    if args.out and inspector_html:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(inspector_html)
        print(f"[inspector] Wrote pruned scrape HTML to {args.out}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
