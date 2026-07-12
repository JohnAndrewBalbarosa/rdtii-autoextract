"""Closed RDTII Pillar 6/7 sub-indicator vocabulary from the golden dataset."""

from __future__ import annotations

import os
from functools import lru_cache

from zetarix.domain.indicator_codes import to_db
from zetarix.scoring.golden_dataset import GoldRecord, load_gold_records

_DEFAULT_DOCS = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "docs"
)
_FOCUS = frozenset({"Australia", "Singapore", "Malaysia"})


@lru_cache(maxsize=4)
def load_indicator_vocabulary(docs_dir: str = _DEFAULT_DOCS) -> dict[int, frozenset[str]]:
    """Return valid golden-DB indicator ids per pillar (e.g. ``6.2``)."""
    by_pillar: dict[int, set[str]] = {6: set(), 7: set()}
    for record in load_gold_records(docs_dir):
        if record.pillar_id in by_pillar:
            by_pillar[record.pillar_id].add(to_db(record.indicator_id))
    return {p: frozenset(tags) for p, tags in by_pillar.items()}


def vocabulary_for_pillar(pillar: int, docs_dir: str | None = None) -> frozenset[str]:
    vocab = load_indicator_vocabulary(docs_dir or _DEFAULT_DOCS)
    return vocab.get(pillar, frozenset())


def constrain_tags(raw_tags: list[str] | tuple[str, ...], pillar: int, docs_dir: str | None = None) -> tuple[str, ...]:
    """Keep only tags in the closed P6/P7 vocabulary for ``pillar``."""
    allowed = vocabulary_for_pillar(pillar, docs_dir)
    out: list[str] = []
    for tag in raw_tags:
        cleaned = str(tag).strip()
        if not cleaned:
            continue
        try:
            normalized = to_db(cleaned)
        except ValueError:
            continue
        if normalized in allowed:
            out.append(normalized)
    return tuple(dict.fromkeys(out))


def vocabulary_schema_enum(pillar: int, docs_dir: str | None = None) -> list[str]:
    return sorted(vocabulary_for_pillar(pillar, docs_dir))
