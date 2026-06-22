"""FallbackProvisionExtractor — try a primary extractor, fall back per-document.

Composes two ``ProvisionExtractor``s: run the primary (the tag→set-trie matcher); if it
produces no findings for a document, run the fallback (the keyword mock) so the live path
still yields rows. Both share the ``extract(doc, pillar) -> list[Finding]`` port, so this is
itself a drop-in ``ProvisionExtractor``. Pure: no I/O, deterministic given its delegates.
"""

from __future__ import annotations

from core.domain.document import CrawledDocument
from core.domain.entities import Finding


class FallbackProvisionExtractor:
    """Primary-then-fallback extractor (per-document, not global)."""

    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def extract(self, doc: CrawledDocument, pillar: int) -> list[Finding]:
        primary = self._primary.extract(doc, pillar)
        if primary:
            return primary
        return self._fallback.extract(doc, pillar)
