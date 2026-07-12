"""Tests for few-shot retriever and eval harness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zetarix.training.eval_harness import (
    compare_baselines,
    score_law_interpreter,
    score_tag_generator,
)
from zetarix.training.few_shot_retriever import FewShotRetriever, jaccard_similarity
from zetarix.training.schemas import LawInterpreterExample, TagGeneratorExample


def _law(jurisdiction: str, pillar: int, text: str, source_id: str) -> LawInterpreterExample:
    return LawInterpreterExample(
        tagged_provision_input=text,
        jurisdiction=jurisdiction,
        pillar=pillar,
        obligation_type="requirement",
        scope="scope",
        applicability_triggers=("trigger",),
        plain_summary="summary",
        source_id=source_id,
    )


def test_jaccard_similarity_is_bounded():
    assert jaccard_similarity("cross border transfer data", "cross border transfer regime") > 0.3
    assert 0.0 <= jaccard_similarity("", "anything") <= 1.0


def test_few_shot_retriever_filters_jurisdiction_and_pillar():
    retriever = FewShotRetriever(
        law_examples=[
            _law("Singapore", 6, "transfer personal data abroad singapore", "sg-1"),
            _law("Australia", 6, "privacy act cross border disclosure", "au-1"),
        ],
        tag_examples=[],
    )
    hits = retriever.retrieve_law_interpreter(
        tagged_provision_input="transfer personal data outside singapore organisation",
        jurisdiction="Singapore",
        pillar=6,
        k=2,
    )
    assert hits
    assert hits[0].source_id == "sg-1"


def test_score_law_interpreter_accuracy():
    gold = [
        LawInterpreterExample(
            tagged_provision_input="x",
            jurisdiction="SG",
            pillar=6,
            obligation_type="requirement",
            scope="All orgs",
            applicability_triggers=(),
            plain_summary="s",
        )
    ]
    preds = [{"obligation_type": "requirement", "scope": "All orgs"}]
    metrics = score_law_interpreter(preds, gold)
    assert metrics.obligation_type_accuracy == 1.0
    assert metrics.scope_accuracy == 1.0


def test_score_tag_generator_f1():
    gold = [
        TagGeneratorExample(
            legal_interpretation="x",
            jurisdiction="SG",
            pillar=6,
            precedent_tags=(),
            indicator_tags=("6.2",),
            rationale="r",
        )
    ]
    preds = [{"indicator_tags": ["6.2", "6.9"]}]
    metrics = score_tag_generator(preds, gold)
    assert metrics.true_positives == 1
    assert metrics.false_positives == 1
    assert metrics.precision == 0.5


def test_compare_baselines_flags_small_margin():
    from zetarix.training.eval_harness import EvalReport, StageEvalResult, TagGeneratorMetrics, LawInterpreterMetrics

    li = LawInterpreterMetrics(0.5, 0.5, 10, 5, 5)
    report = EvalReport(
        results=(
            StageEvalResult(
                mode="zero_shot",
                law_interpreter=li,
                tag_generator=TagGeneratorMetrics(0.6, 0.6, 0.6, 6, 4, 4, 10),
            ),
            StageEvalResult(
                mode="few_shot",
                law_interpreter=LawInterpreterMetrics(0.7, 0.7, 10, 7, 7),
                tag_generator=TagGeneratorMetrics(0.8, 0.8, 0.8, 8, 2, 2, 10),
            ),
            StageEvalResult(
                mode="system_prompt_baseline",
                law_interpreter=LawInterpreterMetrics(0.72, 0.72, 10, 7, 7),
                tag_generator=TagGeneratorMetrics(0.82, 0.82, 0.82, 8, 2, 2, 10),
            ),
        )
    )
    verdict = compare_baselines(report)
    assert "NOT beat" in verdict or "delta" in verdict.lower()
