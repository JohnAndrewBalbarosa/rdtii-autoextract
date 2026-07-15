from __future__ import annotations

from zetarix.domain.entities import DiscoveryTag
from zetarix.extraction.reviewer_brief_generator import ReviewerBriefGenerator, ReviewerBriefInput


class _NullTemplateLLM:
    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        return {
            "scope": None,
            "provisions": None,
            "impact": None,
            "verbatim_snippet": None,
            "mapping_rationale": None,
            "confidence": None,
            "review_notes": None,
        }


def _input(**overrides) -> ReviewerBriefInput:
    data = ReviewerBriefInput(
        title="Personal Data Protection Act 2012",
        jurisdiction="Singapore",
        pillar=6,
        indicator="P6-I1",
        article_number="Section 26",
        provision_text=(
            "Section 26. An organisation shall not transfer any personal data to a "
            "country or territory outside Singapore except in accordance with this Act."
        ),
        source_url="https://sso.agc.gov.sg/Act/PDPA2012",
        nearby_context=(
            "Section 25 concerns retention. Section 26. An organisation shall not "
            "transfer any personal data to a country or territory outside Singapore "
            "except in accordance with this Act. Section 27 concerns exceptions."
        ),
        discovery_tag=DiscoveryTag.KNOWN,
        supporting_snippet=(
            "An organisation shall not transfer any personal data to a country or "
            "territory outside Singapore except in accordance with this Act"
        ),
    )
    return ReviewerBriefInput(**{**data.__dict__, **overrides})


def test_reviewer_brief_generator_rejects_placeholder_inputs():
    generator = ReviewerBriefGenerator()

    finding = generator.generate(
        _input(
            source_url="https://...",
            provision_text="[exact section text here]",
            nearby_context="[1–2 lines before and after]",
        )
    )

    assert finding is None


def test_reviewer_brief_generator_uses_real_input_when_llm_returns_null_template():
    generator = ReviewerBriefGenerator(llm_provider=_NullTemplateLLM())

    finding = generator.generate(_input())

    assert finding is not None
    assert finding.title == "Personal Data Protection Act 2012"
    assert finding.url == "https://sso.agc.gov.sg/Act/PDPA2012"
    assert finding.article_section == "Section 26"
    assert "cross-border transfer" in finding.scope.lower()
    assert "keyword" not in finding.mapping_rationale.lower()
    assert "Detected" not in finding.impact
    assert finding.verbatim_snippet
    assert finding.notes
    assert 0.0 <= finding.confidence <= 1.0
