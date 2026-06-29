"""Tests for the restored cluster-graph artifact (2nd pipeline output).

Covers the tag-overlap similarity scorer, the Louvain community detector, and the
cluster pipeline orchestration/serialisation. Determinism is asserted because the artifact
must be reproducible for audit.
"""

from __future__ import annotations

from adapters.clustering import LouvainCommunityDetector, TagOverlapScorer
from core.domain.concept_node import ConceptNode
from core.pipeline.cluster_pipeline import (
    build_clusters,
    clusters_to_json,
    discovery_candidates,
)


def _node(section_id: str, tags: set[str]) -> ConceptNode:
    return ConceptNode(
        section_id=section_id,
        document_url="https://gov.example/act",
        text="text",
        caption="caption",
        tags=frozenset(tags),
        language="en",
    )


_NODES = [
    _node("s26", {"cross-border", "transfer", "restriction"}),
    _node("s26a", {"cross-border", "transfer", "consent"}),
    _node("s24", {"personal-data", "processing", "security"}),
    _node("s25", {"personal-data", "processing", "retention"}),
    _node("s1", {"short-title"}),  # isolated — shares no tag with the others
]


def test_scorer_only_links_shared_tag_nodes():
    edges = TagOverlapScorer().score_edges(_NODES)
    pairs = {(e.source, e.target) for e in edges}
    assert ("s26", "s26a") in pairs  # share cross-border + transfer
    assert ("s24", "s25") in pairs  # share personal-data + processing
    # The isolated short-title node shares no tag → no edge touches it.
    assert all("s1" not in (e.source, e.target) for e in edges)


def test_scorer_records_shared_tags_and_bounded_weight():
    edges = TagOverlapScorer().score_edges(_NODES)
    for edge in edges:
        assert edge.shared_tags  # audit basis present
        assert 0.0 < edge.weight <= 1.0


def test_scorer_single_node_has_no_edges():
    assert TagOverlapScorer().score_edges([_NODES[0]]) == []


def test_detector_partitions_all_nodes():
    edges = TagOverlapScorer().score_edges(_NODES)
    communities = LouvainCommunityDetector().detect(_NODES, edges)
    members = {m for c in communities for m in c.members}
    assert members == {n.section_id for n in _NODES}  # every node assigned
    # The isolated node forms its own singleton community.
    assert any(c.members == ("s1",) for c in communities)


def test_detector_groups_related_sections_together():
    edges = TagOverlapScorer().score_edges(_NODES)
    communities = LouvainCommunityDetector().detect(_NODES, edges)
    groups = [set(c.members) for c in communities]
    assert {"s26", "s26a"} in groups
    assert {"s24", "s25"} in groups


def test_clusters_deterministic():
    scorer, detector = TagOverlapScorer(), LouvainCommunityDetector()
    first = clusters_to_json(build_clusters(_NODES, scorer, detector))
    second = clusters_to_json(build_clusters(_NODES, scorer, detector))
    assert first == second


def test_empty_nodes_yield_empty_graph():
    graph = build_clusters([], TagOverlapScorer(), LouvainCommunityDetector())
    assert graph.communities == ()
    assert graph.edges == ()
    payload = clusters_to_json(graph)
    assert payload == {"communities": [], "edges": []}


def test_discovery_candidates_surfaces_unmatched_coclustered_members():
    graph = build_clusters(_NODES, TagOverlapScorer(), LouvainCommunityDetector())
    # s26 is "matched" (mapped to an indicator); its cluster-mate s26a is unmatched →
    # it is surfaced as a NEW-discovery candidate.
    candidates = discovery_candidates(graph, matched_ids={"s26"})
    surfaced = {sid for ids in candidates.values() for sid in ids}
    assert "s26a" in surfaced
    # The unrelated personal-data community has no matched node → no candidates from it.
    assert "s24" not in surfaced and "s25" not in surfaced


def test_discovery_candidates_serialised_into_artifact():
    graph = build_clusters(_NODES, TagOverlapScorer(), LouvainCommunityDetector())
    candidates = discovery_candidates(graph, matched_ids={"s26"})
    payload = clusters_to_json(graph, candidates)
    assert "discovery_candidates" in payload
    assert any("s26a" in ids for ids in payload["discovery_candidates"].values())
