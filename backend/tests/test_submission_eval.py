"""Tests for submission field-level eval."""

from __future__ import annotations

from datetime import date

from zetarix.domain.entities import Finding, Pillar
from zetarix.scoring.golden_dataset import GoldRecord
from zetarix.training.submission_eval import _score_fields, _field_similarity


def _gold(**kwargs) -> GoldRecord:
    defaults = dict(
        country="Singapore",
        pillar_id=6,
        indicator_id="6.2",
        act_name="Personal Data Protection Act 2012",
        coverage="Horizontal",
        impact="Section 26 requires comparable protection for outbound transfers.",
        timeframe="Since 2012 last amended on 1 February 2021",
        raw_score=None,
        urls=("https://sso.agc.gov.sg/Act/PDPA2012",),
    )
    defaults.update(kwargs)
    return GoldRecord(**defaults)


def test_provisions_requires_gold_similarity_not_just_length():
    pred = Finding(
        title="Home",
        last_update=None,
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        scope="",
        provisions="Part 10A TRANSFER OF REGISTRATION" * 2,
        impact="",
        pillar=Pillar(6),
        indicator="P6-I1",
        confidence=0.5,
        economy="Singapore",
        verbatim_snippet="Part 10A TRANSFER OF REGISTRATION" * 2,
    )
    gold = _gold()
    scores = _score_fields(pred, gold)
    assert len(pred.provisions) >= 20
    assert _field_similarity(pred.provisions, gold.impact) < 0.15
    assert scores["provisions"] is False


def test_last_update_accepts_year_in_title_when_date_missing():
    pred = Finding(
        title="Personal Data Protection Act (revised 1 February 2021)",
        last_update=None,
        url="https://example.com",
        scope="",
        provisions="",
        impact="",
        pillar=Pillar(7),
        indicator="P7-I1",
        confidence=0.5,
        economy="Singapore",
    )
    gold = _gold(
        pillar_id=7,
        indicator_id="7.1",
        timeframe="Since 2012 last amended on 1 February 2021",
    )
    scores = _score_fields(pred, gold)
    assert scores["last_update"] is True


def test_empty_scope_scores_zero_against_gold_coverage():
    pred = Finding(
        title="Personal Data Protection Act 2012",
        last_update=date(2021, 2, 1),
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        scope="",
        provisions="Section 26 outbound transfer text here with enough length.",
        impact="",
        pillar=Pillar(6),
        indicator="P6-I2",
        confidence=0.5,
        economy="Singapore",
    )
    gold = _gold()
    scores = _score_fields(pred, gold)
    assert scores["scope"] is False
