"""Stage 5b — weighted / personalized PageRank ranking."""

from __future__ import annotations

from adapters.graph.networkx_graph_builder import NetworkxGraphBuilder
from adapters.graph.pagerank_ranker import PagerankRanker
from core.domain.graph import ConceptNode, Edge


def _node(section_id: str) -> ConceptNode:
    return ConceptNode(section_id, "u", "", "", frozenset(), "en")


def _star_graph():
    # Hub "h" linked to three leaves -> hub should rank highest.
    nodes = [_node(n) for n in ("h", "x", "y", "z")]
    edges = [Edge("h", "x", 1.0), Edge("h", "y", 1.0), Edge("h", "z", 1.0)]
    return NetworkxGraphBuilder().build(nodes, edges)


def test_ranks_sum_to_one_and_hub_wins() -> None:
    ranks = PagerankRanker().rank(_star_graph())
    assert abs(sum(ranks.values()) - 1.0) < 1e-6
    assert ranks["h"] == max(ranks.values())


def test_personalization_shifts_mass_to_seed() -> None:
    graph = _star_graph()
    ranker = PagerankRanker()
    base = ranker.rank(graph)
    personalized = ranker.rank(graph, seeds=["x"])
    assert personalized["x"] > base["x"]


def test_empty_graph_returns_empty() -> None:
    empty = NetworkxGraphBuilder().build([], [])
    assert PagerankRanker().rank(empty) == {}


def test_ranking_is_deterministic() -> None:
    graph = _star_graph()
    assert PagerankRanker().rank(graph) == PagerankRanker().rank(graph)
