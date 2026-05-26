"""Stage 5a — generality hierarchy via Formal Concept Analysis (cluster -> tree).

Built from the node x tag matrix, NOT from the pruned edges — the lattice is a parallel
artifact from the same tagged nodes, so tweaking theta never reshapes the tree. FCA orders
concepts by the denotative <-> connotative gradient: a concept's extent is the example
sections it covers, its intent is the tags describing it. Fewer tags => more examples =>
more general (root / entry point); more tags => fewer examples => deeper / more specific.

Deterministic: objects and properties are sorted before building, so the `concepts` (MIT)
lattice is reproducible.
"""

from __future__ import annotations

from typing import Sequence

from concepts import Context

from core.domain.graph import Concept, ConceptLattice, ConceptNode

_OBJ_PREFIX = "node::"  # namespaces section ids so they never collide with tag names


class FcaHierarchyBuilder:
    """Deterministic HierarchyBuilder: node x tag matrix -> FCA concept lattice."""

    def build(self, nodes: Sequence[ConceptNode]) -> ConceptLattice:
        section_ids = sorted(node.section_id for node in nodes)
        properties = sorted({tag for node in nodes for tag in node.tags})

        if not section_ids or not properties:
            return ConceptLattice(concepts=(), root_intents=())

        # `concepts` requires object and property labels to be disjoint; section ids and
        # tags can collide (a heading is both a node id and a tag), so namespace objects.
        tags_by_id = {node.section_id: node.tags for node in nodes}
        objects = tuple(f"{_OBJ_PREFIX}{sid}" for sid in section_ids)
        bools = tuple(
            tuple(prop in tags_by_id[sid] for prop in properties) for sid in section_ids
        )

        lattice = Context(objects, tuple(properties), bools).lattice

        concepts = tuple(
            sorted(
                (
                    Concept(
                        intent=frozenset(concept.intent),
                        extent=frozenset(obj[len(_OBJ_PREFIX):] for obj in concept.extent),
                        parent_intents=tuple(
                            frozenset(parent.intent) for parent in concept.upper_neighbors
                        ),
                    )
                    for concept in lattice
                ),
                key=lambda c: (len(c.intent), sorted(c.intent), sorted(c.extent)),
            )
        )

        # Entry points = the most general non-trivial categories: the lower neighbours of
        # the supremum (the top concept that covers every section).
        root_intents = tuple(
            frozenset(neighbour.intent) for neighbour in lattice.supremum.lower_neighbors
        )
        return ConceptLattice(concepts=concepts, root_intents=root_intents)
