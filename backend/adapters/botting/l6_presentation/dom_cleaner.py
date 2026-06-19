from bs4 import BeautifulSoup

class DomCleaner:
    """OSI Layer 6 (Presentation): Translates raw HTML bytes/strings into clean, readable text."""

    def clean_html(self, html_content: str, selectors: dict[str, str] = None) -> str:
        """Strips boilerplate and returns clean text."""
        soup = BeautifulSoup(html_content, "html.parser")
        
        # If content_area selector is provided, try to find it
        main_content = None
        if selectors and "content_area" in selectors:
            main_content = soup.select_one(selectors["content_area"])
        
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
