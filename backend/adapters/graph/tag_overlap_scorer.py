"""Stage 2 — deterministic edge scorer (tag overlap only, no embeddings).

Relatedness between two nodes is driven by how many tags they share, IDF-weighted so
rare shared tags count more than ubiquitous ones (a tag every node carries says little).
Concretely the weight is an IDF-weighted Jaccard over the two tag sets. The Edge.basis
records the shared tags so a reviewer can verify the link in seconds (R6) — no black-box
edges. Pure set math: same nodes always produce the same weight.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Sequence

from core.domain.graph import ConceptNode, Edge


class TagOverlapEdgeScorer:
    """Deterministic EdgeScorer: weight = IDF-weighted Jaccard of shared tags."""

    def __init__(self, idf: dict[str, float]) -> None:
        self._idf = idf

    @classmethod
    def from_nodes(cls, nodes: Sequence[ConceptNode]) -> "TagOverlapEdgeScorer":
        """Compute smoothed IDF for every tag from the corpus of nodes."""
        total = len(nodes)
        doc_freq: Counter[str] = Counter()
        for node in nodes:
            for tag in node.tags:
                doc_freq[tag] += 1
        # Smoothed IDF; +1 keeps weights positive and avoids div-by-zero.
        idf = {tag: math.log((total + 1) / (df + 1)) + 1.0 for tag, df in doc_freq.items()}
        return cls(idf)

    def score(self, a: ConceptNode, b: ConceptNode) -> Edge:
        shared = a.tags & b.tags
        union = a.tags | b.tags
        if not shared or not union:
            weight = 0.0
        else:
            shared_mass = sum(self._idf.get(t, 1.0) for t in shared)
            union_mass = sum(self._idf.get(t, 1.0) for t in union)
            weight = shared_mass / union_mass if union_mass else 0.0

        basis = tuple(f"tag:{t}" for t in sorted(shared))
        return Edge(source_id=a.section_id, target_id=b.section_id, weight=weight, basis=basis)
