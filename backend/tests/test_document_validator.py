"""DocumentComplianceValidator must be deterministic — no per-page LLM call.

The validator only decides whether a parsed document is structurally a usable legal
document. That is a rule check (does it have non-empty section content?), not a model
judgement, so it must never spend LLM tokens. See memory: two-scrapers-cost-divergence.
"""

from __future__ import annotations

import pytest

from zetarix.domain.document import ParsedDocument, RawSection
from zetarix.validation.document_validator import DocumentComplianceValidator


def _doc(sections: list[RawSection], url: str = "https://example.gov/law") -> ParsedDocument:
    return ParsedDocument(document_url=url, language="en", sections=tuple(sections))


def test_empty_sections_are_invalid():
    assert DocumentComplianceValidator().is_valid(_doc([])) is False


def test_sections_with_text_are_valid_without_any_llm():
    doc = _doc([RawSection(heading="Act", level=1, text="Personal data must be protected.")])
    assert DocumentComplianceValidator().is_valid(doc) is True


def test_sections_with_only_blank_text_are_invalid():
    doc = _doc([RawSection(heading="", level=1, text="   \n\t")])
    assert DocumentComplianceValidator().is_valid(doc) is False


def test_validator_never_calls_the_llm():
    class BoomLLM:
        def complete(self, prompt, schema, agent_profile="main_controller"):
            raise AssertionError("validator must not call the LLM")

    doc = _doc([RawSection(heading="Act", level=1, text="reasonable security arrangements")])
    assert DocumentComplianceValidator(llm_provider=BoomLLM()).is_valid(doc) is True
