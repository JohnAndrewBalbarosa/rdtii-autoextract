"""LLMProvisionExtractor — live extraction via Law Interpreter + Tag Generator.

Chains the Phase 2 few-shot/RAG-grounded stages behind the ``ProvisionExtractor`` port.
HTML Structure Tagger stays rule-based upstream; this adapter handles legal reasoning only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from zetarix.domain.document import CrawledDocument
from zetarix.domain.entities import DiscoveryTag, Finding, Pillar
from zetarix.domain.indicator_codes import to_canonical
from zetarix.extraction.document_metadata import extract_document_metadata
from zetarix.extraction.law_interpreter import LawInterpreter
from zetarix.extraction.tag_generator import TagGenerator
from zetarix.ports import LLMProvider
from zetarix.inference.grounding import create_law_interpreter, create_tag_generator

_SECTION_HEADING_RE = re.compile(
    r"^(?P<heading>(?:Section|Article|Art\.?|s\.)\s*\d+[A-Za-z]?.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_MIN_SECTION_CHARS = 40
_DEFAULT_CONFIDENCE = 0.7
_MAX_RATIONALE_CHARS = 300


@dataclass(frozen=True)
class _ProvisionSection:
    heading: str
    text: str


class LLMProvisionExtractor:
    """``ProvisionExtractor`` backed by grounded Law Interpreter + Tag Generator."""

    def __init__(
        self,
        llm: LLMProvider,
        *,
        interpreter: LawInterpreter | None = None,
        tagger: TagGenerator | None = None,
    ) -> None:
        self._interpreter = interpreter or create_law_interpreter(llm)
        self._tagger = tagger or create_tag_generator(llm)

    def extract(self, doc: CrawledDocument, pillar: int) -> list[Finding]:
        sections = self._split_sections(doc.text or "")
        if not sections:
            return []

        meta = extract_document_metadata(doc.text or "", url=doc.url or "")
        title = meta.act_title
        last_update = meta.last_update
        pillar_enum = Pillar(pillar)
        findings: list[Finding] = []

        for section in sections:
            tagged_input = self._tagged_input(title, section, doc)
            interpretation = self._interpreter.interpret(
                tagged_provision_input=tagged_input,
                jurisdiction=doc.economy,
                pillar=pillar,
            )
            legal_text = self._legal_interpretation_text(interpretation, section.text)
            mapping = self._tagger.generate(
                legal_interpretation=legal_text,
                jurisdiction=doc.economy,
                pillar=pillar,
                precedent_tags=interpretation.applicability_triggers,
            )
            for indicator_db in mapping.indicator_tags:
                findings.append(
                    self._to_finding(
                        doc=doc,
                        title=title,
                        last_update=last_update,
                        pillar=pillar_enum,
                        section=section,
                        interpretation=interpretation,
                        indicator_db=indicator_db,
                        rationale=mapping.rationale,
                    )
                )
        return findings

    def _split_sections(self, text: str) -> list[_ProvisionSection]:
        if not text.strip():
            return []

        matches = list(_SECTION_HEADING_RE.finditer(text))
        if not matches:
            chunk = text.strip()
            if len(chunk) >= _MIN_SECTION_CHARS:
                return [_ProvisionSection(heading="Untitled", text=chunk[:2000])]
            return []

        sections: list[_ProvisionSection] = []
        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if len(body) < _MIN_SECTION_CHARS:
                continue
            heading = re.sub(r"\s+", " ", match.group("heading")).strip()
            sections.append(_ProvisionSection(heading=heading, text=body[:2000]))
        return sections

    def _tagged_input(self, title: str, section: _ProvisionSection, doc: CrawledDocument) -> str:
        parts = [f"Document: {title}", f"Article: {section.heading}", f"Provision: {section.text}"]
        if doc.url:
            parts.append(f"Source: {doc.url}")
        return "\n".join(parts)

    @staticmethod
    def _legal_interpretation_text(interpretation, provision_text: str) -> str:
        triggers = ", ".join(interpretation.applicability_triggers) or "(none)"
        return (
            f"Scope: {interpretation.scope}\n"
            f"Obligation type: {interpretation.obligation_type}\n"
            f"Triggers: {triggers}\n"
            f"Summary: {interpretation.plain_summary}\n"
            f"Provision excerpt: {provision_text[:500]}"
        )

    def _to_finding(
        self,
        *,
        doc: CrawledDocument,
        title: str,
        last_update: date | None,
        pillar: Pillar,
        section: _ProvisionSection,
        interpretation,
        indicator_db: str,
        rationale: str,
    ) -> Finding:
        # Cited clause = full section body under the matched heading (not keyword proximity).
        snippet = section.text[:300].strip()
        mapping_rationale = (rationale or interpretation.plain_summary)[:_MAX_RATIONALE_CHARS]
        return Finding(
            title=title,
            last_update=last_update,
            url=doc.url,
            scope=interpretation.scope,
            provisions=section.text[:2000].strip(),
            impact=interpretation.plain_summary,
            pillar=pillar,
            indicator=to_canonical(indicator_db),
            confidence=_DEFAULT_CONFIDENCE,
            economy=doc.economy,
            article_section=section.heading,
            discovery_tag=DiscoveryTag.KNOWN,
            verbatim_snippet=snippet,
            mapping_rationale=mapping_rationale,
            location_ref=doc.url or None,
            notes="LLM extraction (Law Interpreter + Tag Generator).",
        )

    def _derive_title(self, doc: CrawledDocument) -> str:
        """Deprecated — use ``document_metadata.extract_act_title``."""
        return extract_document_metadata(doc.text or "", url=doc.url or "").act_title
