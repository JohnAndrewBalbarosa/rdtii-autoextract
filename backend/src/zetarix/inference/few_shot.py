"""Few-shot / RAG grounding retriever for Law Interpreter and Tag Generator.

Phase 2 of ``backend/docs/pipeline-stages-and-training.md``. Retrieves the k most similar
prior verified examples (same jurisdiction + pillar) using token-set Jaccard similarity,
with optional SetTrieIndex tag-overlap ranking as a secondary signal.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from zetarix.scoring.set_trie import SetTrieIndex, SetTrieItem
from zetarix.pretrain.dataset.schemas import LawInterpreterExample, TagGeneratorExample

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> frozenset[str]:
    return frozenset(_WORD_RE.findall(text.lower()))


def jaccard_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


@dataclass(frozen=True)
class RetrievedExample:
    """One few-shot exemplar with similarity score."""

    example: dict[str, Any]
    score: float
    source_id: str


class FewShotRetriever:
    """Retrieve verified training exemplars for few-shot prompt injection."""

    def __init__(
        self,
        law_examples: Sequence[LawInterpreterExample] | None = None,
        tag_examples: Sequence[TagGeneratorExample] | None = None,
    ) -> None:
        self._law_positives = [
            ex for ex in (law_examples or ()) if ex.label == "positive"
        ]
        self._tag_positives = [
            ex for ex in (tag_examples or ()) if ex.label == "positive"
        ]
        self._tag_trie = self._build_tag_trie(self._tag_positives)

    @classmethod
    def from_jsonl(
        cls,
        law_path: Path | str,
        tag_path: Path | str,
    ) -> "FewShotRetriever":
        law = [_load_law_row(row) for row in _read_jsonl(law_path)]
        tags = [_load_tag_row(row) for row in _read_jsonl(tag_path)]
        return cls(law_examples=law, tag_examples=tags)

    @classmethod
    def from_splits_dir(cls, splits_dir: Path | str) -> "FewShotRetriever":
        root = Path(splits_dir)
        return cls.from_jsonl(
            root / "law_interpreter_train.jsonl",
            root / "tag_generator_train.jsonl",
        )

    @staticmethod
    def _build_tag_trie(examples: Sequence[TagGeneratorExample]) -> SetTrieIndex | None:
        if not examples:
            return None
        items = [
            SetTrieItem(node_id=ex.source_id or str(i), tags=frozenset(ex.indicator_tags))
            for i, ex in enumerate(examples)
            if ex.indicator_tags
        ]
        return SetTrieIndex(items) if items else None

    def retrieve_law_interpreter(
        self,
        *,
        tagged_provision_input: str,
        jurisdiction: str,
        pillar: int,
        k: int = 3,
    ) -> tuple[RetrievedExample, ...]:
        candidates = [
            ex
            for ex in self._law_positives
            if ex.jurisdiction == jurisdiction and ex.pillar == pillar
        ]
        if not candidates:
            candidates = [ex for ex in self._law_positives if ex.pillar == pillar]
        scored = sorted(
            (
                RetrievedExample(
                    example=ex.to_dict(),
                    score=jaccard_similarity(tagged_provision_input, ex.tagged_provision_input),
                    source_id=ex.source_id,
                )
                for ex in candidates
            ),
            key=lambda item: (-item.score, item.source_id),
        )
        return tuple(scored[:k])

    def retrieve_tag_generator(
        self,
        *,
        legal_interpretation: str,
        jurisdiction: str,
        pillar: int,
        precedent_tags: Sequence[str] = (),
        k: int = 3,
    ) -> tuple[RetrievedExample, ...]:
        candidates = [
            ex
            for ex in self._tag_positives
            if ex.jurisdiction == jurisdiction and ex.pillar == pillar
        ]
        if not candidates:
            candidates = [ex for ex in self._tag_positives if ex.pillar == pillar]

        trie_boost: dict[str, float] = {}
        if self._tag_trie and precedent_tags:
            query_tags = frozenset(precedent_tags)
            for node_id in self._tag_trie.query_subsets(query_tags):
                trie_boost[node_id] = 0.15

        scored = sorted(
            (
                RetrievedExample(
                    example=ex.to_dict(),
                    score=(
                        jaccard_similarity(legal_interpretation, ex.legal_interpretation)
                        + trie_boost.get(ex.source_id, 0.0)
                    ),
                    source_id=ex.source_id,
                )
                for ex in candidates
            ),
            key=lambda item: (-item.score, item.source_id),
        )
        return tuple(scored[:k])

    def build_law_interpreter_prompt(
        self,
        *,
        tagged_provision_input: str,
        jurisdiction: str,
        pillar: int,
        k: int = 3,
    ) -> str:
        exemplars = self.retrieve_law_interpreter(
            tagged_provision_input=tagged_provision_input,
            jurisdiction=jurisdiction,
            pillar=pillar,
            k=k,
        )
        blocks = []
        for i, item in enumerate(exemplars, start=1):
            ex = item.example
            blocks.append(
                f"EXAMPLE {i} (similarity={item.score:.3f}):\n"
                f"INPUT:\n{ex['tagged_provision_input']}\n"
                f"OUTPUT:\n"
                f"  obligation_type: {ex['obligation_type']}\n"
                f"  scope: {ex['scope']}\n"
                f"  applicability_triggers: {ex['applicability_triggers']}\n"
                f"  plain_summary: {ex['plain_summary']}"
            )
        exemplar_text = "\n\n".join(blocks) if blocks else "(no prior exemplars)"
        return (
            "You are the RDTII Law Interpreter. Classify the legal obligation in the tagged provision.\n"
            f"Jurisdiction: {jurisdiction}\nPillar: {pillar}\n\n"
            f"Verified prior examples:\n{exemplar_text}\n\n"
            "Now interpret this provision. Return JSON only.\n"
            f"INPUT:\n{tagged_provision_input}"
        )

    def build_tag_generator_prompt(
        self,
        *,
        legal_interpretation: str,
        jurisdiction: str,
        pillar: int,
        precedent_tags: Sequence[str] = (),
        k: int = 3,
    ) -> str:
        exemplars = self.retrieve_tag_generator(
            legal_interpretation=legal_interpretation,
            jurisdiction=jurisdiction,
            pillar=pillar,
            precedent_tags=precedent_tags,
            k=k,
        )
        blocks = []
        for i, item in enumerate(exemplars, start=1):
            ex = item.example
            blocks.append(
                f"EXAMPLE {i} (similarity={item.score:.3f}):\n"
                f"INPUT:\n{ex['legal_interpretation']}\n"
                f"OUTPUT:\n"
                f"  indicator_tags: {ex['indicator_tags']}\n"
                f"  rationale: {ex['rationale']}"
            )
        exemplar_text = "\n\n".join(blocks) if blocks else "(no prior exemplars)"
        tag_hint = ", ".join(precedent_tags) if precedent_tags else "(none)"
        return (
            "You are the RDTII Law-Aware Tag Generator. Map the legal interpretation to RDTII indicators.\n"
            f"Jurisdiction: {jurisdiction}\nPillar: {pillar}\nPrecedent tags: {tag_hint}\n\n"
            f"Verified prior examples:\n{exemplar_text}\n\n"
            "Now generate indicator tags. Return JSON only.\n"
            f"INPUT:\n{legal_interpretation}"
        )


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_law_row(row: dict[str, Any]) -> LawInterpreterExample:
    return LawInterpreterExample.from_dict(row)


def _load_tag_row(row: dict[str, Any]) -> TagGeneratorExample:
    return TagGeneratorExample.from_dict(row)
