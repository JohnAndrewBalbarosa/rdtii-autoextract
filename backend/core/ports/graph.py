"""Concept-graph ports — interfaces for the 5-stage graph pipeline.

Each concrete model/library (BGE-M3 tagger, NetworkX, FCA, PageRank) implements one of
these Protocols as an adapter. The core never imports those libraries (R12, R16).
See docs/GRAPH_PIPELINE.md.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from core.domain.graph import (
    Community,
    ConceptGraph,
    ConceptLattice,
    ConceptNode,
    Edge,
)


class Captioner(Protocol):
    """Stage 0/1a — at OCR time, produce a SigLIP-style descriptor of a section.

    Runs up front, alongside/after OCR (incl. scanned, non-English, visual layout — R19).
    Its caption is the BASIS that the Tagger embeds and scores. Reference adapter:
    a vision-language model (e.g. Qwen2-VL / ColQwen2, Apache) over the section image,
    falling back to OCR text when the layout is plain.
    """

    def caption(self, raw_section: bytes, ocr_text: str, language: str) -> str: ...


class Tagger(Protocol):
    """Stage 1 — multi-label tagging from text + caption (SigLIP-style sigmoid scoring)."""

    def tag(self, section_id: str, text: str, caption: str, language: str) -> frozenset[str]: ...


class EdgeScorer(Protocol):
    """Stage 2 — relation strength between two nodes (tag overlap + embedding cosine)."""

    def score(self, a: ConceptNode, b: ConceptNode) -> Edge: ...


class GraphBuilder(Protocol):
    """Stage 2/3 — assemble the weighted graph and prune edges below a calibrated theta.

    Pseudo-deterministic: same inputs + same theta + fixed seeds -> identical graph.
    """

    def build(self, nodes: Sequence[ConceptNode], edges: Sequence[Edge]) -> ConceptGraph: ...
    def prune(self, graph: ConceptGraph, threshold: float) -> ConceptGraph: ...


class CommunityDetector(Protocol):
    """Stage 4 — cluster the pruned graph into themed groupings (Louvain/Leiden, fixed seed)."""

    def detect(self, graph: ConceptGraph) -> list[Community]: ...


class HierarchyBuilder(Protocol):
    """Stage 5a — induce the FCA concept lattice (general roots -> specific leaves)."""

    def build(self, nodes: Sequence[ConceptNode]) -> ConceptLattice: ...


class GraphRanker(Protocol):
    """Stage 5b — weighted / personalized PageRank over the concept graph.

    `seeds` selects entry-point root nodes for personalized ranking; None = global.
    """

    def rank(self, graph: ConceptGraph, seeds: Sequence[str] | None = None) -> dict[str, float]: ...
