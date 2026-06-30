from __future__ import annotations

from core.domain.document import ParsedDocument
from core.ports import LLMProvider


class DocumentComplianceValidator:
    """Domain Service: deterministic structural validity check for a parsed document.

    This is a rule check, not a model judgement: a document is usable if it has at
    least one section carrying non-empty content. It must NEVER spend LLM tokens —
    the previous per-page ``complete()`` call sent only the URL + section count to the
    model, which carried no signal a deterministic rule cannot replicate, while costing
    one LLM call per page at scale. See memory: two-scrapers-cost-divergence.
    """

    def __init__(self, llm_provider: LLMProvider | None = None):
        # Retained for constructor compatibility with existing wiring; intentionally unused.
        self._llm = llm_provider

    def is_valid(self, document: ParsedDocument) -> bool:
        """Main Controller logic: accept only documents with real section content."""
        if not document.sections:
            return False
        return any(section.text.strip() for section in document.sections)
