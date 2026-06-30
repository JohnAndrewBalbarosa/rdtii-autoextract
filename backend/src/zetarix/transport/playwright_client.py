from playwright.sync_api import sync_playwright
from zetarix.ports import HtmlFetcherPort
from zetarix.transport.proxy_config import ProxyConfig

class PlaywrightClient(HtmlFetcherPort):
    """OSI Layer 4 (Transport): Headless browser communication using Playwright."""

    def __init__(self, headless: bool = True, timeout_ms: int = 30000, proxy_config: ProxyConfig = None):
        self._headless = headless
        self._timeout = timeout_ms
        self._proxy_config = proxy_config

    def fetch(self, url: str) -> str:
        """Render the page using a headless browser and return the HTML."""
        with sync_playwright() as p:
            launch_args = {"headless": self._headless}
            if self._proxy_config:
                pw_proxy = self._proxy_config.to_playwright_proxy()
                if pw_proxy:
                    launch_args["proxy"] = pw_proxy
                    
            browser = p.chromium.launch(**launch_args)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=self._timeout)
                return page.content()
            except Exception as e:
                raise RuntimeError(f"Playwright error fetching {url}: {e}")
            finally:
                browser.close()

