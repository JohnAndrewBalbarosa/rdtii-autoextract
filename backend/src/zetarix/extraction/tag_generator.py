"""Tag Generator use case — map legal interpretations to RDTII indicator tags.

SetTrie lookup fires before LLM fallback; LLM output is constrained to the closed
P6/P7 vocabulary. Hit-rate stats are logged via ``set_trie_tagger``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal, Sequence

from zetarix.domain.indicator_codes import to_db
from zetarix.llm.prompt_contracts import build_tag_generator_prompt
from zetarix.ports import LLMProvider
from zetarix.inference.few_shot import FewShotRetriever
from zetarix.inference.schemas import TAG_GENERATOR_OUTPUT_SCHEMA
from zetarix.inference.set_trie import SetTrieTagger, get_stats, record_llm_fallback
from zetarix.inference.vocabulary import constrain_tags, vocabulary_for_pillar, vocabulary_schema_enum

GroundingMode = Literal["none", "few_shot"]
_ENV_GROUNDING = "ZETARIX_GROUNDING"
_ENV_FEW_SHOT_K = "ZETARIX_FEW_SHOT_K"
_DEFAULT_K = 3

logger = logging.getLogger("zetarix.extraction.tag_generator")


@dataclass(frozen=True)
class IndicatorMapping:
    indicator_tags: tuple[str, ...]
    rationale: str
    source: str = "llm"  # set_trie | llm


class TagGenerator:
    def __init__(
        self,
        llm: LLMProvider,
        *,
        retriever: FewShotRetriever | None = None,
        set_trie_tagger: SetTrieTagger | None = None,
        grounding: GroundingMode = "few_shot",
        k: int = _DEFAULT_K,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._set_trie = set_trie_tagger
        self._grounding = grounding
        self._k = k

    @classmethod
    def from_env(cls, llm: LLMProvider, retriever: FewShotRetriever | None = None) -> "TagGenerator":
        grounding = os.environ.get(_ENV_GROUNDING, "few_shot")
        if grounding not in ("none", "few_shot"):
            grounding = "few_shot"
        k = int(os.environ.get(_ENV_FEW_SHOT_K, _DEFAULT_K))
        trie = None
        if retriever is not None and retriever._tag_positives:
            trie = SetTrieTagger.from_examples(retriever._tag_positives)
        return cls(llm, retriever=retriever, set_trie_tagger=trie, grounding=grounding, k=k)

    def generate(
        self,
        *,
        legal_interpretation: str,
        jurisdiction: str,
        pillar: int,
        precedent_tags: Sequence[str] = (),
    ) -> IndicatorMapping:
        precedent = frozenset(constrain_tags(precedent_tags, pillar))

        if self._set_trie is not None:
            trie_tags = self._set_trie.lookup(
                precedent_tags=precedent,
                jurisdiction=jurisdiction,
                pillar=pillar,
            )
            if trie_tags:
                return IndicatorMapping(
                    indicator_tags=trie_tags,
                    rationale="SetTrie match on precedent tags + jurisdiction/pillar.",
                    source="set_trie",
                )

        record_llm_fallback()
        prompt = self._build_prompt(
            legal_interpretation=legal_interpretation,
            jurisdiction=jurisdiction,
            pillar=pillar,
            precedent_tags=precedent_tags,
        )
        schema = _constrained_schema(pillar)
        result = self._llm.complete(prompt, schema, "tag_generator")
        raw_tags = result.get("indicator_tags") or []
        tags = constrain_tags(raw_tags, pillar)
        if raw_tags and not tags:
            logger.warning(
                "LLM returned %d tag(s) outside P%d vocabulary: %s",
                len(raw_tags),
                pillar,
                raw_tags,
            )
        return IndicatorMapping(
            indicator_tags=tags,
            rationale=str(result.get("rationale", "")),
            source="llm",
        )

    def stats(self) -> dict:
        return get_stats().to_dict()

    def _build_prompt(
        self,
        *,
        legal_interpretation: str,
        jurisdiction: str,
        pillar: int,
        precedent_tags: Sequence[str],
    ) -> str:
        allowed = sorted(vocabulary_for_pillar(pillar))
        vocab_block = "\n".join(f"- {t}" for t in allowed[:40])
        if len(allowed) > 40:
            vocab_block += f"\n- ... ({len(allowed)} total valid P{pillar} indicators)"

        base = ""
        if self._grounding == "few_shot" and self._retriever is not None:
            base = self._retriever.build_tag_generator_prompt(
                legal_interpretation=legal_interpretation,
                jurisdiction=jurisdiction,
                pillar=pillar,
                precedent_tags=precedent_tags,
                k=self._k,
            )
        else:
            base = build_tag_generator_prompt(
                legal_interpretation=legal_interpretation,
                jurisdiction=jurisdiction,
                pillar=pillar,
                precedent_tags=list(precedent_tags),
            )
        return (
            f"{base}\n\nALLOWED_INDICATOR_IDS (select ONLY from this closed list):\n{vocab_block}"
        )


def _constrained_schema(pillar: int) -> dict:
    enum_vals = vocabulary_schema_enum(pillar)
    schema = dict(TAG_GENERATOR_OUTPUT_SCHEMA)
    schema = json_copy(schema)
    schema["properties"] = dict(schema["properties"])
    schema["properties"]["indicator_tags"] = {
        "type": "array",
        "items": {"type": "string", "enum": enum_vals} if enum_vals else {"type": "string"},
    }
    return schema


def json_copy(obj: dict) -> dict:
    import json

    return json.loads(json.dumps(obj))


def _normalize_tag(tag: str) -> str:
    cleaned = str(tag).strip()
    if not cleaned:
        return ""
    try:
        return to_db(cleaned)
    except ValueError:
        return cleaned
