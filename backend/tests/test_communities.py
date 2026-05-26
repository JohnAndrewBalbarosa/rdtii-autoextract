"""Stage 4 — Louvain community detection (clusters)."""

from __future__ import annotations

from adapters.graph.louvain_communities import LouvainCommunityDetector
from adapters.graph.networkx_graph_builder import NetworkxGraphBuilder
from core.domain.graph import ConceptNode, Edge


def _node(section_id: str) -> ConceptNode:
    return ConceptNode(section_id, "u", "", "", frozenset(), "en")


def _two_cluster_graph():
    # Two tight triangles ({a,b,c} and {x,y,z}) joined by one weak bridge.
    nodes = [_node(n) for n in ("a", "b", "c", "x", "y", "z")]
    edges = [
        Edge("a", "b", 1.0), Edge("b", "c", 1.0), Edge("a", "c", 1.0),
        Edge("x", "y", 1.0), Edge("y", "z", 1.0), Edge("x", "z", 1.0),
        Edge("c", "x", 0.05),
    ]
    return NetworkxGraphBuilder().build(nodes, edges)


def test_detects_two_communities() -> None:
    graph = _two_cluster_graph()
    communities = LouvainCommunityDetector(seed=42).detect(graph)
    assert len(communities) == 2
    # Every node belongs to exactly one community.
    members = [m for c in communities for m in c.member_ids]
    assert sorted(members) == ["a", "b", "c", "x", "y", "z"]


def test_community_ids_are_deterministic() -> None:
    graph = _two_cluster_graph()
    first = LouvainCommunityDetector(seed=42).detect(graph)
    second = LouvainCommunityDetector(seed=42).detect(graph)
    assert first == second


def test_empty_graph_yields_no_communities() -> None:
    empty = NetworkxGraphBuilder().build([], [])
    assert LouvainCommunityDetector().detect(empty) == []
