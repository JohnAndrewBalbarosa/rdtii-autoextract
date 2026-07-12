"""Law Interpreter use case — classify legal obligations from tagged provisions.

Phase 2 inference stage. Framework-agnostic: depends only on ``LLMProvider`` and an
optional ``FewShotRetriever`` for RAG-grounded exemplars.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from zetarix.llm.prompt_contracts import build_law_interpreter_prompt
from zetarix.ports import LLMProvider
from zetarix.inference.few_shot import FewShotRetriever
from zetarix.inference.schemas import LAW_INTERPRETER_OUTPUT_SCHEMA

GroundingMode = Literal["none", "few_shot"]
_ENV_GROUNDING = "ZETARIX_GROUNDING"
_ENV_FEW_SHOT_K = "ZETARIX_FEW_SHOT_K"
_DEFAULT_K = 3


@dataclass(frozen=True)
class LegalInterpretation:
    """Structured output from the Law Interpreter stage."""

    obligation_type: str
    scope: str
    applicability_triggers: tuple[str, ...]
    plain_summary: str


class LawInterpreter:
    """Interpret a tagged provision into obligation type, scope, and plain summary."""

    def __init__(
        self,
        llm: LLMProvider,
        *,
        retriever: FewShotRetriever | None = None,
        grounding: GroundingMode = "few_shot",
        k: int = _DEFAULT_K,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._grounding = grounding
        self._k = k

    @classmethod
    def from_env(cls, llm: LLMProvider, retriever: FewShotRetriever | None = None) -> "LawInterpreter":
        grounding = os.environ.get(_ENV_GROUNDING, "few_shot")
        if grounding not in ("none", "few_shot"):
            grounding = "few_shot"
        k = int(os.environ.get(_ENV_FEW_SHOT_K, _DEFAULT_K))
        return cls(llm, retriever=retriever, grounding=grounding, k=k)

    def interpret(
        self,
        *,
        tagged_provision_input: str,
        jurisdiction: str,
        pillar: int,
    ) -> LegalInterpretation:
        prompt = self._build_prompt(
            tagged_provision_input=tagged_provision_input,
            jurisdiction=jurisdiction,
            pillar=pillar,
        )
        result = self._llm.complete(prompt, LAW_INTERPRETER_OUTPUT_SCHEMA, "law_interpreter")
        triggers = result.get("applicability_triggers") or []
        return LegalInterpretation(
            obligation_type=str(result.get("obligation_type", "other")),
            scope=str(result.get("scope", "")),
            applicability_triggers=tuple(str(t) for t in triggers),
            plain_summary=str(result.get("plain_summary", "")),
        )

    def _build_prompt(self, *, tagged_provision_input: str, jurisdiction: str, pillar: int) -> str:
        if self._grounding == "few_shot" and self._retriever is not None:
            return self._retriever.build_law_interpreter_prompt(
                tagged_provision_input=tagged_provision_input,
                jurisdiction=jurisdiction,
                pillar=pillar,
                k=self._k,
            )
        return build_law_interpreter_prompt(
            tagged_provision_input=tagged_provision_input,
            jurisdiction=jurisdiction,
            pillar=pillar,
        )
