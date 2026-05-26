"""Stage 2/3 — graph assembly and threshold / mutual-top-k pruning."""

from __future__ import annotations

from adapters.graph.networkx_graph_builder import NetworkxGraphBuilder, to_networkx
from core.domain.graph import ConceptNode, Edge


def _node(section_id: str) -> ConceptNode:
    return ConceptNode(section_id, "u", "", "", frozenset(), "en")


def _edges() -> list[Edge]:
    return [
        Edge("a", "b", 0.9),
        Edge("a", "c", 0.3),
        Edge("b", "c", 0.1),
    ]


def test_prune_drops_edges_below_theta() -> None:
    builder = NetworkxGraphBuilder()
    nodes = [_node("a"), _node("b"), _node("c")]
    graph = builder.build(nodes, _edges())
    pruned = builder.prune(graph, threshold=0.5)
    assert [(e.source_id, e.target_id) for e in pruned.edges] == [("a", "b")]
    assert pruned.threshold == 0.5


def test_build_sorts_edges_by_weight_desc() -> None:
    builder = NetworkxGraphBuilder()
    graph = builder.build([_node("a"), _node("b"), _node("c")], _edges())
    weights = [e.weight for e in graph.edges]
    assert weights == sorted(weights, reverse=True)


def test_mutual_top_k_reduces_hub_edges() -> None:
    # Hub "h" connects to three leaves; with k=1 only the strongest mutual link survives.
    nodes = [_node(n) for n in ("h", "x", "y", "z")]
    edges = [Edge("h", "x", 0.9), Edge("h", "y", 0.5), Edge("h", "z", 0.4)]
    builder = NetworkxGraphBuilder(mutual_top_k=1)
    graph = builder.build(nodes, edges)
    pruned = builder.prune(graph, threshold=0.0)
    assert [(e.source_id, e.target_id) for e in pruned.edges] == [("h", "x")]


def test_prune_is_deterministic() -> None:
    builder = NetworkxGraphBuilder()
    graph = builder.build([_node("a"), _node("b"), _node("c")], _edges())
    assert builder.prune(graph, 0.2) == builder.prune(graph, 0.2)


def test_to_networkx_carries_weights() -> None:
    builder = NetworkxGraphBuilder()
    graph = builder.build([_node("a"), _node("b")], [Edge("a", "b", 0.7)])
    g = to_networkx(graph)
    assert g.number_of_nodes() == 2
    assert g["a"]["b"]["weight"] == 0.7
