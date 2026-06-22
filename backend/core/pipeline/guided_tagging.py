"""Guided tagging use case for high-context guide + low-context section tagging.

This module stays deterministic and framework-agnostic:
- a guide provider builds bounded context once per document
- a task builder emits one low-context packet per raw section
- a reconciler validates model output against the source text and emits ConceptNodes
- a pipeline composes the three steps without importing any model SDKs
"""

from __future__ import annotations

import re

from core.domain.document import (
    DocumentGuide,
    ParsedDocument,
    RawSection,
    SectionTaggingResult,
    SectionTaggingTask,
    TagEvidence,
    TaggingReconciliationResult,
    TaggingReviewItem,
)
from core.domain.concept_node import ConceptNode
from core.ports.extraction import (
    DocumentGuideProvider,
    GuidedSectionTagger,
)

_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    """Normalize a heading into a stable breadcrumb slug."""
    return _SLUG_NON_ALNUM.sub("-", text.strip().lower()).strip("-")


def _section_breadcrumbs(document: ParsedDocument) -> list[str]:
    """Return deterministic section IDs for the document's raw sections."""
    stack: list[tuple[int, str]] = []
    section_ids: list[str] = []

    for section in document.sections:
        while stack and stack[-1][0] >= section.level:
            stack.pop()
        stack.append((section.level, section.heading))
        section_ids.append("/".join(_slug(heading) for _, heading in stack))

    return section_ids


def _group_sections(document: ParsedDocument) -> dict[str, list[RawSection]]:
    """Group raw sections by breadcrumb ID while preserving source order."""
    grouped: dict[str, list[RawSection]] = {}
    for section_id, section in zip(_section_breadcrumbs(document), document.sections, strict=True):
        grouped.setdefault(section_id, []).append(section)
    return grouped


def _join_section_text(sections: list[RawSection]) -> str:
    return "\n\n".join(section.text for section in sections if section.text).strip()


class SectionTaskBuilder:
    """Build one low-context tagging task per raw section."""

    def __init__(self, allowed_tags: frozenset[str]) -> None:
        self._allowed_tags = allowed_tags

    @property
    def allowed_tags(self) -> frozenset[str]:
        """The configured taxonomy labels available to low-context taggers."""
        return self._allowed_tags

    def build(self, document: ParsedDocument, guide: DocumentGuide) -> tuple[SectionTaggingTask, ...]:
        tasks: list[SectionTaggingTask] = []
        section_ids = _section_breadcrumbs(document)

        for section_id, section in zip(section_ids, document.sections, strict=True):
            allowed_tags = self._allowed_tags
            relevant_labels = guide.relevant_labels_for(section_id)
            narrowed = allowed_tags & relevant_labels if relevant_labels else frozenset()
            if narrowed:
                allowed_tags = narrowed

            tasks.append(
                SectionTaggingTask(
                    section_id=section_id,
                    document_url=document.document_url,
                    language=document.language,
                    heading=section.heading,
                    text=section.text,
                    caption=section.heading,
                    guide_excerpt=guide.excerpt_for(section_id),
                    allowed_tags=allowed_tags,
                )
            )

        return tuple(tasks)


