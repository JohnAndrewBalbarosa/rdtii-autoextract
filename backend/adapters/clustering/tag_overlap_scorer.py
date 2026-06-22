"""TagOverlapScorer — deterministic IDF-weighted-Jaccard edges over ConceptNode tags.

Two sections are related when they share tags; rare shared tags count more (IDF). Edges are
built only between nodes that share at least one tag (sparse — no O(n²) materialisation of
the complete graph; an inverted tag→nodes index yields the candidate pairs). Every edge
records its ``shared_tags`` so a reviewer can verify the connection. Pure + deterministic:
nodes sorted by ``section_id``, weights rounded, no RNG.
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Sequence

from core.domain.cluster import ClusterEdge
from core.domain.concept_node import ConceptNode

_WEIGHT_PRECISION = 6


class TagOverlapScorer:
    """Scores edges by IDF-weighted Jaccard over shared tags."""

    def score_edges(self, nodes: Sequence[ConceptNode]) -> list[ClusterEdge]:
        ordered = sorted(nodes, key=lambda n: n.section_id)
        if len(ordered) < 2:
            return []

        total = len(ordered)
        # Document frequency per tag (how many nodes carry it) → IDF.
        doc_freq: dict[str, int] = {}
        for node in ordered:
            for tag in node.tags:
                doc_freq[tag] = doc_freq.get(tag, 0) + 1
        idf = {tag: math.log((total + 1) / (df + 1)) + 1.0 for tag, df in doc_freq.items()}

        # Inverted index → only score pairs that actually share a tag.
        by_tag: dict[str, list[str]] = {}
        tags_of = {node.section_id: node.tags for node in ordered}
        for node in ordered:
            for tag in node.tags:
                by_tag.setdefault(tag, []).append(node.section_id)

        candidate_pairs: set[tuple[str, str]] = set()
        for ids in by_tag.values():
            if len(ids) < 2:
                continue
            for a, b in combinations(sorted(set(ids)), 2):
                candidate_pairs.add((a, b))

        edges: list[ClusterEdge] = []
        for a, b in sorted(candidate_pairs):
            tags_a, tags_b = tags_of[a], tags_of[b]
            shared = tags_a & tags_b
            if not shared:
                continue
            union = tags_a | tags_b
            num = sum(idf[t] for t in shared)
            den = sum(idf[t] for t in union)
            weight = round(num / den, _WEIGHT_PRECISION) if den else 0.0
            if weight <= 0:
                continue
            edges.append(
                ClusterEdge(
                    source=a,
                    target=b,
                    weight=weight,
                    shared_tags=tuple(sorted(shared)),
                )
            )
        return edges
