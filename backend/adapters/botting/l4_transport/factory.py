import re

from core.ports import HtmlFetcherPort
from adapters.botting.l4_transport.fetch_result import FetchResult

# Single-page-app shells render their real content with JS; the static HTML carries only a
# framework marker and little visible text. Detecting these triggers the dynamic engine.
_SPA_MARKERS = (
    "ng-version",
    "<app-root",
    "data-reactroot",
    "__next_data__",
    "window.__nuxt__",
    'id="root"',
    'id="__next"',
)
_SPA_MIN_VISIBLE_CHARS = 1200
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


class TransportFactory(HtmlFetcherPort):
    """OSI Layer 4 (Transport): Hybrid factory that selects the best fetching engine."""

    def __init__(self, static_fetcher: HtmlFetcherPort, dynamic_fetcher: HtmlFetcherPort):
        self._static = static_fetcher
        self._dynamic = dynamic_fetcher

    def fetch_raw(self, url: str) -> FetchResult:
        """Binary-safe fetch: delegates to static fetcher's fetch_raw if available."""
        if hasattr(self._static, "fetch_raw"):
            result = self._static.fetch_raw(url)
            # PDFs never need JS rendering; return immediately
            if result.is_pdf:
                return result
            # For HTML, check if dynamic rendering is needed
            try:
                html = result.text
            except ValueError:
                return result
            if self._is_headless_required(html):
                # Dynamic fetcher may not have fetch_raw; fall back to fetch() wrapped in FetchResult
                if hasattr(self._dynamic, "fetch_raw"):
                    return self._dynamic.fetch_raw(url)
                dyn_html = self._dynamic.fetch(url)
                return FetchResult(
                    url=url,
                    status=200,
                    content_type="text/html; charset=utf-8",
                    body=dyn_html.encode("utf-8", errors="replace"),
                )
            return result
        # Fallback: static fetcher has no fetch_raw, wrap str result
        html = self._static.fetch(url)
        if self._is_headless_required(html):
            html = self._dynamic.fetch(url)
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

    def fetch_raw_dynamic(self, url: str) -> FetchResult:
        """Force the dynamic (JS-rendering) engine — used when a scaffold declares a domain
        dynamic, or as a retry when static extraction yields nothing legislative."""
        if hasattr(self._dynamic, "fetch_raw"):
            return self._dynamic.fetch_raw(url)
        dyn_html = self._dynamic.fetch(url)
        return FetchResult(
            url=url,
            status=200,
            content_type="text/html; charset=utf-8",
            body=dyn_html.encode("utf-8", errors="replace"),
        )

    def _is_headless_required(self, html_content: str) -> bool:
        """Heuristic detection of JS-heavy or empty content (incl. unrendered SPA shells)."""
        lower_content = html_content.lower()
        indicators = [
            "javascript is required",
            "enable javascript",
            "you need to enable javascript",
        ]
        if any(ind in lower_content for ind in indicators):
            return True
        if len(html_content) < 500 and "<script" in lower_content:
            return True
        if any(marker in lower_content for marker in _SPA_MARKERS):
            visible = _WS_RE.sub(" ", _TAG_RE.sub(" ", html_content)).strip()
            if len(visible) < _SPA_MIN_VISIBLE_CHARS:
                return True
        return False
