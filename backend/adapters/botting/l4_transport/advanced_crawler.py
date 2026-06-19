import re
import urllib.parse
from bs4 import BeautifulSoup
from typing import Optional, List, Dict, Set

from adapters.botting.l4_transport.proxy_config import ProxyConfig
from adapters.botting.l4_transport.http_client import HttpClient
from adapters.botting.l4_transport.playwright_client import PlaywrightClient
from adapters.botting.l4_transport.pdf_parser import PdfParser

class AdvancedCrawler:
    """Advanced crawler that prefers dynamic fetch, falling back to static fetch, cleans HTML,
    scans for PDF links (including in scripts and external JS files), and extracts PDF text.
    """

    def __init__(self, proxy_config: Optional[ProxyConfig] = None):
        self.proxy_config = proxy_config
        self.playwright_client = PlaywrightClient(proxy_config=proxy_config)
        self.http_client = HttpClient(proxy_config=proxy_config)
        self.pdf_parser = PdfParser(proxy_config=proxy_config)
        self.pdf_pattern = re.compile(r'https?://[^\s"\'<>]+?\.pdf', re.IGNORECASE)

    def fetch_page(self, url: str) -> str:
        """Fetch page content, preferring dynamic (Playwright) with fallback to static (HttpClient)."""
        try:
            return self.playwright_client.fetch(url)
        except Exception as e:
            # Fallback to static fetch using HttpClient
            return self.http_client.fetch(url)

    def clean_html(self, html_content: str) -> str:
        """Clean HTML to only get main body content, excluding headers, footers, navs, styles, templates."""
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Target the body tag, fallback to the entire soup
        body = soup.find("body") or soup
        
        # Elements to exclude/remove
        exclude_tags = ["header", "footer", "nav", "style", "template", "noscript", "script"]
        for tag in exclude_tags:
            for element in body.find_all(tag):
                element.decompose()
                
        return str(body)

    def extract_links_from_text(self, text: str) -> Set[str]:
        """Search for PDF links matching the pattern in the given text using regex."""
        return set(self.pdf_pattern.findall(text))

    def scan_script_tags(self, html_content: str) -> Set[str]:
        """Scan inline <script> tags for embedded PDF links."""
        soup = BeautifulSoup(html_content, "html.parser")
        links = set()
        for script in soup.find_all("script"):
            if script.string:
                links.update(self.extract_links_from_text(script.string))
        return links

    def scan_external_js(self, html_content: str, base_url: str) -> Set[str]:
        """Scan for external JS files, fetch them, and extract PDF links."""
        soup = BeautifulSoup(html_content, "html.parser")
        links = set()
        for script in soup.find_all("script"):
            src = script.get("src")
            if src:
                # Resolve relative/absolute URL
                js_url = urllib.parse.urljoin(base_url, src)
                try:
                    # Download the JS content via http_client
                    js_content = self.http_client.fetch(js_url)
                    links.update(self.extract_links_from_text(js_content))
                except Exception:
                    # Fail silently on script fetch error as some external scripts may be blocked or unavailable
                    pass
        return links

    def crawl(self, url: str) -> Dict[str, any]:
        """Crawl the given page: fetch, clean, scan for PDF links, download/parse them."""
        # 1. Fetch page (dynamic with static fallback)
        html_content = self.fetch_page(url)
        
        # 2. Extract PDF links
        pdf_links = set()
        
        # Search PDF links matching regex pattern in the HTML content
        pdf_links.update(self.extract_links_from_text(html_content))
        
        # Scan inline script tags
        pdf_links.update(self.scan_script_tags(html_content))
        
        # Scan external JS files
        pdf_links.update(self.scan_external_js(html_content, url))
        
        # 3. Clean HTML
        cleaned_html = self.clean_html(html_content)
        
        # 4. Download and parse found PDF files
        pdf_contents = {}
        for link in pdf_links:
            try:
                pdf_text = self.pdf_parser.parse(link)
                pdf_contents[link] = pdf_text
            except Exception as e:
                pdf_contents[link] = f"Error parsing PDF: {str(e)}"
                
        return {
            "raw_html": html_content,
            "cleaned_html": cleaned_html,
            "pdf_links": list(pdf_links),
            "pdf_contents": pdf_contents
        }