class GuidedTaggingReconciler:
    """Validate low-context results and convert accepted ones into graph nodes."""

    def __init__(
        self,
        min_confidence: float = 0.6,
        allowed_tags: frozenset[str] | None = None,
    ) -> None:
        self._min_confidence = min_confidence
        self._allowed_tags = allowed_tags or frozenset()

    def reconcile(
        self,
        document: ParsedDocument,
        guide: DocumentGuide,
        results: list[SectionTaggingResult],
    ) -> TaggingReconciliationResult:
        sections_by_id = _group_sections(document)
        results_by_id: dict[str, list[SectionTaggingResult]] = {}
        for result in results:
            results_by_id.setdefault(result.section_id, []).append(result)

        accepted_nodes: list[ConceptNode] = []
        review_items: list[TaggingReviewItem] = []

        for section_id in sorted(sections_by_id):
            matching_results = results_by_id.pop(section_id, [])
            if not matching_results:
                continue

            section_text = _join_section_text(sections_by_id[section_id])
            guide_labels = guide.relevant_labels_for(section_id)
            allowed_tags = self._allowed_for_section(guide_labels)

            accepted_tags: set[str] = set()

            for result in matching_results:
                reason, detail = self._validate_result(
                    section_id=section_id,
                    section_text=section_text,
                    allowed_tags=allowed_tags,
                    result=result,
                )
                if reason:
                    review_items.append(
                        TaggingReviewItem(section_id=section_id, reason=reason, detail=detail)
                    )
                    break

                accepted_tags.update(result.tags)

            if any(item.section_id == section_id for item in review_items):
                continue

            if not accepted_tags:
                review_items.append(
                    TaggingReviewItem(
                        section_id=section_id,
                        reason="empty-tags",
                        detail="No tags were accepted for this section.",
                    )
                )
                continue

            accepted_nodes.append(
                ConceptNode(
                    section_id=section_id,
                    document_url=document.document_url,
                    text=section_text,
                    caption=sections_by_id[section_id][-1].heading,
                    tags=frozenset(accepted_tags),
                    language=document.language,
                )
            )

        for section_id in sorted(results_by_id):
            for result in results_by_id[section_id]:
                review_items.append(
                    TaggingReviewItem(
                        section_id=section_id,
                        reason="unknown-section",
                        detail=f"Result references {result.section_id!r}, which does not map to a document section.",
                    )
                )

        return TaggingReconciliationResult(
            nodes=tuple(sorted(accepted_nodes, key=lambda node: node.section_id)),
            review_items=tuple(sorted(review_items, key=lambda item: (item.section_id, item.reason, item.detail))),
        )

    def merge(
        self,
        document: ParsedDocument,
        guide: DocumentGuide,
        results: list[SectionTaggingResult],
    ) -> list[ConceptNode]:
        """Compatibility method used by the existing extraction port."""
        return list(self.reconcile(document, guide, results).nodes)

    def _validate_result(
        self,
        *,
        section_id: str,
        section_text: str,
        allowed_tags: frozenset[str],
        result: SectionTaggingResult,
    ) -> tuple[str, str]:
        if result.section_id != section_id:
            return ("unknown-section", f"Result references {result.section_id!r}, not {section_id!r}.")

        if result.abstain_reason:
            return ("abstain", result.abstain_reason)

        if result.confidence < self._min_confidence:
            return (
                "low-confidence",
                f"Confidence {result.confidence:.3f} is below threshold {self._min_confidence:.3f}.",
            )

        if allowed_tags and not result.tags.issubset(allowed_tags):
            unknown = ", ".join(sorted(result.tags - allowed_tags))
            return ("unknown-tags", f"Tags outside the allowed taxonomy: {unknown}.")

        if not result.tags:
            return ("empty-tags", "Result did not produce any tags.")

        for tag in sorted(result.tags):
            if not self._tag_has_support(tag, section_text, result.evidence):
                return (
                    "unsupported-tag",
                    f"Tag {tag!r} has no evidence quote present in the source section text.",
                )

        return ("", "")

    def _allowed_for_section(self, guide_labels: frozenset[str]) -> frozenset[str]:
        if not self._allowed_tags:
            return guide_labels
        narrowed = self._allowed_tags & guide_labels if guide_labels else frozenset()
        return narrowed or self._allowed_tags

    @staticmethod
    def _tag_has_support(tag: str, section_text: str, evidence: tuple[TagEvidence, ...]) -> bool:
        for item in evidence:
            if item.tag != tag:
                continue
            quote = item.quote.strip()
            if quote and quote in section_text:
                return True
        return False


class GuidedTaggingPipeline:
    """Compose guide creation, section tagging, and deterministic reconciliation."""

    def __init__(
        self,
        guide_provider: DocumentGuideProvider,
        tagger: GuidedSectionTagger,
        task_builder: SectionTaskBuilder,
        reconciler: "GuidedTaggingReconciler",
    ) -> None:
        self._guide_provider = guide_provider
        self._tagger = tagger
        self._task_builder = task_builder
        self._reconciler = reconciler

    def run(self, document: ParsedDocument) -> TaggingReconciliationResult:
        guide = self._guide_provider.build(document)
        tasks = self._task_builder.build(document, guide)
        results = [self._tagger.tag(task) for task in tasks]
        return self._reconciler.reconcile(document, guide, results)
