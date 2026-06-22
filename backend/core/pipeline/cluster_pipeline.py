"""Cluster pipeline — ConceptNode seed → similarity edges → communities (the 2nd artifact).

Orchestrates the injected ``SimilarityScorer`` and ``CommunityDetector`` ports into a
``ClusterGraph`` and serialises it. Dependency-injected so ``core`` never imports networkx or
louvain; ``run.py`` wires the concrete adapters. Pure given its delegates — no I/O except
``write_clusters``.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Sequence

from core.domain.cluster import ClusterGraph
from core.domain.concept_node import ConceptNode
from core.ports.clustering import CommunityDetector, SimilarityScorer


def build_clusters(
    nodes: Sequence[ConceptNode],
    scorer: SimilarityScorer,
    detector: CommunityDetector,
) -> ClusterGraph:
    """Build the cluster artifact from tagged nodes via the injected scorer + detector."""
    node_list = list(nodes)
    if not node_list:
        return ClusterGraph()
    edges = scorer.score_edges(node_list)
    communities = detector.detect(node_list, edges)
    return ClusterGraph(edges=tuple(edges), communities=tuple(communities))


def discovery_candidates(graph: ClusterGraph, matched_ids) -> dict[int, list[str]]:
    """Clustering-assisted NEW-discovery candidates.

    For each community that contains at least one *matched* node (a section the matcher
    mapped to an indicator), the community's other, unmatched members are surfaced as
    candidate NEW provisions worth review — they sit next to KNOWN-mapped law in concept
    space but the deterministic matcher did not map them. Returned per community id; empty
    when nothing qualifies. This does NOT auto-emit findings (that would hurt precision);
    it is a review aid, written into the cluster artifact.
    """
    matched = set(matched_ids)
    out: dict[int, list[str]] = {}
    for community in graph.communities:
        members = set(community.members)
        if members & matched:
            candidates = sorted(members - matched)
            if candidates:
                out[community.community_id] = candidates
    return out


def clusters_to_json(graph: ClusterGraph, candidates: dict | None = None) -> dict:
    """Serialise a ``ClusterGraph`` to a plain, deterministic JSON-able dict.

    When ``candidates`` is provided (from :func:`discovery_candidates`) a
    ``discovery_candidates`` key is added mapping community id → candidate section ids.
    """
    payload = OrderedDict(
        (
            (
                "communities",
                [
                    OrderedDict(
                        (
                            ("community_id", c.community_id),
                            ("members", list(c.members)),
                            ("shared_tags", list(c.shared_tags)),
                        )
                    )
                    for c in graph.communities
                ],
            ),
            (
                "edges",
                [
                    OrderedDict(
                        (
                            ("source", e.source),
                            ("target", e.target),
                            ("weight", e.weight),
                            ("shared_tags", list(e.shared_tags)),
                        )
                    )
                    for e in graph.edges
                ],
            ),
        )
    )
    if candidates is not None:
        payload["discovery_candidates"] = {
            str(community_id): list(ids) for community_id, ids in sorted(candidates.items())
        }
    return payload


def write_clusters(graph: ClusterGraph, path, candidates: dict | None = None) -> None:
    """Write the cluster artifact JSON to ``path`` (UTF-8, pretty, non-ASCII preserved)."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(clusters_to_json(graph, candidates), handle, ensure_ascii=False, indent=2)
