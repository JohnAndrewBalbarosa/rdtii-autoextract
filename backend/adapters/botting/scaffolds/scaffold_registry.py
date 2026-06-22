from typing import Optional
from urllib.parse import urlparse
from .base_scaffold import BaseScaffold
from .homeaffairs_gov_au import HomeAffairsScaffold
from .sso_agc_gov_sg import SSOAgcScaffold
from .pdpc_gov_sg import PDPCScaffold
from .pdp_gov_my import PDPMyScaffold

class ScaffoldRegistry:
    """OSI Layer 7 (Application): Registry to discover and match URLs to Scaffolds."""

    def __init__(self, scaffolds: list[BaseScaffold] | None = None):
        if scaffolds is None:
            # Default: register all known scaffolds
            scaffolds = [
                HomeAffairsScaffold(),
                SSOAgcScaffold(),
                PDPCScaffold(),
                PDPMyScaffold(),
            ]
        self._scaffolds = {s.target_domain: s for s in scaffolds}

    def get_scaffold_for_url(self, url: str) -> Optional[BaseScaffold]:
        """Match a URL to a registered scaffold based on domain."""
        domain = urlparse(url).netloc
        # Support both 'www.example.com' and 'example.com' matching
        for target, scaffold in self._scaffolds.items():
            if target in domain:
                return scaffold
        return None
