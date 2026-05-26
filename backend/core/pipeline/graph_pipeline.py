"""Concept-graph pipeline — orchestrates Stage 1 -> 5 over the ports.

Pure composition: this module depends only on domain types and port Protocols, never on a
concrete adapter (R12, R16). Wire real adapters at the edge and inject them. The flow:

    extract (Stage 1)        -> tagged ConceptNodes
    score + build + prune    -> weighted, pruned ConceptGraph (Stage 2/3)
    detect communities       -> clusters (Stage 4)
    build FCA lattice        -> generality tree (Stage 5a, from node x tag matrix)
    rank                     -> within-graph importance (Stage 5b)

Edge candidates are generated here via a tag inverted index (only pairs sharing >= 1 tag),
the cheap stand-in for the conceptual complete graph. Deterministic throughout.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Sequence

from core.domain.document import ParsedDocument
from core.domain.graph import Community, ConceptGraph, ConceptLattice, ConceptNode, Edge
from core.ports.extraction import SectionExtractor
from core.ports.graph import (
    CommunityDetector,
    EdgeScorer,
    GraphBuilder,
    GraphRanker,
    HierarchyBuilder,
)

# A factory builds an EdgeScorer from the extracted nodes (e.g. to compute corpus IDF).
EdgeScorerFactory = Callable[[Sequence[ConceptNode]], EdgeScorer]


@dataclass(frozen=True)
class GraphPipelineResult:
    """The bundle of artifacts produced by one pipeline run."""

    nodes: tuple[ConceptNode, ...]
    graph: ConceptGraph  # pruned
    communities: tuple[Community, ...]
    lattice: ConceptLattice
    ranks: dict[str, float]


class GraphPipeline:
    """Composes the five concept-graph stages over injected port implementations."""

    def __init__(
        self,
        extractor: SectionExtractor,
        scorer_factory: EdgeScorerFactory,
        builder: GraphBuilder,
        detector: CommunityDetector,
        hierarchy: HierarchyBuilder,
        ranker: GraphRanker,
    ) -> None:
        self._extractor = extractor
        self._scorer_factory = scorer_factory
        self._builder = builder
        self._detector = detector
        self._hierarchy = hierarchy
        self._ranker = ranker

    def run(
        self,
        document: ParsedDocument,
        *,
        theta: float,
        seeds: Sequence[str] | None = None,
    ) -> GraphPipelineResult:
        nodes = self._extractor.extract(document)  # Stage 1

        scorer = self._scorer_factory(nodes)
        edges = self._candidate_edges(nodes, scorer)  # Stage 2
        graph = self._builder.build(nodes, edges)
        pruned = self._builder.prune(graph, theta)  # Stage 3

        communities = self._detector.detect(pruned)  # Stage 4
        lattice = self._hierarchy.build(nodes)  # Stage 5a (from nodes, not edges)
        ranks = self._ranker.rank(pruned, seeds)  # Stage 5b

        return GraphPipelineResult(
            nodes=tuple(nodes),
            graph=pruned,
            communities=tuple(communities),
            lattice=lattice,
            ranks=ranks,
        )

    @staticmethod
    def _candidate_edges(nodes: Sequence[ConceptNode], scorer: EdgeScorer) -> list[Edge]:
        """Score every node pair that shares at least one tag (deterministic order)."""
        index: dict[str, list[ConceptNode]] = defaultdict(list)
        for node in nodes:
            for tag in node.tags:
                index[tag].append(node)

        seen: set[tuple[str, str]] = set()
        edges: list[Edge] = []
        for members in index.values():
            ordered = sorted(members, key=lambda n: n.section_id)
            for i in range(len(ordered)):
                for j in range(i + 1, len(ordered)):
                    a, b = ordered[i], ordered[j]
                    key = (a.section_id, b.section_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append(scorer.score(a, b))

        return sorted(edges, key=lambda e: (-e.weight, e.source_id, e.target_id))
