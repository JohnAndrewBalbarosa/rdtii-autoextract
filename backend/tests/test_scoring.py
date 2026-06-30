"""Unit tests for the Stage-2 scoring substrate (precision/recall/F1 + discovery diff)."""

from __future__ import annotations

import pytest

from datetime import date

from zetarix.domain.entities import DiscoveryTag, Finding, Pillar
from zetarix.scoring.golden_dataset import GoldRecord, ReferenceItem
from zetarix.scoring.scoring import (
    MatchItem,
    act_similarity,
    discovery_diff,
    finding_to_match_item,
    is_match,
    normalize_url,
    score,
)


def _item(country="Australia", pillar=6, indicator="6.1", act="Privacy Act 1988", urls=()):
    return MatchItem(country=country, pillar_id=pillar, indicator_id=indicator, act_name=act, urls=urls)


# --- normalisation / similarity ---

def test_normalize_url_is_scheme_and_slash_insensitive():
    assert normalize_url("https://www.legislation.gov.au/C2004/") == "legislation.gov.au/c2004"
    assert normalize_url("http://legislation.gov.au/C2004") == normalize_url("https://www.legislation.gov.au/C2004/")


def test_act_similarity_is_year_insensitive_and_bounded():
    assert act_similarity("Privacy Act 1988", "Privacy Act 2024") == 1.0
    assert act_similarity("Privacy Act", "Customs Act") < 0.6
    assert 0.0 <= act_similarity("", "anything") <= 1.0


# --- matching rule ---

def test_match_requires_same_pillar():
    assert not is_match(_item(pillar=6), _item(pillar=7))


def test_match_on_close_act_name():
    assert is_match(_item(act="My Health Records Act 2012"), _item(act="My Health Records Act 2020"))


def test_match_on_shared_url_even_if_act_differs():
    pred = _item(act="Totally Different Name", urls=("https://legislation.gov.au/C2004",))
    gold = _item(act="Privacy Act 1988", urls=("http://www.legislation.gov.au/C2004/",))
    assert is_match(pred, gold)


def test_no_match_when_country_conflicts():
    assert not is_match(_item(country="Australia"), _item(country="Singapore"))


def test_match_when_prediction_omits_country():
    assert is_match(_item(country=""), _item(country="Australia"))


# --- F1 aggregation ---

def test_perfect_score():
    gold = [_item(indicator="6.1"), _item(indicator="6.2", act="Telecommunications Act")]
    report = score(list(gold), list(gold))
    assert report.precision == 1.0 and report.recall == 1.0 and report.f1 == 1.0


def test_partial_score_counts_fp_and_fn():
    gold = [_item(indicator="6.1", act="Privacy Act"), _item(indicator="6.2", act="Telecom Act")]
    preds = [_item(indicator="6.1", act="Privacy Act"), _item(indicator="6.9", act="Made Up Act")]
    report = score(preds, gold)
    assert report.true_positives == 1
    assert report.false_positives == 1  # the made-up act
    assert report.false_negatives == 1  # Telecom Act missed
    assert report.precision == pytest.approx(0.5)
    assert report.recall == pytest.approx(0.5)


def test_one_to_one_matching_no_double_count():
    # Two identical preds must not both match a single gold record.
    gold = [_item(act="Privacy Act 1988")]
    preds = [_item(act="Privacy Act 1988"), _item(act="Privacy Act 1988")]
    report = score(preds, gold)
    assert report.true_positives == 1
    assert report.false_positives == 1


def test_per_pillar_breakdown_present():
    gold = [_item(pillar=6, indicator="6.1"), _item(pillar=7, indicator="7.1", act="Telecom Act")]
    report = score(list(gold), list(gold))
    assert set(report.per_pillar) == {6, 7}
    assert report.per_pillar[6].f1 == 1.0


def test_empty_predictions_zero_score():
    gold = [_item()]
    report = score([], gold)
    assert report.f1 == 0.0 and report.false_negatives == 1


# --- discovery diff (R20) ---

def test_discovery_flags_act_absent_from_gold_and_refs():
    gold = [GoldRecord("Australia", 6, "6.1", "Privacy Act 1988", "", "", "", 0.5,
                       ("https://legislation.gov.au/C2004",))]
    refs = (ReferenceItem("Australia", "Cyber Security Strategy", "", "", "https://homeaffairs.gov.au/x"),)
    novel = _item(act="Brand New Data Bill 2026", urls=("https://newportal.gov.au/bill",))
    known = _item(act="Privacy Act 1988", urls=("https://legislation.gov.au/C2004",))
    result = discovery_diff([novel, known], gold, refs)
    acts = [m.act_name for m in result]
    assert "Brand New Data Bill 2026" in acts
    assert "Privacy Act 1988" not in acts  # already in gold


def test_discovery_excludes_reference_csv_acts():
    refs = (ReferenceItem("Australia", "Cyber Security Strategy", "", "", "https://homeaffairs.gov.au/x"),)
    pred = _item(act="Cyber Security Strategy", urls=("https://homeaffairs.gov.au/x",))
    assert discovery_diff([pred], [], refs) == []


# --- indicator format-agnostic matching (P6-I1 ↔ 6.1) ---

def _finding(indicator="P6-I1", economy="Australia", act="Privacy Act 1988", url="https://legislation.gov.au/C2004"):
    return Finding(
        title=act,
        last_update=date(2024, 1, 1),
        url=url,
        scope="",
        provisions="",
        impact="",
        pillar=Pillar.CROSS_BORDER_DATA_FLOWS,
        indicator=indicator,
        confidence=0.9,
        economy=economy,
        discovery_tag=DiscoveryTag.NEW,
    )


def test_finding_to_match_item_canonicalises_indicator_and_uses_economy():
    item = finding_to_match_item(_finding(indicator="P6-I1", economy="Australia"))
    assert item.indicator_id == "P6-I1"
    assert item.country == "Australia"


def test_finding_to_match_item_canonicalises_dotted_indicator():
    item = finding_to_match_item(_finding(indicator="6.1"))
    assert item.indicator_id == "P6-I1"


def test_canonical_prediction_matches_dotted_gold_record():
    # Finding with canonical "P6-I1" must score against a gold record stored as "6.1".
    pred = _finding(indicator="P6-I1", act="Privacy Act 1988")
    gold = [GoldRecord("Australia", 6, "6.1", "Privacy Act 1988", "", "", "", 0.5,
                       ("https://legislation.gov.au/C2004",))]
    report = score([pred], gold)
    assert report.true_positives == 1
    assert report.false_positives == 0
    assert report.false_negatives == 0
    assert report.f1 == 1.0


def test_economy_falls_back_to_legacy_country_attr():
    # A Finding-like object exposing only a legacy `country` attr (no economy set).
    legacy = _finding(economy="")
    object.__setattr__(legacy, "country", "Singapore")
    item = finding_to_match_item(legacy)
    assert item.country == "Singapore"
