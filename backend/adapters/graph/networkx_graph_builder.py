"""Stage 2/3 — assemble the weighted graph and prune below a calibrated theta.

Conceptually every node starts connected to every other (a complete graph); pruning is
the eraser, not the glue. In practice the pipeline only scores pairs that share at least
one tag (the cheap stand-in for N^2 edges), then this builder drops edges with
weight < theta. Optional mutual top-k keeps an edge only when each endpoint ranks the
other among its strongest neighbours — this kills "hub" nodes that link to everything.

Pseudo-deterministic: no RNG, sorted tie-breaking, so the same nodes + edges + theta
yield a byte-for-byte identical graph (needed for the audit view, R6/R15). This module is
also the single home for ConceptGraph -> networkx conversion, reused by the community and
PageRank adapters.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

import networkx as nx

from core.domain.graph import ConceptGraph, ConceptNode, Edge


class NetworkxGraphBuilder:
    """Deterministic GraphBuilder: assemble + threshold/mutual-top-k prune."""

    def __init__(self, mutual_top_k: int | None = None) -> None:
        self._mutual_top_k = mutual_top_k

    def build(self, nodes: Sequence[ConceptNode], edges: Sequence[Edge]) -> ConceptGraph:
        ordered_nodes = tuple(sorted(nodes, key=lambda n: n.section_id))
        ordered_edges = tuple(
            sorted(edges, key=lambda e: (-e.weight, e.source_id, e.target_id))
        )
        # threshold 0.0 here = "unpruned"; prune() applies the calibrated theta.
        return ConceptGraph(nodes=ordered_nodes, edges=ordered_edges, threshold=0.0)

    def prune(self, graph: ConceptGraph, threshold: float) -> ConceptGraph:
        survivors = [e for e in graph.edges if e.weight >= threshold]

        if self._mutual_top_k is not None:
            survivors = self._apply_mutual_top_k(survivors, self._mutual_top_k)

        ordered = tuple(sorted(survivors, key=lambda e: (-e.weight, e.source_id, e.target_id)))
        return ConceptGraph(nodes=graph.nodes, edges=ordered, threshold=threshold)

    @staticmethod
    def _apply_mutual_top_k(edges: Sequence[Edge], k: int) -> list[Edge]:
        # Build undirected adjacency: node -> [(weight, neighbour_id, edge)]
        adjacency: dict[str, list[tuple[float, str, Edge]]] = defaultdict(list)
        for edge in edges:
            adjacency[edge.source_id].append((edge.weight, edge.target_id, edge))
            adjacency[edge.target_id].append((edge.weight, edge.source_id, edge))

        top_neighbours: dict[str, set[str]] = {}
        for node_id, neighbours in adjacency.items():
            ranked = sorted(neighbours, key=lambda item: (-item[0], item[1]))
            top_neighbours[node_id] = {nbr_id for _, nbr_id, _ in ranked[:k]}

        kept: list[Edge] = []
        for edge in edges:
            if (
                edge.target_id in top_neighbours.get(edge.source_id, set())
                and edge.source_id in top_neighbours.get(edge.target_id, set())
            ):
                kept.append(edge)
        return kept


def to_networkx(graph: ConceptGraph) -> nx.Graph:
    """Convert a ConceptGraph into a weighted, undirected networkx graph.

    Shared by the community and PageRank adapters so the conversion lives in one place.
    """
    g = nx.Graph()
    for node in graph.nodes:
        g.add_node(node.section_id)
    for edge in graph.edges:
        g.add_edge(edge.source_id, edge.target_id, weight=edge.weight)
    return g
