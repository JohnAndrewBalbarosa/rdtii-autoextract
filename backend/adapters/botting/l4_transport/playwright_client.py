from playwright.sync_api import sync_playwright
from core.ports import HtmlFetcherPort
from adapters.botting.l4_transport.proxy_config import ProxyConfig

class PlaywrightClient(HtmlFetcherPort):
    """OSI Layer 4 (Transport): Headless browser communication using Playwright."""

    def __init__(self, headless: bool = True, timeout_ms: int = 30000, proxy_config: ProxyConfig = None):
        self._headless = headless
        self._timeout = timeout_ms
        self._proxy_config = proxy_config

    def fetch(self, url: str) -> str:
        """Render the page using a headless browser with anti-bot evasion and return the HTML."""
        with sync_playwright() as p:
            launch_args = {
                "headless": self._headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ]
            }
            if self._proxy_config:
                pw_proxy = self._proxy_config.to_playwright_proxy()
                if pw_proxy:
                    launch_args["proxy"] = pw_proxy
                    
            browser = p.chromium.launch(**launch_args)
            try:
                # Use a realistic browser context to spoof human visitors
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 720},
                    locale="en-US",
                    timezone_id="America/New_York",
                    java_script_enabled=True,
                )
                
                # Add typical headers to match browser request profile
                context.set_extra_http_headers({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                })
                
                page = context.new_page()
                
                # Evade basic navigator.webdriver bot-detection checks
                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
                
                # Navigate and wait for content
                # "domcontentloaded" is faster and less prone to timeout on pages with heavy tracking/analytics
                page.goto(url, wait_until="domcontentloaded", timeout=self._timeout)
                
                # Wait briefly for page dynamic scripts to settle
                page.wait_for_timeout(1000)
                
                return page.content()
            except Exception as e:
                raise RuntimeError(f"Playwright error fetching {url}: {e}")
            finally:
                browser.close()

