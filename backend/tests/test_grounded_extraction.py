"""Tests for Phase 2 grounded Law Interpreter + Tag Generator inference."""

from __future__ import annotations

from zetarix.domain.document import CrawledDocument
from zetarix.extraction.law_interpreter import LawInterpreter
from zetarix.extraction.llm_provision_extractor import LLMProvisionExtractor
from zetarix.extraction.tag_generator import TagGenerator
from zetarix.training.few_shot_retriever import FewShotRetriever
from zetarix.training.schemas import (
    LAW_INTERPRETER_OUTPUT_SCHEMA,
    TAG_GENERATOR_OUTPUT_SCHEMA,
    LawInterpreterExample,
    TagGeneratorExample,
)


class _RecordingLLM:
    def __init__(self) -> None:
        self.prompts: list[tuple[str, str]] = []

    def complete(self, prompt: str, schema: dict, agent_profile: str = "main_controller") -> dict:
        self.prompts.append((agent_profile, prompt))
        if agent_profile == "law_interpreter":
            return {
                "obligation_type": "requirement",
                "scope": "Organisations transferring data abroad",
                "applicability_triggers": ["cross-border transfer"],
                "plain_summary": "Conditional transfer regime",
            }
        return {
            "indicator_tags": ["6.2"],
            "rationale": "Maps to cross-border transfer conditions",
        }


def _retriever() -> FewShotRetriever:
    return FewShotRetriever(
        law_examples=[
            LawInterpreterExample(
                tagged_provision_input="Act: PDPA\nProvision: transfer abroad",
                jurisdiction="Singapore",
                pillar=6,
                obligation_type="requirement",
                scope="Organisations",
                applicability_triggers=("transfer",),
                plain_summary="Transfer rules",
                source_id="sg-1",
            )
        ],
        tag_examples=[
            TagGeneratorExample(
                legal_interpretation="Scope: transfers\nImpact: conditional",
                jurisdiction="Singapore",
                pillar=6,
                precedent_tags=(),
                indicator_tags=("6.2",),
                rationale="Cross-border mapping",
                source_id="sg-tag-1",
            )
        ],
    )


def test_law_interpreter_uses_few_shot_exemplars():
    llm = _RecordingLLM()
    interpreter = LawInterpreter(llm, retriever=_retriever(), grounding="few_shot", k=1)
    result = interpreter.interpret(
        tagged_provision_input="Act: PDPA\nProvision: transfer personal data outside Singapore",
        jurisdiction="Singapore",
        pillar=6,
    )
    assert result.obligation_type == "requirement"
    assert llm.prompts[0][0] == "law_interpreter"
    assert "EXAMPLE 1" in llm.prompts[0][1]


def test_law_interpreter_zero_shot_skips_exemplars():
    llm = _RecordingLLM()
    interpreter = LawInterpreter(llm, retriever=_retriever(), grounding="none")
    interpreter.interpret(
        tagged_provision_input="Provision text",
        jurisdiction="Singapore",
        pillar=6,
    )
    assert "EXAMPLE" not in llm.prompts[0][1]
    assert "TAGGED_PROVISION_START" in llm.prompts[0][1]


def test_tag_generator_uses_few_shot_exemplars():
    llm = _RecordingLLM()
    tagger = TagGenerator(llm, retriever=_retriever(), grounding="few_shot", k=1)
    mapping = tagger.generate(
        legal_interpretation="Scope: transfers abroad",
        jurisdiction="Singapore",
        pillar=6,
    )
    assert mapping.indicator_tags == ("6.2",)
    assert "EXAMPLE 1" in llm.prompts[-1][1]


def test_llm_provision_extractor_produces_findings():
    llm = _RecordingLLM()
    extractor = LLMProvisionExtractor(
        llm,
        interpreter=LawInterpreter(llm, grounding="none"),
        tagger=TagGenerator(llm, grounding="none"),
    )
    doc = CrawledDocument(
        url="https://example.gov/act",
        economy="Singapore",
        text=(
            "Personal Data Protection Act 2012\n"
            "Last amended on 1 February 2021\n\n"
            "Section 26 Transfer limitation obligation\n"
            "An organisation must not transfer personal data outside Singapore "
            "except in accordance with requirements ensuring comparable protection.\n\n"
            "Section 27 Other matter\n"
            "Short unrelated text."
        ),
        is_pdf=False,
    )
    findings = extractor.extract(doc, pillar=6)
    assert len(findings) == 1
    assert findings[0].indicator == "P6-I2"
    assert findings[0].economy == "Singapore"
    assert "transfer" in findings[0].verbatim_snippet.lower()
    assert findings[0].title == "Personal Data Protection Act 2012"
    assert findings[0].scope == "Organisations transferring data abroad"
    assert findings[0].impact == "Conditional transfer regime"
    assert findings[0].last_update == __import__("datetime").date(2021, 2, 1)
    assert findings[0].article_section.startswith("Section 26")
