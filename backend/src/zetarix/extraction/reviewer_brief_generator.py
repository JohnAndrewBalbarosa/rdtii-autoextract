"""Generate reviewer-ready findings from real legal provision text.

This module sits behind the existing ProvisionExtractor seam. It accepts only
validated live provision inputs, optionally asks an LLM for the reviewer brief,
and falls back to deterministic legal-style phrasing when no LLM is available
or the model returns a null/template response.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date

from zetarix.domain.entities import DiscoveryTag, Finding, Pillar
from zetarix.ports import LLMProvider

_LOG = logging.getLogger(__name__)

_PLACEHOLDER_FRAGMENTS = (
    "[exact section text here]",
    "[1–2 lines before and after]",
    "[1-2 lines before and after]",
    "provide the provision inputs",
)
_PLACEHOLDER_VALUES = {
    "https://...",
    "null",
    "none",
    "",
}
_OBLIGATION_RE = re.compile(r"\b(shall|must|may not|must not|shall not|required|unless|except)\b", re.I)
_DEFINITION_ONLY_RE = re.compile(r"\b(means|refers to|includes|definition)\b", re.I)
_URL_RE = re.compile(r"^https?://", re.I)
_WHITESPACE_RE = re.compile(r"\s+")

_BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "scope": {"type": "string"},
        "provisions": {"type": "string"},
        "impact": {"type": "string"},
        "verbatim_snippet": {"type": "string"},
        "mapping_rationale": {"type": "string"},
        "confidence": {"type": "number"},
        "review_notes": {"type": "string"},
    },
    "required": [
        "scope",
        "provisions",
        "impact",
        "verbatim_snippet",
        "mapping_rationale",
        "confidence",
        "review_notes",
    ],
}

_SCOPE_BY_INDICATOR = {
    "P6-I1": "Cross-border transfer of personal data",
    "P6-I2": "Data localisation or domestic-storage requirement",
    "P6-I3": "Transfer assessment or adequacy condition",
    "P7-I1": "Security obligations for personal data",
    "P7-I2": "Controller accountability obligations",
    "P7-I3": "Rights of the data subject or individual",
    "P7-I4": "Personal-data processing obligations",
    "P7-I5": "Conditions for lawful processing",
}


@dataclass(frozen=True)
class ReviewerBriefInput:
    title: str
    jurisdiction: str
    pillar: int
    indicator: str
    article_number: str
    provision_text: str
    source_url: str
    nearby_context: str
    last_update: date | None = None
    discovery_tag: DiscoveryTag | None = None
    supporting_snippet: str = ""


class ReviewerBriefGenerator:
    """Generate reviewer-ready Finding objects from real legal provisions only."""

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self._llm = llm_provider

    def generate(self, data: ReviewerBriefInput) -> Finding | None:
        if not self._is_valid_input(data):
            _LOG.warning(
                "Skipping reviewer brief for invalid provision input title=%r article=%r url=%r",
                data.title,
                data.article_number,
                data.source_url,
            )
            return None

        brief = self._deterministic_brief(data)
        if self._llm is not None:
            llm_brief = self._generate_with_llm(data)
            if llm_brief is not None:
                brief = llm_brief

        return Finding(
            title=data.title,
            last_update=data.last_update,
            url=data.source_url,
            scope=brief["scope"],
            provisions=brief["provisions"],
            impact=brief["impact"],
            pillar=Pillar(data.pillar),
            indicator=data.indicator,
            confidence=float(brief["confidence"]),
            economy=data.jurisdiction,
            law_number=None,
            article_section=data.article_number,
            discovery_tag=data.discovery_tag or DiscoveryTag.KNOWN,
            verbatim_snippet=brief["verbatim_snippet"],
            mapping_rationale=brief["mapping_rationale"],
            location_ref=data.source_url,
            notes=brief["review_notes"],
        )

    def _is_valid_input(self, data: ReviewerBriefInput) -> bool:
        required_values = (
            data.title,
            data.jurisdiction,
            data.indicator,
            data.article_number,
            data.provision_text,
            data.source_url,
            data.nearby_context,
        )
        if any(self._is_placeholder(value) for value in required_values):
            return False
        if not _URL_RE.match(data.source_url.strip()):
            return False
        cleaned = self._clean_text(data.provision_text)
        if len(cleaned) < 40:
            return False
        return True

    def _is_placeholder(self, value: object) -> bool:
        text = self._clean_text("" if value is None else str(value))
        lowered = text.lower()
        if lowered in _PLACEHOLDER_VALUES:
            return True
        return any(fragment in lowered for fragment in _PLACEHOLDER_FRAGMENTS)

    def _generate_with_llm(self, data: ReviewerBriefInput) -> dict[str, object] | None:
        prompt = self._prompt(data)
        try:
            response = self._llm.complete(prompt, _BRIEF_SCHEMA, agent_profile="main_controller")
        except Exception as exc:
            _LOG.info("LLM reviewer brief unavailable for %s %s (%s)", data.title, data.article_number, exc)
            return None
        if not isinstance(response, dict):
            return None
        return self._normalize_llm_response(response)

    def _normalize_llm_response(self, payload: dict[str, object]) -> dict[str, object] | None:
        normalized: dict[str, object] = {}
        for key in (
            "scope",
            "provisions",
            "impact",
            "verbatim_snippet",
            "mapping_rationale",
            "review_notes",
        ):
            raw = payload.get(key)
            text = self._clean_text("" if raw is None else str(raw))
            if self._is_placeholder(text):
                return None
            normalized[key] = text

        try:
            confidence = float(payload.get("confidence"))
        except (TypeError, ValueError):
            return None
        if not 0.0 <= confidence <= 1.0:
            return None
        normalized["confidence"] = confidence
        return normalized

    def _prompt(self, data: ReviewerBriefInput) -> str:
        return (
            "You are generating an ESCAP reviewer brief from a live legal provision.\n"
            "Use concise legal reasoning. Do not mention keyword matching or extraction.\n"
            "Return JSON only.\n\n"
            f"Title: {data.title}\n"
            f"Jurisdiction: {data.jurisdiction}\n"
            f"Pillar: {data.pillar}\n"
            f"Indicator: {data.indicator}\n"
            f"Article/Section: {data.article_number}\n"
            f"Source URL: {data.source_url}\n"
            f"Last update: {data.last_update.isoformat() if data.last_update else 'null'}\n"
            f"Discovery tag: {data.discovery_tag.value if data.discovery_tag else 'null'}\n"
            f"Provision text:\n{data.provision_text}\n\n"
            f"Nearby context:\n{data.nearby_context}\n\n"
            f"Supporting snippet:\n{data.supporting_snippet}\n"
        )

    def _deterministic_brief(self, data: ReviewerBriefInput) -> dict[str, object]:
        scope = _SCOPE_BY_INDICATOR.get(data.indicator, "Relevant legal obligation")
        verbatim = self._best_snippet(data)
        provision = self._summarize_provision(data.provision_text, data.article_number)
        strength = self._strength(data.provision_text)
        impact = self._impact_text(data.indicator, scope, data.provision_text, strength)
        rationale = self._mapping_rationale(data.indicator, scope, data.provision_text, strength)
        confidence = self._confidence(data.provision_text, strength)
        review_notes = self._review_note(data.article_number, scope, strength)
        return {
            "scope": scope,
            "provisions": provision,
            "impact": impact,
            "verbatim_snippet": verbatim,
            "mapping_rationale": rationale,
            "confidence": confidence,
            "review_notes": review_notes,
        }

    def _best_snippet(self, data: ReviewerBriefInput) -> str:
        snippet = self._clean_text(data.supporting_snippet or data.provision_text)
        if len(snippet.split()) <= 30:
            return snippet
        words = snippet.split()
        return " ".join(words[:30]).strip()

    def _summarize_provision(self, text: str, article_number: str) -> str:
        cleaned = self._clean_text(text)
        lowered_article = article_number.lower()
        if cleaned.lower().startswith(lowered_article.lower()):
            cleaned = cleaned[len(article_number) :].lstrip(" .:-")
        sentences = re.split(r"(?<=[.;])\s+", cleaned)
        provision = sentences[0].strip() if sentences else cleaned
        if len(provision) > 360:
            provision = provision[:357].rstrip() + "..."
        return provision

    def _strength(self, text: str) -> str:
        cleaned = self._clean_text(text)
        lowered = cleaned.lower()
        if _DEFINITION_ONLY_RE.search(lowered) and _OBLIGATION_RE.search(lowered) is None:
            return "weak"
        if _OBLIGATION_RE.search(lowered):
            return "strong"
        return "moderate"

    def _impact_text(self, indicator: str, scope: str, text: str, strength: str) -> str:
        lowered = text.lower()
        if "shall not" in lowered or "must not" in lowered:
            verb = "restricts"
        elif "unless" in lowered or "except" in lowered:
            verb = "conditions"
        elif "may" in lowered:
            verb = "allows"
        else:
            verb = "addresses"
        if strength == "weak":
            return f"This provision is weak evidence for {scope.lower()}; it provides context but not a clear operative rule."
        return f"This provision {verb} the relevant behavior for {scope.lower()}, which is directly relevant to {indicator}."

    def _mapping_rationale(self, indicator: str, scope: str, text: str, strength: str) -> str:
        if strength == "weak":
            return f"The section mentions {scope.lower()}, but it reads more like contextual or definitional text than a clear operative rule for {indicator}."
        return f"The section sets an article-level rule on {scope.lower()}, so it is direct evidence for {indicator}."

    def _confidence(self, text: str, strength: str) -> float:
        if strength == "weak":
            return 0.42
        if len(self._clean_text(text)) >= 180:
            return 0.86
        if strength == "strong":
            return 0.78
        return 0.64

    def _review_note(self, article_number: str, scope: str, strength: str) -> str:
        if strength == "weak":
            return f"Review whether {article_number} is only contextual text rather than an operative {scope.lower()} rule."
        return f"Verify that {article_number} states an operative rule on {scope.lower()}."

    @staticmethod
    def _clean_text(text: str) -> str:
        return _WHITESPACE_RE.sub(" ", text.strip())
