"""SetTrie-first tag lookup with hit-rate telemetry for Tag Generator."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from zetarix.scoring.set_trie import SetTrieIndex, SetTrieItem
from zetarix.inference.vocabulary import constrain_tags
from zetarix.pretrain.dataset.schemas import TagGeneratorExample

logger = logging.getLogger("zetarix.inference.set_trie")

_FOCUS = frozenset({"Australia", "Singapore", "Malaysia"})


@dataclass
class SetTrieTaggerStats:
    trie_hits: int = 0
    trie_misses: int = 0
    llm_fallbacks: int = 0

    @property
    def trie_attempts(self) -> int:
        return self.trie_hits + self.trie_misses

    @property
    def hit_rate(self) -> float:
        return self.trie_hits / self.trie_attempts if self.trie_attempts else 0.0

    def to_dict(self) -> dict:
        return {
            "trie_hits": self.trie_hits,
            "trie_misses": self.trie_misses,
            "llm_fallbacks": self.llm_fallbacks,
            "hit_rate": round(self.hit_rate, 4),
        }


_STATS = SetTrieTaggerStats()


def get_stats() -> SetTrieTaggerStats:
    return _STATS


def reset_stats() -> None:
    global _STATS
    _STATS = SetTrieTaggerStats()


@dataclass
class SetTrieTagger:
    """Deterministic tag lookup from precedent tags before LLM fallback."""

    index: SetTrieIndex
    examples_by_id: dict[str, TagGeneratorExample] = field(default_factory=dict)

    @classmethod
    def from_examples(cls, examples: list[TagGeneratorExample]) -> "SetTrieTagger":
        positives = [ex for ex in examples if ex.label == "positive" and ex.indicator_tags]
        items = [
            SetTrieItem(node_id=ex.source_id or str(i), tags=frozenset(ex.indicator_tags))
            for i, ex in enumerate(positives)
        ]
        by_id = {ex.source_id or str(i): ex for i, ex in enumerate(positives)}
        return cls(index=SetTrieIndex(items), examples_by_id=by_id)

    def lookup(
        self,
        *,
        precedent_tags: frozenset[str],
        jurisdiction: str,
        pillar: int,
    ) -> tuple[str, ...] | None:
        """Return indicator tags if SetTrie finds a matching verified example."""
        global _STATS
        if not precedent_tags:
            _STATS.trie_misses += 1
            return None

        candidates = self.index.query_subsets(precedent_tags)
        if not candidates:
            _STATS.trie_misses += 1
            logger.debug("SetTrie miss pillar=%s jurisdiction=%s tags=%s", pillar, jurisdiction, precedent_tags)
            return None

        for cid in candidates:
            ex = self.examples_by_id.get(cid)
            if ex is None:
                continue
            if ex.jurisdiction != jurisdiction or ex.pillar != pillar:
                continue
            tags = constrain_tags(ex.indicator_tags, pillar)
            if tags:
                _STATS.trie_hits += 1
                logger.info(
                    "SetTrie hit jurisdiction=%s pillar=%s tags=%s -> %s",
                    jurisdiction,
                    pillar,
                    precedent_tags,
                    tags,
                )
                return tags

        _STATS.trie_misses += 1
        return None

def record_llm_fallback() -> None:
    global _STATS
    _STATS.llm_fallbacks += 1
