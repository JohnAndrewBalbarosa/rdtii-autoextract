"""Deterministic section-aware extractor for the MVP live path.

This replaces the purely mock reference adapter as the default live extractor while
preserving the same ``ProvisionExtractor`` contract and deterministic behavior.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from zetarix.domain.document import CrawledDocument
from zetarix.domain.entities import DiscoveryTag, Finding
from zetarix.domain.indicator_codes import to_canonical
from zetarix.extraction.document_metadata import extract_document_metadata
from zetarix.extraction.mock_provision_extractor import (
    MockProvisionExtractor,
    _MAX_SNIPPET_CHARS,
    _PILLAR_KEYWORDS,
    _SECTION_RE,
)
from zetarix.extraction.reviewer_brief_generator import ReviewerBriefGenerator, ReviewerBriefInput
from zetarix.ports import LLMProvider

_SECTION_HEADER_RE = re.compile(
    r"(?im)^\s*((?:Section|Article|Art\.?|s\.)\s*\d+[A-Za-z]?)\b[.:]?\s*(.*)$"
)
_BARE_SECTION_HEADER_RE = re.compile(
    r"(?im)^\s*(?P<number>\d+[A-Za-z]{0,2})\s+(?P<title>[A-Z][^\n]{2,180})$"
)
_INLINE_SECTION_HEADER_RE = re.compile(
    r"(?<![A-Za-z])(?P<number>\d+[A-Za-z]{0,2})\s+(?P<title>[A-Z][A-Za-z]{2,})"
)
_CLAUSE_BOUNDARY_RE = re.compile(r"[.;\n]")
_P6_CONTEXT_RE = re.compile(
    r"\b(personal data|personal information|privacy|australian privacy principle|overseas recipient|cross-border)\b",
    re.IGNORECASE,
)
_TRANSFER_CONTEXT_WINDOW = 160
_OPERATIVE_RULE_RE = re.compile(
    r"\b("
    r"shall|must|may not|must not|shall not|required|prohibited|unless|except|"
    r"remains accountable|is liable|is taken to|is deemed to|must comply|"
    r"may disclose|must not disclose|must obtain|is not an interference|"
    r"does not apply|applies to|is subject to|only if|condition"
    r")\b",
    re.IGNORECASE,
)
_DEFINITION_HEADING_RE = re.compile(
    r"\b(interpretation|definitions?)\b",
    re.IGNORECASE,
)
_DEFINITION_BODY_RE = re.compile(
    r"\b(means|includes|refers to|has the meaning given by|for the purposes of this act)\b",
    re.IGNORECASE,
)
_ADMIN_NOISE_RE = re.compile(
    r"\b(contents|schedule|endnote|chapter|part\s+\d+|division\s+\d+|commission|contact|privacy statement|terms and conditions)\b",
    re.IGNORECASE,
)
_P6_SUBSTANTIVE_RE = re.compile(
    r"\b("
    r"transfer|transferred|disclose|disclosed|disclosure|send|sent|outside\s+[A-Z][a-z]+|"
    r"outside Australia|outside Singapore|foreign law|foreign country|foreign countries|"
    r"overseas|overseas recipient|cross-border|recipient|adequacy|comparable protection|"
    r"accountable|accountability|safeguards?|protection\s+comparable|jurisdiction"
    r")\b",
    re.IGNORECASE,
)
_P7_SUBSTANTIVE_RE = re.compile(
    r"\b("
    r"consent|collect|collection|use|disclose|disclosure|retain|retention|"
    r"security|protect|safeguard|breach|notify|processing|process|access|correction|"
    r"purpose limitation|reasonable steps|withdraw"
    r")\b",
    re.IGNORECASE,
)
_HEADING_ONLY_RATIO = 0.28
_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class _SectionBlock:
    article_section: str
    text: str


@dataclass(frozen=True)
class _RelevanceDecision:
    accepted: bool
    score: int
    reason: str


class RuleBasedProvisionExtractor:
    """Deterministic provision extractor using section boundaries and keyword rules."""

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self._fallback = MockProvisionExtractor()
        self._briefs = ReviewerBriefGenerator(llm_provider)

    def extract(self, doc: CrawledDocument, pillar: int) -> list[Finding]:
        sections = self._split_sections(doc.text or "")
        if not sections:
            _LOG.info("Rejected live document without section structure url=%s", doc.url)
            return []

        metadata = extract_document_metadata(doc.text or "", url=doc.url or "")
        title = metadata.act_title or self._fallback._derive_title(doc)
        ranked_findings: list[tuple[int, Finding]] = []
        seen: set[tuple[str, str]] = set()

        for block in sections:
            for keyword, indicator_db in _PILLAR_KEYWORDS.get(pillar, ()):
                hit = self._keyword_hit(block.text, keyword, pillar)
                if hit is None:
                    continue
                indicator = to_canonical(indicator_db)
                key = (block.article_section, indicator)
                if key in seen:
                    continue
                decision = self._assess_relevance(block, pillar, keyword, hit.start(), hit.end())
                if not decision.accepted:
                    _LOG.info(
                        "Rejected live section title=%r article=%r indicator=%s reason=%s",
                        title,
                        block.article_section,
                        indicator,
                        decision.reason,
                    )
                    continue
                snippet = self._snippet(block.text, hit.start(), hit.end())
                finding = self._briefs.generate(
                    ReviewerBriefInput(
                        title=title,
                        jurisdiction=doc.economy,
                        pillar=pillar,
                        indicator=indicator,
                        article_number=block.article_section,
                        provision_text=block.text,
                        source_url=doc.url,
                        nearby_context=block.text,
                        last_update=metadata.last_update,
                        discovery_tag=DiscoveryTag.KNOWN,
                        supporting_snippet=snippet,
                    )
                )
                if finding is None:
                    _LOG.warning(
                        "Skipping invalid live finding title=%r article=%r indicator=%s url=%s",
                        title,
                        block.article_section,
                        indicator,
                        doc.url,
                    )
                    continue
                seen.add(key)
                ranked_findings.append((decision.score, finding))

        ranked_findings.sort(key=lambda item: (-item[0], -item[1].confidence, item[1].article_section.lower()))
        return [finding for _score, finding in ranked_findings]

    def _keyword_hit(self, text: str, keyword: str, pillar: int):
        hit = re.search(r"\b" + re.escape(keyword) + r"\b", text, re.IGNORECASE)
        if hit is None:
            return None
        if pillar == 6 and keyword in {"transfer", "overseas", "adequacy"}:
            window_start = max(0, hit.start() - _TRANSFER_CONTEXT_WINDOW)
            window_end = min(len(text), hit.end() + _TRANSFER_CONTEXT_WINDOW)
            local_text = text[window_start:window_end]
            if _P6_CONTEXT_RE.search(local_text) is None:
                return None
        return hit

    def _assess_relevance(
        self,
        block: _SectionBlock,
        pillar: int,
        keyword: str,
        hit_start: int,
        hit_end: int,
    ) -> _RelevanceDecision:
        text = re.sub(r"\s+", " ", block.text.strip())
        lowered = text.lower()
        article = block.article_section.lower()

        if len(text) < 80:
            return _RelevanceDecision(False, 0, "section_too_short")
        if _ADMIN_NOISE_RE.search(article) or _ADMIN_NOISE_RE.search(text[:120]):
            return _RelevanceDecision(False, 0, "administrative_or_boilerplate")

        heading_share = len(article) / max(len(text), 1)
        if heading_share >= _HEADING_ONLY_RATIO:
            return _RelevanceDecision(False, 0, "heading_without_substance")

        local_text = text[max(0, hit_start - 220) : min(len(text), hit_end + 220)]
        if self._definition_only(article, text, local_text):
            return _RelevanceDecision(False, 0, "definition_only")

        if not _OPERATIVE_RULE_RE.search(local_text):
            return _RelevanceDecision(False, 0, "no_operative_rule")

        substantive_pattern = _P6_SUBSTANTIVE_RE if pillar == 6 else _P7_SUBSTANTIVE_RE
        substantive_hits = len(substantive_pattern.findall(local_text))
        if substantive_hits == 0:
            return _RelevanceDecision(False, 0, "no_pillar_specific_substance")

        keyword_hits = len(re.findall(r"\b" + re.escape(keyword) + r"\b", local_text, re.IGNORECASE))
        score = 0
        score += 4 if re.search(r"\b(shall not|must not|prohibited|unless|except)\b", local_text, re.I) else 0
        score += 3 if re.search(r"\b(shall|must|required|is liable|is taken to|is deemed to)\b", local_text, re.I) else 0
        score += 2 if re.search(r"\b(remains accountable|foreign law|overseas recipient|outside Australia|outside Singapore)\b", local_text, re.I) else 0
        score += min(substantive_hits, 3)
        score += min(keyword_hits, 2)

        if pillar == 6 and not self._pillar_6_specific(local_text):
            return _RelevanceDecision(False, 0, "weak_cross_border_context")
        if pillar == 7 and not self._pillar_7_specific(local_text):
            return _RelevanceDecision(False, 0, "weak_domestic_dp_context")

        if score < 6:
            return _RelevanceDecision(False, score, "below_relevance_threshold")
        return _RelevanceDecision(True, score, "accepted")

    def _definition_only(self, article: str, text: str, local_text: str) -> bool:
        if _DEFINITION_HEADING_RE.search(article) or _DEFINITION_HEADING_RE.search(text[:100]):
            return True
        if _DEFINITION_BODY_RE.search(local_text):
            if _OPERATIVE_RULE_RE.search(local_text) is None:
                return True
            if re.search(r"\b(has the meaning given by|means)\b", local_text, re.I):
                return True
        return False

    def _pillar_6_specific(self, local_text: str) -> bool:
        return bool(
            re.search(
                r"\b("
                r"overseas recipient|foreign law|cross-border|outside Australia|outside Singapore|"
                r"country or territory outside|transfer personal data|discloses personal information to an overseas recipient|"
                r"comparable protection|adequacy|recipient"
                r")\b",
                local_text,
                re.I,
            )
        )

    def _pillar_7_specific(self, local_text: str) -> bool:
        return bool(
            re.search(
                r"\b("
                r"consent|collection|use|disclosure|retain|retention|security|protect|breach|notify|"
                r"access|correction|withdraw|purpose"
                r")\b",
                local_text,
                re.I,
            )
        )

    def _split_sections(self, text: str) -> list[_SectionBlock]:
        matches = list(_SECTION_HEADER_RE.finditer(text))
        if not matches:
            bare_matches = list(_BARE_SECTION_HEADER_RE.finditer(text))
            if bare_matches:
                blocks: list[_SectionBlock] = []
                for i, match in enumerate(bare_matches):
                    start = match.start()
                    end = bare_matches[i + 1].start() if i + 1 < len(bare_matches) else len(text)
                    section_text = text[start:end].strip()
                    blocks.append(
                        _SectionBlock(
                            article_section=f"section {match.group('number')}",
                            text=section_text,
                        )
                    )
                return blocks
            inline_matches = [
                match
                for match in _INLINE_SECTION_HEADER_RE.finditer(text)
                if match.group("title").lower() not in {"contents", "endnote", "schedule", "chapter"}
            ]
            if inline_matches:
                blocks: list[_SectionBlock] = []
                for i, match in enumerate(inline_matches):
                    start = match.start()
                    end = inline_matches[i + 1].start() if i + 1 < len(inline_matches) else len(text)
                    section_text = text[start:end].strip()
                    blocks.append(
                        _SectionBlock(
                            article_section=f"section {match.group('number')}",
                            text=section_text,
                        )
                    )
                return blocks
            nearby = list(_SECTION_RE.finditer(text))
            if not nearby:
                return []
            blocks: list[_SectionBlock] = []
            for i, match in enumerate(nearby):
                start = match.start()
                end = nearby[i + 1].start() if i + 1 < len(nearby) else len(text)
                section_text = text[start:end].strip()
                blocks.append(_SectionBlock(article_section=match.group(0), text=section_text))
            return blocks

        blocks = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section_text = text[start:end].strip()
            blocks.append(_SectionBlock(article_section=match.group(1).strip(), text=section_text))
        return blocks

    def _snippet(self, text: str, start: int, end: int) -> str:
        left = 0
        for boundary in _CLAUSE_BOUNDARY_RE.finditer(text, 0, start):
            left = boundary.end()
        right_match = _CLAUSE_BOUNDARY_RE.search(text, end)
        right = right_match.start() if right_match else len(text)
        snippet = text[left:right].strip()
        return snippet[:_MAX_SNIPPET_CHARS].strip()
