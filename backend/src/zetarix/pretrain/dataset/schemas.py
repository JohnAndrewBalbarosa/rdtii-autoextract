"""Training-record schemas for Law Interpreter and Tag Generator fine-tunes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


LabelKind = Literal["positive", "negative"]


@dataclass(frozen=True)
class LawInterpreterExample:
    """One Law Interpreter training row.

    Input: tagged provision text + jurisdiction + pillar.
    Output: obligation classification and plain-language summary.
    """

    tagged_provision_input: str
    jurisdiction: str
    pillar: int
    obligation_type: str
    scope: str
    applicability_triggers: tuple[str, ...]
    plain_summary: str
    label: LabelKind = "positive"
    source_id: str = ""
    source: str = "gold"  # gold | review

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["applicability_triggers"] = list(self.applicability_triggers)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LawInterpreterExample":
        triggers = data.get("applicability_triggers") or []
        return cls(
            tagged_provision_input=str(data["tagged_provision_input"]),
            jurisdiction=str(data["jurisdiction"]),
            pillar=int(data["pillar"]),
            obligation_type=str(data["obligation_type"]),
            scope=str(data["scope"]),
            applicability_triggers=tuple(str(t) for t in triggers),
            plain_summary=str(data["plain_summary"]),
            label=data.get("label", "positive"),
            source_id=str(data.get("source_id", "")),
            source=str(data.get("source", "gold")),
        )


@dataclass(frozen=True)
class TagGeneratorExample:
    """One Tag Generator training row.

    Input: legal interpretation + jurisdiction + pillar + precedent tags.
    Output: RDTII indicator tags and mapping rationale.
    """

    legal_interpretation: str
    jurisdiction: str
    pillar: int
    precedent_tags: tuple[str, ...]
    indicator_tags: tuple[str, ...]
    rationale: str
    label: LabelKind = "positive"
    source_id: str = ""
    source: str = "gold"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["precedent_tags"] = list(self.precedent_tags)
        payload["indicator_tags"] = list(self.indicator_tags)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TagGeneratorExample":
        return cls(
            legal_interpretation=str(data["legal_interpretation"]),
            jurisdiction=str(data["jurisdiction"]),
            pillar=int(data["pillar"]),
            precedent_tags=tuple(str(t) for t in (data.get("precedent_tags") or [])),
            indicator_tags=tuple(str(t) for t in (data.get("indicator_tags") or [])),
            rationale=str(data["rationale"]),
            label=data.get("label", "positive"),
            source_id=str(data.get("source_id", "")),
            source=str(data.get("source", "gold")),
        )


@dataclass
class ReviewDecision:
    """A verify/reject action from the review UI, stored as append-only JSONL."""

    finding_id: str
    review_status: Literal["verified", "rejected"]
    jurisdiction: str
    pillar: int
    title: str
    scope: str
    provisions: str
    impact: str
    indicator: str
    indicator_label: str = ""
    document_title: str = ""
    article_number: str = ""
    language: str = "en"
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewDecision":
        return cls(
            finding_id=str(data["finding_id"]),
            review_status=data["review_status"],
            jurisdiction=str(data["jurisdiction"]),
            pillar=int(data["pillar"]),
            title=str(data.get("title", "")),
            scope=str(data.get("scope", "")),
            provisions=str(data.get("provisions", "")),
            impact=str(data.get("impact", "")),
            indicator=str(data.get("indicator", "")),
            indicator_label=str(data.get("indicator_label", "")),
            document_title=str(data.get("document_title", "")),
            article_number=str(data.get("article_number", "")),
            language=str(data.get("language", "en")),
            timestamp=str(data.get("timestamp", "")),
        )
