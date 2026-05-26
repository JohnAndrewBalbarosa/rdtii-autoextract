"""Stage 4 — community detection (clusters), the Obsidian-style groupings.

Runs Louvain modularity optimisation (python-louvain, BSD — NOT the GPL leidenalg) over
the pruned, weighted graph with a fixed seed, so the clustering is reproducible. Community
ids are assigned deterministically from the sorted membership, not from Louvain's internal
numbering, so two runs label the same clusters identically.
"""

from __future__ import annotations

import community as community_louvain

from adapters.graph.networkx_graph_builder import to_networkx
from core.domain.graph import Community, ConceptGraph

_DEFAULT_SEED = 42


class LouvainCommunityDetector:
    """Deterministic CommunityDetector via Louvain with a fixed seed."""

    def __init__(self, seed: int = _DEFAULT_SEED) -> None:
        self._seed = seed

    def detect(self, graph: ConceptGraph) -> list[Community]:
        g = to_networkx(graph)
        if g.number_of_nodes() == 0:
            return []

        partition = community_louvain.best_partition(
            g, weight="weight", random_state=self._seed
        )

        members_by_label: dict[int, set[str]] = {}
        for node_id, label in partition.items():
            members_by_label.setdefault(label, set()).add(node_id)

        # Deterministic ids: sort clusters by their sorted membership, then number them.
        ordered = sorted(members_by_label.values(), key=lambda ids: sorted(ids))
        return [
            Community(community_id=f"c{index}", member_ids=frozenset(members))
            for index, members in enumerate(ordered)
        ]
