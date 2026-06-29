from playwright.sync_api import sync_playwright
from core.ports import HtmlFetcherPort
from adapters.botting.l4_transport.proxy_config import ProxyConfig

class PlaywrightClient(HtmlFetcherPort):
    """OSI Layer 4 (Transport): Headless browser communication using Playwright."""

    def __init__(
        self,
        headless: bool = True,
        timeout_ms: int = 60000,
        proxy_config: ProxyConfig = None,
        expand: bool = True,
    ):
        self._headless = headless
        self._timeout = timeout_ms
        self._proxy_config = proxy_config
        self._expand = expand

    # Best-effort JS to open collapsed legal content (accordions / "Expand all" toggles),
    # so portals that lazy-render provision text (e.g. legislation.gov.au) yield full bodies.
    _EXPAND_JS = """() => {
        const fire = (el) => { try { el.click(); } catch (_) {} };
        document.querySelectorAll('button, a, [role=button]').forEach((b) => {
            const t = (b.textContent || '').trim().toLowerCase();
            if (t === 'expand all' || t === 'expand' || t.startsWith('expand ') ||
                t === 'show all' || t === 'open all') fire(b);
        });
        document.querySelectorAll('[aria-expanded="false"]').forEach(fire);
    }"""

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
                # SPAs (e.g. legislation.gov.au) keep background traffic alive, so
                # "networkidle" routinely times out. Wait for the DOM, then expand + settle.
                page.goto(url, wait_until="domcontentloaded", timeout=self._timeout)
                if self._expand:
                    # Expand twice (nested accordions), settling after each, all best-effort.
                    for _ in range(2):
                        try:
                            page.evaluate(self._EXPAND_JS)
                            page.wait_for_timeout(1500)
                        except Exception:
                            break
                    try:
                        page.wait_for_load_state("networkidle", timeout=self._timeout)
                    except Exception:
                        pass
                return page.content()
            except Exception as e:
                raise RuntimeError(f"Playwright error fetching {url}: {e}")
            finally:
                browser.close()

