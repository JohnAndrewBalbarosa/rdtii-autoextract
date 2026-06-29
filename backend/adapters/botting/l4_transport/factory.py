from core.ports import HtmlFetcherPort
from adapters.botting.l4_transport.fetch_result import FetchResult


class TransportFactory(HtmlFetcherPort):
    """OSI Layer 4 (Transport): Hybrid factory that selects the best fetching engine."""

    def __init__(self, static_fetcher: HtmlFetcherPort, dynamic_fetcher: HtmlFetcherPort):
        self._static = static_fetcher
        self._dynamic = dynamic_fetcher

    def _fetch_dynamic(self, url: str) -> FetchResult:
        """Helper to invoke the dynamic fetcher."""
        if hasattr(self._dynamic, "fetch_raw"):
            return self._dynamic.fetch_raw(url)
        dyn_html = self._dynamic.fetch(url)
        return FetchResult(
            url=url,
            status=200,
            content_type="text/html; charset=utf-8",
            body=dyn_html.encode("utf-8", errors="replace"),
        )

    def fetch_raw(self, url: str) -> FetchResult:
        """Binary-safe fetch: delegates to static fetcher's fetch_raw, falling back to dynamic on blocks or failures."""
        if hasattr(self._static, "fetch_raw"):
            try:
                result = self._static.fetch_raw(url)
                # PDFs never need JS rendering; return immediately
                if result.is_pdf:
                    return result
                
                try:
                    html = result.text
                except ValueError:
                    return result

                # Check if it was blocked or requires JS
                if result.status in (403, 429) or self._is_headless_required(html):
                    return self._fetch_dynamic(url)
                return result
            except Exception:
                # Fall back to dynamic client on network exceptions or retry exhaustion
                return self._fetch_dynamic(url)

        # Fallback: static fetcher has no fetch_raw, wrap str result
        try:
            html = self._static.fetch(url)
        except Exception:
            html = ""
        if not html or self._is_headless_required(html):
            try:
                html = self._dynamic.fetch(url)
            except Exception:
                pass
        return FetchResult(
            url=url,
            status=200,
            content_type="text/html; charset=utf-8",
            body=html.encode("utf-8", errors="replace"),
        )

    def fetch(self, url: str) -> str:
        """Try static fetch first; fallback to dynamic if content looks empty or JS-locked."""
        result = self.fetch_raw(url)
        try:
            return result.text
        except ValueError:
            # Binary content (PDF) — return empty string to satisfy HtmlFetcherPort
            return ""

    def _is_headless_required(self, html_content: str) -> bool:
        """Heuristic detection of JS-heavy or empty content."""
        indicators = [
            "javascript is required",
            "enable javascript",
            "you need to enable javascript",
        ]
        lower_content = html_content.lower()
        if any(ind in lower_content for ind in indicators):
            return True
        if len(html_content) < 500 and "<script" in lower_content:
            return True
        return False
