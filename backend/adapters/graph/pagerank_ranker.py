"""Stage 5b — within-graph importance via weighted PageRank.

Not Google's web PageRank but the same eigenvector-centrality model run on the concept
graph: it scores which nodes are influential hubs. With `seeds`, Personalized PageRank
measures which nodes are "closest" to a chosen entry point — the FCA tree gives the shape
(specificity), PageRank gives the ordering within a level. Deterministic power iteration
over networkx (BSD).
"""

from __future__ import annotations

from typing import Sequence

import networkx as nx

from adapters.graph.networkx_graph_builder import to_networkx
from core.domain.graph import ConceptGraph


class PagerankRanker:
    """Deterministic GraphRanker: weighted / personalized PageRank."""

    def rank(self, graph: ConceptGraph, seeds: Sequence[str] | None = None) -> dict[str, float]:
        g = to_networkx(graph)
        if g.number_of_nodes() == 0:
            return {}

        personalization = None
        if seeds:
            valid = [s for s in seeds if s in g]
            if valid:
                personalization = {node: (1.0 if node in valid else 0.0) for node in g.nodes}

        return nx.pagerank(g, weight="weight", personalization=personalization)
