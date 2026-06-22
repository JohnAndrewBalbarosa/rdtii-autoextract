"""LouvainCommunityDetector — deterministic community detection (networkx + python-louvain).

Builds a weighted, undirected graph from the scorer's edges (plus every node, so isolated
sections still land in a community), runs Louvain modularity optimisation with a fixed seed,
then relabels communities by their smallest member for a stable, reproducible id assignment.
Cycles in the graph are fine — communities never become a tree.

License: ``python-louvain`` (``community``) is BSD; ``networkx`` is BSD — both Apache-safe.
The GPL ``leidenalg``/``igraph`` stack is deliberately avoided.
"""

from __future__ import annotations

from collections import Counter
from typing import Sequence

import community as community_louvain
import networkx as nx

from core.domain.cluster import ClusterEdge, Community
from core.domain.concept_node import ConceptNode

_SEED = 42  # fixed seed → deterministic partition


class LouvainCommunityDetector:
    """Partition nodes+edges into communities deterministically via Louvain."""

    def detect(
        self, nodes: Sequence[ConceptNode], edges: Sequence[ClusterEdge]
    ) -> list[Community]:
        if not nodes:
            return []

        tags_of = {node.section_id: set(node.tags) for node in nodes}

        graph = nx.Graph()
        for section_id in sorted(tags_of):  # insertion order sorted → deterministic layout
            graph.add_node(section_id)
        for edge in sorted(edges, key=lambda e: (e.source, e.target)):
            graph.add_edge(edge.source, edge.target, weight=edge.weight)

        partition = community_louvain.best_partition(graph, weight="weight", random_state=_SEED)

        members_by_part: dict[int, list[str]] = {}
        for section_id, part in partition.items():
            members_by_part.setdefault(part, []).append(section_id)

        # Relabel: order communities by their smallest member for a stable id.
        ordered_parts = sorted(members_by_part.values(), key=lambda ids: min(ids))
        communities: list[Community] = []
        for new_id, members in enumerate(ordered_parts):
            members_sorted = tuple(sorted(members))
            communities.append(
                Community(
                    community_id=new_id,
                    members=members_sorted,
                    shared_tags=self._shared_tags(members_sorted, tags_of),
                )
            )
        return communities

    @staticmethod
    def _shared_tags(members: tuple[str, ...], tags_of: dict[str, set[str]]) -> tuple[str, ...]:
        """Tags common to all members; else the tags carried by a majority (deterministic)."""
        member_tag_sets = [tags_of.get(m, set()) for m in members]
        if not member_tag_sets:
            return ()
        intersection = set.intersection(*member_tag_sets) if member_tag_sets else set()
        if intersection:
            return tuple(sorted(intersection))
        # Fallback: tags appearing in > half the members, ranked by frequency then name.
        counts = Counter(tag for tags in member_tag_sets for tag in tags)
        threshold = len(members) / 2
        majority = [tag for tag, count in counts.items() if count > threshold]
        majority.sort(key=lambda t: (-counts[t], t))
        return tuple(majority)
