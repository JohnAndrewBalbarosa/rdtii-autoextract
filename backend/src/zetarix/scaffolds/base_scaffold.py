from abc import ABC, abstractmethod
from typing import Optional

class BaseScaffold(ABC):
    """Base class for site-specific botting logic (Scaffolds)."""

    @property
    @abstractmethod
    def target_domain(self) -> str:
        """The domain this scaffold applies to (e.g., 'homeaffairs.gov.au')."""
        pass

    def get_transport_type(self) -> str:
        """Override to force 'static' or 'dynamic' transport."""
        return "auto"

    def get_custom_selectors(self) -> dict[str, str]:
        """Site-specific CSS/XPath selectors for cleaner extraction."""
        return {}

    def get_keywords(self) -> list[str]:
        """Site-specific keywords for relevance tagging."""
        return []
