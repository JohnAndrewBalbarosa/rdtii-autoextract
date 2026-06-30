"""Stage 1 — deterministic structural extraction."""

from __future__ import annotations

from zetarix.extraction.structural_extractor import StructuralExtractor
from zetarix.domain.document import ParsedDocument, RawSection


def test_each_scope_becomes_one_node(parsed_document: ParsedDocument) -> None:
    nodes = StructuralExtractor().extract(parsed_document)
    assert len(nodes) == 7  # one node per distinct heading breadcrumb


def test_tags_are_the_heading_breadcrumb(parsed_document: ParsedDocument) -> None:
    nodes = {n.section_id: n for n in StructuralExtractor().extract(parsed_document)}
    adequacy = nodes["data-protection-act/cross-border-data-flows/adequacy-decisions"]
    assert adequacy.tags == frozenset(
        {"data-protection-act", "cross-border-data-flows", "adequacy-decisions"}
    )
    assert adequacy.caption == "Adequacy Decisions"  # leaf heading, no AI captioning


def test_blocks_in_same_scope_are_combined() -> None:
    # Two blocks resolving to the same breadcrumb must merge into one node.
    doc = ParsedDocument(
        document_url="u",
        language="en",
        sections=(
            RawSection("Title", 1, "first part"),
            RawSection("Title", 1, "second part"),
        ),
    )
    nodes = StructuralExtractor().extract(doc)
    assert len(nodes) == 1
    assert "first part" in nodes[0].text and "second part" in nodes[0].text


def test_extraction_is_deterministic(parsed_document: ParsedDocument) -> None:
    first = StructuralExtractor().extract(parsed_document)
    second = StructuralExtractor().extract(parsed_document)
    assert first == second
