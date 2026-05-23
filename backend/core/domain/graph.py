"""Concept-graph domain entities — framework-agnostic, immutable.

Nodes (tagged law sections) connect into a weighted graph; weak edges are pruned;
clusters and a generality hierarchy emerge. No graph library is imported here.
See docs/GRAPH_PIPELINE.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class ConceptNode:
    """A law section turned into a graph node, with multiple tags (Stage 1)."""

    section_id: str
    document_url: str
    text: str  # OCR'd section text
    caption: str  # SigLIP-style descriptor produced at OCR time; the BASIS for tags
    tags: frozenset[str]  # multi-label, derived from text + caption
    language: str

    def with_tags(self, tags: frozenset[str]) -> "ConceptNode":
        """Return a new node with replaced tags (no mutation)."""
        return replace(self, tags=tags)


@dataclass(frozen=True)
class Edge:
    """A weighted, explainable relation between two nodes (Stage 2/3).

    `basis` records *why* the edge exists (shared tags, cosine) so a reviewer can
    verify it in seconds (R6). No black-box edges.
    """

    source_id: str
    target_id: str
    weight: float
    basis: tuple[str, ...] = ()  # e.g. ("tag:cross-border-transfer", "cosine:0.82")


@dataclass(frozen=True)
class ConceptGraph:
    """The pruned, weighted concept web (Stage 3 output)."""

    nodes: tuple[ConceptNode, ...]
    edges: tuple[Edge, ...]
    threshold: float  # the calibrated theta applied during pruning


@dataclass(frozen=True)
class Community:
    """A detected grouping of nodes — the Obsidian-style cluster (Stage 4)."""

    community_id: str
    member_ids: frozenset[str]


@dataclass(frozen=True)
class Concept:
    """An FCA concept: extent (examples) vs intent (tags) — Stage 5.

    More intent (richer description) implies smaller extent (fewer, more specific
    examples). This is the denotative <-> connotative gradient.
    """

    intent: frozenset[str]  # tags / description (connotation)
    extent: frozenset[str]  # section_ids covered (denotation)
    parent_intents: tuple[frozenset[str], ...] = field(default=())


@dataclass(frozen=True)
class ConceptLattice:
    """Generality hierarchy over concepts: general roots -> specific leaves (Stage 5)."""

    concepts: tuple[Concept, ...]
    root_intents: tuple[frozenset[str], ...]  # entry-point (most general) concepts
