"""Guided high-context guide + low-context tagging workflow."""

from __future__ import annotations

import pytest

from zetarix.domain.document import (
    DocumentGuide,
    GuideSectionHint,
    ParsedDocument,
    RawSection,
    SectionTaggingResult,
    SectionTaggingTask,
    TagEvidence,
)
from zetarix.extraction.guided_tagging import (
    GuidedTaggingPipeline,
    GuidedTaggingReconciler,
    SectionTaskBuilder,
)

ALLOWED_TAGS = frozenset(
    {
        "cross-border-transfer",
        "data-subject-rights",
        "data-protection-overview",
    }
)


@pytest.fixture
def guided_document() -> ParsedDocument:
    return ParsedDocument(
        document_url="https://example.gov/privacy-law",
        language="en",
        sections=(
            RawSection("Privacy Law", 1, "This law governs personal data."),
            RawSection("Cross-Border Data Flows", 2, "Transfers abroad require approval."),
            RawSection("Data Subject Rights", 2, "Individuals may request access."),
        ),
    )


@pytest.fixture
def guided_guide(guided_document: ParsedDocument) -> DocumentGuide:
    return DocumentGuide(
        document_url=guided_document.document_url,
        language=guided_document.language,
        purpose="Protect personal data while regulating transfers.",
        section_hints=(
            GuideSectionHint(
                section_id="privacy-law",
                summary="Overview of the law.",
                relevant_labels=frozenset({"data-protection-overview"}),
            ),
            GuideSectionHint(
                section_id="privacy-law/cross-border-data-flows",
                summary="Rules for transfers outside the jurisdiction.",
                relevant_labels=frozenset({"cross-border-transfer"}),
            ),
            GuideSectionHint(
                section_id="privacy-law/data-subject-rights",
                summary="Rights granted to individual data subjects.",
                relevant_labels=frozenset({"data-subject-rights"}),
            ),
        ),
    )


def test_task_builder_creates_bounded_section_packets(
    guided_document: ParsedDocument, guided_guide: DocumentGuide
) -> None:
    tasks = SectionTaskBuilder(ALLOWED_TAGS).build(guided_document, guided_guide)

    assert len(tasks) == 3
    transfer_task = next(
        task for task in tasks if task.section_id == "privacy-law/cross-border-data-flows"
    )

    assert transfer_task.text == "Transfers abroad require approval."
    assert "Individuals may request access." not in transfer_task.text
    assert "Rules for transfers outside the jurisdiction." in transfer_task.guide_excerpt
    assert transfer_task.allowed_tags == frozenset({"cross-border-transfer"})


def test_reconciler_accepts_evidence_backed_high_confidence_tags(
    guided_document: ParsedDocument, guided_guide: DocumentGuide
) -> None:
    result = SectionTaggingResult(
        section_id="privacy-law/cross-border-data-flows",
        tags=frozenset({"cross-border-transfer"}),
        evidence=(
            TagEvidence(tag="cross-border-transfer", quote="Transfers abroad require approval"),
        ),
        confidence=0.91,
    )

    reconciled = GuidedTaggingReconciler(
        min_confidence=0.7,
        allowed_tags=ALLOWED_TAGS,
    ).reconcile(guided_document, guided_guide, [result])

    assert [node.section_id for node in reconciled.nodes] == [
        "privacy-law/cross-border-data-flows"
    ]
    assert reconciled.nodes[0].tags == frozenset({"cross-border-transfer"})
    assert reconciled.review_items == ()


@pytest.mark.parametrize(
    ("result", "reason"),
    (
        (
            SectionTaggingResult(
                section_id="privacy-law/cross-border-data-flows",
                tags=frozenset({"not-in-taxonomy"}),
                evidence=(TagEvidence(tag="not-in-taxonomy", quote="Transfers abroad"),),
                confidence=0.95,
            ),
            "unknown-tags",
        ),
        (
            SectionTaggingResult(
                section_id="privacy-law/cross-border-data-flows",
                tags=frozenset({"cross-border-transfer"}),
                evidence=(TagEvidence(tag="cross-border-transfer", quote="not in source"),),
                confidence=0.95,
            ),
            "unsupported-tag",
        ),
        (
            SectionTaggingResult(
                section_id="privacy-law/cross-border-data-flows",
                tags=frozenset(),
                evidence=(),
                confidence=0.95,
                abstain_reason="Insufficient evidence.",
            ),
            "abstain",
        ),
        (
            SectionTaggingResult(
                section_id="privacy-law/cross-border-data-flows",
                tags=frozenset({"cross-border-transfer"}),
                evidence=(TagEvidence(tag="cross-border-transfer", quote="Transfers abroad"),),
                confidence=0.4,
            ),
            "low-confidence",
        ),
    ),
)
def test_reconciler_routes_invalid_outputs_to_review(
    guided_document: ParsedDocument,
    guided_guide: DocumentGuide,
    result: SectionTaggingResult,
    reason: str,
) -> None:
    reconciled = GuidedTaggingReconciler(
        min_confidence=0.7,
        allowed_tags=ALLOWED_TAGS,
    ).reconcile(guided_document, guided_guide, [result])

    assert reconciled.nodes == ()
    assert [item.reason for item in reconciled.review_items] == [reason]


def test_pipeline_orchestrates_high_and_low_context_agents(
    guided_document: ParsedDocument,
) -> None:
    class FakeGuideProvider:
        def build(self, document: ParsedDocument) -> DocumentGuide:
            return DocumentGuide(
                document_url=document.document_url,
                language=document.language,
                purpose="Guide built from the full law.",
                section_hints=(
                    GuideSectionHint(
                        section_id="privacy-law",
                        summary="Overview.",
                        relevant_labels=frozenset({"data-protection-overview"}),
                    ),
                    GuideSectionHint(
                        section_id="privacy-law/cross-border-data-flows",
                        summary="Transfers.",
                        relevant_labels=frozenset({"cross-border-transfer"}),
                    ),
                    GuideSectionHint(
                        section_id="privacy-law/data-subject-rights",
                        summary="Rights.",
                        relevant_labels=frozenset({"data-subject-rights"}),
                    ),
                ),
            )

    class FakeLowContextTagger:
        def tag(self, task: SectionTaggingTask) -> SectionTaggingResult:
            tag = next(iter(task.allowed_tags))
            quote = task.text.split(".")[0]
            return SectionTaggingResult(
                section_id=task.section_id,
                tags=frozenset({tag}),
                evidence=(TagEvidence(tag=tag, quote=quote),),
                confidence=0.9,
            )

    pipeline = GuidedTaggingPipeline(
        guide_provider=FakeGuideProvider(),
        tagger=FakeLowContextTagger(),
        task_builder=SectionTaskBuilder(ALLOWED_TAGS),
        reconciler=GuidedTaggingReconciler(min_confidence=0.7, allowed_tags=ALLOWED_TAGS),
    )

    result = pipeline.run(guided_document)

    assert {node.section_id for node in result.nodes} == {
        "privacy-law",
        "privacy-law/cross-border-data-flows",
        "privacy-law/data-subject-rights",
    }
    assert result.review_items == ()
