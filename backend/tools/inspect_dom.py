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
from adapters.botting.l6_presentation.dom_cleaner import DomCleaner
from adapters.botting.scaffolds.scaffold_registry import ScaffoldRegistry
from tools.inspector_render import build_inspector_html


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


def _build_inspector(url: str, *, use_scaffold: bool, headless: bool) -> str:
    """Fetch + render + clean + prune. Returns the scrape-view HTML document."""
    from playwright.sync_api import sync_playwright

    fetch_url, selectors = _resolve_selectors(url, use_scaffold)
    if not fetch_url.lower().startswith(("http://", "https://")):
        raise SystemExit("inspect_dom: only http/https URLs are supported")

    inspector_html = ""
    cleaner = DomCleaner()
    with sync_playwright() as p:
        browser = _launch_chrome(p, headless)
        try:
            page = browser.new_page()
            page.goto(fetch_url, wait_until="networkidle", timeout=30000)
            # Reuse the production expand pass so lazy/accordion provisions are present.
            for _ in range(2):
                try:
                    page.evaluate(PlaywrightClient._EXPAND_JS)
                    page.wait_for_timeout(1500)
                except Exception as exc:
                    print(f"[inspector] expand pass stopped: {exc}", file=sys.stderr)
                    break
            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass

            rendered_html = page.content()
            # The real scrape (same logic), for a "full scraper" summary.
            sections = cleaner.extract_sections(rendered_html, selectors)
            total_chars = sum(len(s.text) for s in sections)
            print(
                f"[inspector] scraped {len(sections)} section(s), {total_chars} chars "
                f"from {fetch_url}",
                flush=True,
            )

            annotated = cleaner.annotate_html(rendered_html, selectors)
            inspector_html = build_inspector_html(annotated, source_url=fetch_url)

            # Repaint the page with everything-but-the-scrape deleted, and hold it open.
            page.set_content(inspector_html, wait_until="domcontentloaded")
            if not headless:
                print(
                    "[inspector] Showing ONLY what the AI scrapes (everything else deleted).\n"
                    "[inspector] DevTools is open for inspection. Press Enter here to close...",
                    flush=True,
                )
                try:
                    input()
                except (EOFError, KeyboardInterrupt):
                    pass
        finally:
            browser.close()

    return inspector_html


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
        help="Write the pruned scrape HTML to this file.",
    )
    args = parser.parse_args(argv)

    inspector_html = _build_inspector(
        args.url,
        use_scaffold=args.use_scaffold,
        headless=args.headless,
    )

    if args.out and inspector_html:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(inspector_html)
        print(f"[inspector] Wrote pruned scrape HTML to {args.out}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
