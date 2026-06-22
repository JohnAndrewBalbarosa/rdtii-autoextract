from bs4 import BeautifulSoup

from core.domain.document import HtmlSection

class DomCleaner:
    """OSI Layer 6 (Presentation): Translates raw HTML bytes/strings into clean, readable text."""

    def clean_html(self, html_content: str, selectors: dict | None = None) -> str:
        """Strips boilerplate and returns clean text."""
        soup = BeautifulSoup(html_content, "html.parser")
        self._strip_boilerplate(soup, selectors.get("boilerplate") if selectors else None)
        
        # If content_area selector is provided, try to find it
        main_content = None
        if selectors and "content_area" in selectors:
            main_content = self._select_first_by_priority(soup, selectors["content_area"])
        
        if not main_content:
            main_content = soup.find("main") or soup.find("article") or soup.find("body") or soup

        texts = []
        
        # Use custom sections selector if available, else default to standard tags
        if selectors and "sections" in selectors:
            elements = main_content.select(selectors["sections"])
        else:
            elements = main_content.find_all(['h1', 'h2', 'h3', 'p', 'li'])
        
        for element in elements:
            texts.append(element.get_text(strip=True))
            
        return "\n".join(texts)

    def extract_sections(self, html_content: str, selectors: dict | None = None) -> list[HtmlSection]:
        """Extract legal-content sections with anchors and heading breadcrumbs."""
        soup = BeautifulSoup(html_content, "html.parser")
        self._strip_boilerplate(soup, selectors.get("boilerplate") if selectors else None)
        main_content = self._content_area(soup, selectors)

        selected_ids: set[int] = set()
        if selectors and selectors.get("sections"):
            try:
                selected_ids = {id(element) for element in main_content.select(selectors["sections"])}
            except Exception:
                selected_ids = set()

        elements = []
        block_tags = {"h1", "h2", "h3", "h4", "p", "li"}
        for element in main_content.find_all(True):
            name = (element.name or "").lower()
            is_standard_block = name in block_tags
            is_custom_block = id(element) in selected_ids and not self._has_nested_standard_block(element)
            if is_standard_block or is_custom_block:
                elements.append(element)

        sections: list[HtmlSection] = []
        heading_stack: list[tuple[int, str]] = []
        current_heading = ""
        current_anchor: str | None = None
        current_path: tuple[str, ...] = ()
        current_text: list[str] = []

        def emit_current() -> None:
            text = "\n".join(part for part in current_text if part)
            if current_heading or text:
                sections.append(
                    HtmlSection(
                        heading=current_heading,
                        text=text,
                        anchor=current_anchor,
                        path=current_path,
                    )
                )

        for element in elements:
            text = element.get_text(" ", strip=True)
            if not text:
                continue
            name = (element.name or "").lower()
            if name in {"h1", "h2", "h3", "h4"}:
                emit_current()
                level = int(name[1])
                heading_stack = [(stack_level, value) for stack_level, value in heading_stack if stack_level < level]
                heading_stack.append((level, text))
                current_heading = text
                current_anchor = self._nearest_anchor(element)
                current_path = tuple(value for _, value in heading_stack)
                current_text = []
            else:
                if not current_heading and not current_text:
                    current_anchor = self._nearest_anchor(element)
                    current_path = ()
                current_text.append(text)

        emit_current()
        return sections

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

    def _content_area(self, soup, selectors: dict | None):
        if selectors and "content_area" in selectors:
            main_content = self._select_first_by_priority(soup, selectors["content_area"])
            if main_content:
                return main_content
        return soup.find("main") or soup.find("article") or soup.find("body") or soup

    def _select_first_by_priority(self, soup, selector_list: str):
        for selector in selector_list.split(","):
            selector = selector.strip()
            if not selector:
                continue
            try:
                match = soup.select_one(selector)
            except Exception:
                continue
            if match is not None:
                return match
        return None

    def _strip_boilerplate(self, soup, extra_selectors=None) -> None:
        selectors = [
            "script",
            "style",
            "noscript",
            "nav",
            "footer",
            "aside",
            "form",
            "[role='navigation']",
            "[role='search']",
            "[role='banner']",
            "[role='contentinfo']",
        ]
        if isinstance(extra_selectors, str):
            selectors.append(extra_selectors)
        elif extra_selectors:
            selectors.extend(extra_selectors)

        for selector in selectors:
            try:
                matches = list(soup.select(selector))
            except Exception:
                continue
            for element in matches:
                element.decompose()

    def _nearest_anchor(self, element) -> str | None:
        anchor = element.get("id") if hasattr(element, "get") else None
        if anchor:
            return str(anchor)
        child_with_anchor = element.find(id=True) if hasattr(element, "find") else None
        if child_with_anchor is not None:
            return str(child_with_anchor.get("id"))
        cursor = element
        while cursor is not None:
            anchor = cursor.get("id") if hasattr(cursor, "get") else None
            if anchor:
                return str(anchor)
            cursor = cursor.parent
        return None

    def _has_nested_standard_block(self, element) -> bool:
        return element.find(["h1", "h2", "h3", "h4", "p", "li"]) is not None
