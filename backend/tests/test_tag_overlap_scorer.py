"""Stage 2 — deterministic tag-overlap edge scorer."""

from __future__ import annotations

from adapters.graph.tag_overlap_scorer import TagOverlapEdgeScorer
from core.domain.graph import ConceptNode


def _node(section_id: str, tags: set[str]) -> ConceptNode:
    return ConceptNode(
        section_id=section_id,
        document_url="u",
        text="",
        caption="",
        tags=frozenset(tags),
        language="en",
    )


def test_weight_is_idf_weighted_jaccard() -> None:
    scorer = TagOverlapEdgeScorer(idf={"common": 1.0, "rare": 3.0, "x": 2.0})
    a = _node("a", {"common", "rare"})
    b = _node("b", {"common", "x"})
    edge = scorer.score(a, b)
    # shared {common}=1.0 ; union {common,rare,x}=1.0+3.0+2.0=6.0
    assert edge.weight == 1.0 / 6.0
    assert edge.basis == ("tag:common",)


def test_no_shared_tags_is_zero() -> None:
    scorer = TagOverlapEdgeScorer(idf={"p": 1.0, "q": 1.0})
    edge = scorer.score(_node("a", {"p"}), _node("b", {"q"}))
    assert edge.weight == 0.0
    assert edge.basis == ()


def test_rarer_shared_tag_weighs_more() -> None:
    # Same overlap shape, but the shared tag is rarer in one pair than the other.
    scorer = TagOverlapEdgeScorer(idf={"rare": 3.0, "common": 1.0, "u1": 1.0, "u2": 1.0, "u3": 1.0, "u4": 1.0})
    rare_pair = scorer.score(_node("a", {"rare", "u1"}), _node("b", {"rare", "u2"}))
    common_pair = scorer.score(_node("c", {"common", "u3"}), _node("d", {"common", "u4"}))
    assert rare_pair.weight > common_pair.weight


def test_from_nodes_gives_common_tags_lower_idf() -> None:
    nodes = [
        _node("a", {"common", "rare"}),
        _node("b", {"common"}),
        _node("c", {"common"}),
    ]
    scorer = TagOverlapEdgeScorer.from_nodes(nodes)
    # `common` appears 3x, `rare` once -> rare must carry more weight.
    assert scorer._idf["rare"] > scorer._idf["common"]  # noqa: SLF001 (white-box check)
