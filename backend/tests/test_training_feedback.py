"""Integration tests for Phase 5 review feedback loop."""

from __future__ import annotations

import json

from zetarix.training.review_log import ReviewDecision, append_review_decision, decision_from_finding_payload, load_review_decisions


def test_decision_from_finding_payload_camel_case():
    decision = decision_from_finding_payload(
        {
            "id": "sg-pdpa-26",
            "reviewStatus": "rejected",
            "jurisdiction": "Malaysia",
            "pillar": 6,
            "title": "Transfer",
            "scope": "scope",
            "provisions": "s26",
            "impact": "impact",
            "indicator": "6.1",
        }
    )
    assert decision.review_status == "rejected"
    assert decision.jurisdiction == "Malaysia"


def test_rebuild_increases_counts_with_review_seed(tmp_path, monkeypatch):
    from zetarix.training.build_dataset import collect_examples, count_examples
    from zetarix.training.review_log import ReviewDecision, append_review_decision

    log = tmp_path / "review.jsonl"
    monkeypatch.setattr("zetarix.training.review_log.default_review_log_path", lambda: log)
    append_review_decision(
        ReviewDecision(
            finding_id="test-1",
            review_status="verified",
            jurisdiction="Singapore",
            pillar=6,
            title="T",
            scope="S",
            provisions="P",
            impact="I",
            indicator="6.2",
        ),
        log_path=log,
    )
    law, tag = collect_examples(review_log=log)
    counts = count_examples(law, tag)
    assert counts.law_interpreter_total >= 1
    assert counts.positives >= 1


def test_training_stats_shape():
    from zetarix.training.routes import get_training_stats

    stats = get_training_stats()
    assert "law_interpreter_total" in stats
    assert "review_decisions" in stats
