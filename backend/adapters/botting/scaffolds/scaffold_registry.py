from typing import Optional
from urllib.parse import urlparse
from .base_scaffold import BaseScaffold

class ScaffoldRegistry:
    """OSI Layer 7 (Application): Registry to discover and match URLs to Scaffolds."""

    def __init__(self, scaffolds: list[BaseScaffold]):
        self._scaffolds = {s.target_domain: s for s in scaffolds}

    def get_scaffold_for_url(self, url: str) -> Optional[BaseScaffold]:
        """Match a URL to a registered scaffold based on domain."""
        domain = urlparse(url).netloc
        # Support both 'www.example.com' and 'example.com' matching
        for target, scaffold in self._scaffolds.items():
            if target in domain:
                return scaffold
        return None
