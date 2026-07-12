"""Tests for the training data pipeline (Phase 1)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from zetarix.scoring.golden_dataset import GoldRecord, load_gold_records
from zetarix.training.build_dataset import (
    build_datasets,
    collect_examples,
    count_examples,
    gold_to_law_interpreter,
    gold_to_tag_generator,
    stratified_split,
)
from zetarix.training.review_log import ReviewDecision, append_review_decision, load_review_decisions
from zetarix.training.schemas import LawInterpreterExample

_DOCS = os.path.join(os.path.dirname(__file__), "..", "..", "docs")
_HAS_DB = os.path.exists(os.path.join(_DOCS, "ESCAP-RDTII-2.1_ Round 1 Database.xlsx"))


def _sample_gold() -> GoldRecord:
        return GoldRecord(
            country="Singapore",
            pillar_id=6,
            indicator_id="6.2",
            act_name="Personal Data Protection Act 2012",
            coverage="Applies to organisations transferring personal data outside Singapore.",
            impact="Establishes a conditional cross-border transfer regime.",
            timeframe="Since 2012",
            raw_score=1.0,
            urls=("https://sso.agc.gov.sg/Act/PDPA2012",),
        )


def test_gold_to_law_interpreter_maps_fields():
    ex = gold_to_law_interpreter(_sample_gold())
    assert ex.jurisdiction == "Singapore"
    assert ex.pillar == 6
    assert ex.scope == _sample_gold().coverage
    assert ex.label == "positive"
    assert "PDPA" in ex.tagged_provision_input or "Personal Data" in ex.tagged_provision_input


def test_gold_to_tag_generator_uses_db_indicator_form():
    ex = gold_to_tag_generator(_sample_gold())
    assert ex.indicator_tags == ("6.2",)
    assert ex.jurisdiction == "Singapore"


def test_stratified_split_preserves_all_examples():
    examples = [
        LawInterpreterExample(
            tagged_provision_input=f"text-{i}",
            jurisdiction=jurisdiction,
            pillar=pillar,
            obligation_type="requirement",
            scope="scope",
            applicability_triggers=(),
            plain_summary="summary",
            source_id=f"id-{i}",
        )
        for i, (jurisdiction, pillar) in enumerate(
            [
                ("Singapore", 6),
                ("Singapore", 6),
                ("Australia", 6),
                ("Malaysia", 7),
                ("Malaysia", 7),
            ]
        )
    ]
    train, val, test = stratified_split(examples, seed=1)
    assert len(train) + len(val) + len(test) == len(examples)


def test_review_log_round_trip(tmp_path):
    log = tmp_path / "review.jsonl"
    decision = ReviewDecision(
        finding_id="sg-pdpa-26",
        review_status="verified",
        jurisdiction="Singapore",
        pillar=6,
        title="Transfer Limitation",
        scope="Cross-border transfers",
        provisions="Section 26",
        impact="Conditional regime",
        indicator="6.2",
    )
    append_review_decision(decision, log_path=log)
    loaded = load_review_decisions(log)
    assert len(loaded) == 1
    assert loaded[0].finding_id == "sg-pdpa-26"


@pytest.mark.skipif(not _HAS_DB, reason="RDTII databases not present in docs/")
def test_build_datasets_writes_splits(tmp_path):
    out = tmp_path / "training"
    counts = build_datasets(docs_dir=_DOCS, review_log=tmp_path / "empty.jsonl", out_dir=out)
    assert counts.law_interpreter_total >= 200
    assert (out / "law_interpreter_train.jsonl").exists()
    assert (out / "splits" / "law_interpreter_test.jsonl").exists()
    report = (out / "dataset_report.txt").read_text(encoding="utf-8")
    assert "Training dataset counts" in report


@pytest.mark.skipif(not _HAS_DB, reason="RDTII databases not present in docs/")
def test_focus_jurisdictions_reported():
    law, tag = collect_examples(docs_dir=_DOCS, review_log=Path("/nonexistent"))
    counts = count_examples(law, tag)
    assert counts.focus_jurisdiction_totals["Singapore"]["law_interpreter"] >= 10
    assert counts.focus_jurisdiction_totals["Australia"]["tag_generator"] >= 5
