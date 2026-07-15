from __future__ import annotations

import logging
import os
from collections import Counter

from bs4 import BeautifulSoup

_LOG = logging.getLogger(__name__)
_DEBUG_ENV = "ZETARIX_DEBUG_DOM"

class DomCleaner:
    """OSI Layer 6 (Presentation): Translates raw HTML bytes/strings into clean, readable text."""

    def clean_html(self, html_content: str, selectors: dict[str, str] = None) -> str:
        """Strips boilerplate and returns clean text."""
        soup = BeautifulSoup(html_content, "html.parser")
        debug_enabled = self._debug_enabled()

        # If content_area selector is provided, try to find it
        main_content = None
        content_selector = None
        if selectors and "content_area" in selectors:
            content_selector = selectors["content_area"]
            main_content = soup.select_one(content_selector)

        if not main_content:
            main_content = soup.find("main") or soup.find("article") or soup.find("body") or soup

        texts = []
        kept_tags: Counter[str] = Counter()
        skipped: Counter[str] = Counter()

        # Use custom sections selector if available, else default to standard tags
        if selectors and "sections" in selectors:
            section_selector = selectors["sections"]
            elements = main_content.select(section_selector)
        else:
            section_selector = "h1,h2,h3,p,li"
            elements = main_content.find_all(['h1', 'h2', 'h3', 'p', 'li'])

        for element in elements:
            kept_tags[element.name or "unknown"] += 0
            classes = set(element.get("class") or [])
            if any(name.startswith(("TOC", "ENote", "Header")) for name in classes):
                skipped[f"class:{','.join(sorted(classes)) or 'unknown'}"] += 1
                continue
            text = element.get_text(" ", strip=True)
            if not text:
                skipped["empty_text"] += 1
                continue
            lowered = text.lower()
            if lowered in {"contents", "about this compilation", "this compilation"}:
                skipped[f"boilerplate:{lowered}"] += 1
                continue
            texts.append(text)
            kept_tags[element.name or "unknown"] += 1

        cleaned = "\n".join(texts)
        if debug_enabled:
            self._log_cleaning_summary(
                content_selector=content_selector,
                section_selector=section_selector,
                kept_tags=kept_tags,
                skipped=skipped,
                cleaned=cleaned,
            )
        return cleaned

    def discover_links(self, html_content: str, selectors: dict[str, str]) -> dict[str, list[str]]:
        """Extracts PDF and internal article links based on the provided selectors."""
        soup = BeautifulSoup(html_content, "html.parser")
        results = {
            "pdf_links": [],
            "article_links": []
        }
        
        if not selectors:
            return results

        if "pdf_links" in selectors:
            for link in soup.select(selectors["pdf_links"]):
                href = link.get("href")
                if href:
                    results["pdf_links"].append(href)

        if "article_links" in selectors:
            for link in soup.select(selectors["article_links"]):
                href = link.get("href")
                if href:
                    results["article_links"].append(href)
                    
        # Remove duplicates
        results["pdf_links"] = list(set(results["pdf_links"]))
        results["article_links"] = list(set(results["article_links"]))

        return results

    def _debug_enabled(self) -> bool:
        return os.environ.get(_DEBUG_ENV, "").strip().lower() in {"1", "true", "yes", "on"}

    def _log_cleaning_summary(
        self,
        *,
        content_selector: str | None,
        section_selector: str,
        kept_tags: Counter[str],
        skipped: Counter[str],
        cleaned: str,
    ) -> None:
        preview = cleaned[:300].replace("\n", " | ")
        kept_summary = {tag: count for tag, count in kept_tags.items() if count}
        _LOG.info(
            "DomCleaner content_selector=%s section_selector=%s kept_tags=%s skipped=%s preview=%r",
            content_selector or "auto(main/article/body)",
            section_selector,
            kept_summary,
            dict(skipped),
            preview,
        )
