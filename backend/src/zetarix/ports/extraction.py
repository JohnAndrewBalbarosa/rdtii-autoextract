"""Extraction ports for structural and guided tagging.

The deterministic extractor keeps the current baseline: ParsedDocument -> ConceptNode[]
without any model call. The guided path adds a high-context document guide and low-context
section taggers, both behind ports so model choices stay outside the core.
"""

from __future__ import annotations

from typing import Protocol

from zetarix.domain.document import (
    DocumentGuide,
    ParsedDocument,
    SectionTaggingResult,
    SectionTaggingTask,
)
from zetarix.domain.concept_node import ConceptNode


class SectionExtractor(Protocol):
    """Deterministic structural extraction: document -> tagged nodes."""

    def extract(self, document: ParsedDocument) -> list[ConceptNode]: ...


class DocumentGuideProvider(Protocol):
    """High-context model pass: whole law -> bounded guide for section taggers."""

    def build(self, document: ParsedDocument) -> DocumentGuide: ...


class GuidedSectionTagger(Protocol):
    """Low-context model pass: one section task -> evidence-backed tags."""

    def tag(self, task: SectionTaggingTask) -> SectionTaggingResult: ...


class TaggingReconciler(Protocol):
    """Deterministic merge of low-context tagging results into graph nodes."""

    def merge(
        self,
        document: ParsedDocument,
        guide: DocumentGuide,
        results: list[SectionTaggingResult],
    ) -> list[ConceptNode]: ...
