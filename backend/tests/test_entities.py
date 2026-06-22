"""Unit tests for domain entities — Finding submission fields + DiscoveryTag.

Focus: the new Round-1 fields are backward-compatible defaults, immutability holds,
and ``with_review`` preserves them.
"""

from __future__ import annotations

from datetime import date

import pytest

from core.domain.entities import DiscoveryTag, Finding, Pillar, ReviewStatus


def _base_finding(**overrides) -> Finding:
    kwargs = dict(
        title="Privacy Act 1988",
        last_update=date(2024, 1, 1),
        url="https://legislation.gov.au/C2004",
        scope="scope",
        provisions="provisions",
        impact="impact",
        pillar=Pillar.CROSS_BORDER_DATA_FLOWS,
        indicator="P6-I1",
        confidence=0.9,
    )
    kwargs.update(overrides)
    return Finding(**kwargs)


def test_discovery_tag_values():
    assert DiscoveryTag.NEW.value == "NEW"
    assert DiscoveryTag.KNOWN.value == "KNOWN"


def test_new_fields_default_backward_compatible():
    # Constructing with only the legacy positional/keyword fields must still work.
    finding = _base_finding()
    assert finding.economy == ""
    assert finding.law_number is None
    assert finding.article_section == ""
    assert finding.discovery_tag is DiscoveryTag.KNOWN
    assert finding.verbatim_snippet == ""
    assert finding.mapping_rationale == ""
    assert finding.location_ref is None
    assert finding.notes == ""
    assert finding.review_status is ReviewStatus.PENDING


def test_indicator_carries_canonical_form():
    assert _base_finding(indicator="P6-I1").indicator == "P6-I1"


def test_finding_is_immutable():
    finding = _base_finding()
    with pytest.raises(Exception):  # FrozenInstanceError (dataclasses)
        finding.economy = "Australia"  # type: ignore[misc]


def test_with_review_preserves_new_fields_and_does_not_mutate():
    finding = _base_finding(
        economy="Australia",
        discovery_tag=DiscoveryTag.NEW,
        verbatim_snippet="Section 26(2): ...",
        article_section="Section 26(2)",
    )
    reviewed = finding.with_review(ReviewStatus.VERIFIED)
    # New object, original untouched (immutability).
    assert reviewed is not finding
    assert finding.review_status is ReviewStatus.PENDING
    assert reviewed.review_status is ReviewStatus.VERIFIED
    # Submission fields carried over.
    assert reviewed.economy == "Australia"
    assert reviewed.discovery_tag is DiscoveryTag.NEW
    assert reviewed.verbatim_snippet == "Section 26(2): ..."
    assert reviewed.article_section == "Section 26(2)"
