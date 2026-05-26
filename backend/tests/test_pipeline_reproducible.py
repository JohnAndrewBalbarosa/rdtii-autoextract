"""End-to-end: the whole Stage 1->5 pipeline is byte-for-byte reproducible."""

from __future__ import annotations

from core.domain.document import ParsedDocument
from core.pipeline.graph_pipeline import GraphPipeline


def test_pipeline_runs_end_to_end(pipeline: GraphPipeline, parsed_document: ParsedDocument) -> None:
    result = pipeline.run(parsed_document, theta=0.1)
    assert len(result.nodes) == 7
    assert result.graph.threshold == 0.1
    assert result.communities  # at least one cluster
    assert result.lattice.concepts  # a tree was built
    assert set(result.ranks) == {n.section_id for n in result.nodes}


def test_same_input_same_seed_is_identical(
    pipeline: GraphPipeline, parsed_document: ParsedDocument
) -> None:
    first = pipeline.run(parsed_document, theta=0.1, seeds=["data-protection-act"])
    second = pipeline.run(parsed_document, theta=0.1, seeds=["data-protection-act"])
    assert first.nodes == second.nodes
    assert first.graph == second.graph
    assert first.communities == second.communities
    assert first.lattice == second.lattice
    assert first.ranks == second.ranks
