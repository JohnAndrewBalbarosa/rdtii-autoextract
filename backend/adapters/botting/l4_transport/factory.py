from core.ports import HtmlFetcherPort

class TransportFactory(HtmlFetcherPort):
    """OSI Layer 4 (Transport): Hybrid factory that selects the best fetching engine."""

    def __init__(self, static_fetcher: HtmlFetcherPort, dynamic_fetcher: HtmlFetcherPort):
        self._static = static_fetcher
        self._dynamic = dynamic_fetcher

    def fetch(self, url: str) -> str:
        """Try static fetch first; fallback to dynamic if content looks empty or JS-locked."""
        content = self._static.fetch(url)
        
        if self._is_headless_required(content):
            return self._dynamic.fetch(url)
            
        return content

    def _is_headless_required(self, html_content: str) -> bool:
        """Heuristic detection of JS-heavy or empty content."""
        indicators = [
            "javascript is required",
            "enable javascript",
            "you need to enable javascript"
        ]
        
        lower_content = html_content.lower()
        if any(ind in lower_content for ind in indicators):
            return True
            
        # If content is extremely short (e.g. just a script tag), likely needs rendering
        if len(html_content) < 500 and "<script" in lower_content:
            return True
            
        return False
