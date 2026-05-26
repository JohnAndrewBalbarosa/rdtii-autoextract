"""Stage 5a — FCA generality hierarchy (cluster -> tree)."""

from __future__ import annotations

from adapters.extraction.structural_extractor import StructuralExtractor
from adapters.graph.fca_hierarchy import FcaHierarchyBuilder
from core.domain.document import ParsedDocument


def test_empty_input_yields_empty_lattice() -> None:
    lattice = FcaHierarchyBuilder().build([])
    assert lattice.concepts == ()
    assert lattice.root_intents == ()


def test_general_concepts_have_fewer_tags_than_specific(parsed_document: ParsedDocument) -> None:
    nodes = StructuralExtractor().extract(parsed_document)
    lattice = FcaHierarchyBuilder().build(nodes)

    assert lattice.concepts  # non-empty
    # Denotative <-> connotative: more intent (tags) implies smaller-or-equal extent.
    for concept in lattice.concepts:
        for parent_intent in concept.parent_intents:
            assert parent_intent < concept.intent  # parents are strictly more general

    # Roots (entry points) are the most general: they carry few tags.
    most_specific = max(lattice.concepts, key=lambda c: len(c.intent))
    assert all(len(root) <= len(most_specific.intent) for root in lattice.root_intents)


def test_hierarchy_is_deterministic(parsed_document: ParsedDocument) -> None:
    nodes = StructuralExtractor().extract(parsed_document)
    assert FcaHierarchyBuilder().build(nodes) == FcaHierarchyBuilder().build(nodes)
