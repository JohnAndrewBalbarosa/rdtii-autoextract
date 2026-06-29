"""Tests for the legislation.gov.au scaffold and its registration."""

from __future__ import annotations

from adapters.botting.scaffolds.legislation_gov_au import LegislationGovAuScaffold
from adapters.botting.scaffolds.scaffold_registry import ScaffoldRegistry


def test_registry_matches_legislation_gov_au():
    scaffold = ScaffoldRegistry().get_scaffold_for_url(
        "https://www.legislation.gov.au/C2004A02123"
    )
    assert isinstance(scaffold, LegislationGovAuScaffold)


def test_declares_dynamic_transport():
    assert LegislationGovAuScaffold().get_transport_type() == "dynamic"


def test_bare_series_url_rewritten_to_text_view():
    sc = LegislationGovAuScaffold()
    assert (
        sc.get_fetch_url("https://www.legislation.gov.au/C2004A02123")
        == "https://www.legislation.gov.au/C2004A02123/latest/text"
    )


def test_non_series_url_left_unchanged():
    sc = LegislationGovAuScaffold()
    url = "https://www.legislation.gov.au/C2004A02123/latest/text"
    assert sc.get_fetch_url(url) == url


def test_has_boilerplate_and_content_selectors():
    sc = LegislationGovAuScaffold()
    assert sc.get_boilerplate_selectors()
    assert "content_area" in sc.get_custom_selectors()
