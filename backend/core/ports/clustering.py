"""Clustering ports — keep ``core`` free of networkx/louvain (R12, ports-and-adapters).

``SimilarityScorer`` turns tagged nodes into weighted edges; ``CommunityDetector`` partitions
those nodes+edges into communities. Concrete adapters (tag-overlap scorer, Louvain detector)
live under ``adapters/clustering`` and swap by injection.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from core.domain.cluster import ClusterEdge, Community
from core.domain.concept_node import ConceptNode


class SimilarityScorer(Protocol):
    """Score pairwise similarity between tagged nodes → weighted edges."""

    def score_edges(self, nodes: Sequence[ConceptNode]) -> list[ClusterEdge]: ...


class CommunityDetector(Protocol):
    """Partition nodes (with edges) into communities deterministically."""

    def detect(
        self, nodes: Sequence[ConceptNode], edges: Sequence[ClusterEdge]
    ) -> list[Community]: ...
