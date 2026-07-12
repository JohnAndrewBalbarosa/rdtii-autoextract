"""Tests for many-to-one discovery matching in submission eval."""

from __future__ import annotations

from zetarix.domain.entities import Finding, Pillar
from zetarix.scoring.golden_dataset import GoldRecord
from zetarix.pretrain.eval.submission import evaluate_submission


def _gold(**kwargs) -> GoldRecord:
    defaults = dict(
        country="Australia",
        pillar_id=6,
        indicator_id="6.1",
        act_name="Privacy Act 1988",
        coverage="Horizontal",
        impact="Cross-border transfer rules under APP 8.",
        timeframe="Since 1988 last amended 2024",
        raw_score=None,
        urls=("https://www.legislation.gov.au/C2004A03712",),
    )
    defaults.update(kwargs)
    return GoldRecord(**defaults)


def _pred(indicator: str, section: str) -> Finding:
    return Finding(
        title="Privacy Act 1988",
        last_update=None,
        url="https://www.legislation.gov.au/C2004A03712",
        scope="All organisations",
        provisions=f"Section {section} text about cross border transfer with enough length here.",
        impact="Requires safeguards for overseas disclosure.",
        pillar=Pillar(6),
        indicator=indicator,
        confidence=0.7,
        economy="Australia",
        article_section=f"Section {section}",
        verbatim_snippet=f"Section {section} text",
    )


def test_many_section_findings_same_act_are_not_false_positives(monkeypatch):
    golds = [_gold(indicator_id="6.1"), _gold(indicator_id="6.2", impact="Other APP.")]
    preds = [_pred("P6-I1", "26"), _pred("P6-I1", "27"), _pred("P6-I2", "28")]

    monkeypatch.setattr(
        "zetarix.pretrain.eval.submission.load_gold_records",
        lambda docs_dir=None: golds,
    )
    report = evaluate_submission(preds, country="Australia", pillar=6)
    assert report.findings_count == 3
    assert report.discovery_precision == 1.0
    assert report.matched_pairs == 3
