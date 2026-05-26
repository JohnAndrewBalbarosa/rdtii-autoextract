"""Extraction port — Stage 1 interface (deterministic structural tagging).

A SectionExtractor turns a ParsedDocument into tagged ConceptNodes WITHOUT any model:
tags come from the heading breadcrumb, and blocks within the same section scope are
combined into one node. The existing `Captioner`/`Tagger` ports in graph.py remain for
a future model-based path but are NOT wired by the reference pipeline. See
docs/GRAPH_PIPELINE.md and core/pipeline/graph_pipeline.py.
"""

from __future__ import annotations

from typing import Protocol

from core.domain.document import ParsedDocument
from core.domain.graph import ConceptNode


class SectionExtractor(Protocol):
    """Stage 1 — deterministic structural extraction: document -> tagged nodes."""

    def extract(self, document: ParsedDocument) -> list[ConceptNode]: ...
