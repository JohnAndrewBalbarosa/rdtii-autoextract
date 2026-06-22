"""Stage 1 — deterministic structural extractor (no model).

Walks a ParsedDocument's ordered heading blocks, maintaining a heading stack so each
block knows its breadcrumb (e.g. Data Protection > Cross-Border Transfer). The breadcrumb
becomes the block's multi-label tag set. Blocks that resolve to the SAME section scope
(identical breadcrumb) are combined into a single ConceptNode — the "pure parser combines
tags into one node" requirement. Fully deterministic: output is sorted by section id, no
RNG, so the same document always yields byte-for-byte identical nodes.
"""

from __future__ import annotations

import re

from core.domain.document import ParsedDocument
from core.domain.concept_node import ConceptNode

_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    """Normalize a heading into a stable tag slug (lowercase, hyphenated)."""
    return _SLUG_NON_ALNUM.sub("-", text.strip().lower()).strip("-")


class StructuralExtractor:
    """Deterministic SectionExtractor: heading breadcrumb -> tags, combine by scope."""

    def extract(self, document: ParsedDocument) -> list[ConceptNode]:
        # First pass: resolve each block's breadcrumb via a level stack.
        stack: list[tuple[int, str]] = []
        # scope_key -> (breadcrumb_tuple, [text_parts])
        scopes: dict[str, tuple[tuple[str, ...], list[str]]] = {}
        order: list[str] = []  # preserve first-seen order before final sort

        for section in document.sections:
            while stack and stack[-1][0] >= section.level:
                stack.pop()
            stack.append((section.level, section.heading))

            breadcrumb = tuple(heading for _, heading in stack)
            scope_key = "/".join(_slug(h) for h in breadcrumb)

            if scope_key not in scopes:
                scopes[scope_key] = (breadcrumb, [])
                order.append(scope_key)
            scopes[scope_key][1].append(section.text)

        nodes = [
            ConceptNode(
                section_id=scope_key,
                document_url=document.document_url,
                text="\n\n".join(part for part in text_parts if part).strip(),
                caption=breadcrumb[-1],  # the section's own heading; no AI captioning
                tags=frozenset(_slug(h) for h in breadcrumb),
                language=document.language,
            )
            for scope_key in order
            for breadcrumb, text_parts in [scopes[scope_key]]
        ]

        # Deterministic ordering for reproducible downstream stages.
        return sorted(nodes, key=lambda n: n.section_id)
