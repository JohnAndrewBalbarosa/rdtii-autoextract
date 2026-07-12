"""Build Law Interpreter and Tag Generator training JSONL from gold + review labels.

Phase 1 of ``backend/docs/pipeline-stages-and-training.md``.

Regenerate:
    cd backend && PYTHONPATH=src python -m zetarix.pretrain.dataset.build
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence, TypeVar

from zetarix.domain.indicator_codes import to_db
from zetarix.scoring.golden_dataset import GoldRecord, load_gold_records
from zetarix.pretrain.dataset.review_log import default_review_log_path, load_review_decisions
from zetarix.pretrain.dataset.schemas import (
    LawInterpreterExample,
    ReviewDecision,
    TagGeneratorExample,
)
from zetarix.pretrain.paths import DOCS_DIR, TRAINING_DATA_DIR

_DEFAULT_DOCS = str(DOCS_DIR)
_DEFAULT_OUT = TRAINING_DATA_DIR

T = TypeVar("T")

_FOCUS_JURISDICTIONS = ("Australia", "Singapore", "Malaysia")
_MIN_FINETUNE_EXAMPLES = 200
_MIN_REAL_PROVISION_CHARS = 80

_OBLIGATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("prohibition", re.compile(r"\b(shall not|must not|prohibit|restriction|restricted|not transfer)\b", re.I)),
    ("requirement", re.compile(r"\b(shall|must|required|requirement|obligation|implement)\b", re.I)),
    ("permission", re.compile(r"\b(may|permit|allowed|enables?|authorised)\b", re.I)),
    ("accountability", re.compile(r"\b(accountab|responsible|duty|controller|processor)\b", re.I)),
    ("assessment", re.compile(r"\b(assessment|impact assessment|evaluate|dossier)\b", re.I)),
)

_TRIGGER_SPLIT = re.compile(r"[;,\n]|(?:\band\b)|(?:\bor\b)|(?:\bwhere\b)|(?:\bwhen\b)|(?:\bif\b)", re.I)


@dataclass(frozen=True)
class DatasetCounts:
    """Example counts per stage, broken down by jurisdiction and pillar."""

    law_interpreter_total: int
    tag_generator_total: int
    law_interpreter_by_jurisdiction: dict[str, int]
    tag_generator_by_jurisdiction: dict[str, int]
    law_interpreter_by_pillar: dict[int, int]
    tag_generator_by_pillar: dict[int, int]
    law_interpreter_by_jurisdiction_pillar: dict[tuple[str, int], int]
    tag_generator_by_jurisdiction_pillar: dict[tuple[str, int], int]
    positives: int
    negatives: int
    focus_jurisdiction_totals: dict[str, dict[str, int]]

    def enough_for_finetune(self, *, min_examples: int = _MIN_FINETUNE_EXAMPLES) -> bool:
        return (
            self.law_interpreter_total >= min_examples
            and self.tag_generator_total >= min_examples
        )

    def to_report(self) -> str:
        lines = [
            "=== Training dataset counts ===",
            f"Law Interpreter total: {self.law_interpreter_total}",
            f"Tag Generator total:   {self.tag_generator_total}",
            f"Positives: {self.positives}  Negatives (hard): {self.negatives}",
            "",
            "Law Interpreter by jurisdiction:",
        ]
        for key in sorted(self.law_interpreter_by_jurisdiction):
            lines.append(f"  {key}: {self.law_interpreter_by_jurisdiction[key]}")
        lines.append("")
        lines.append("Tag Generator by jurisdiction:")
        for key in sorted(self.tag_generator_by_jurisdiction):
            lines.append(f"  {key}: {self.tag_generator_by_jurisdiction[key]}")
        lines.extend(
            [
                "",
                "By pillar (law_interpreter / tag_generator):",
            ]
        )
        pillars = sorted(set(self.law_interpreter_by_pillar) | set(self.tag_generator_by_pillar))
        for pillar in pillars:
            li = self.law_interpreter_by_pillar.get(pillar, 0)
            tg = self.tag_generator_by_pillar.get(pillar, 0)
            lines.append(f"  Pillar {pillar}: {li} / {tg}")
        lines.extend(["", f"Focus jurisdictions ({', '.join(_FOCUS_JURISDICTIONS)}):"])
        for jurisdiction in _FOCUS_JURISDICTIONS:
            bucket = self.focus_jurisdiction_totals.get(jurisdiction, {})
            lines.append(
                f"  {jurisdiction}: law_interpreter={bucket.get('law_interpreter', 0)}, "
                f"tag_generator={bucket.get('tag_generator', 0)}"
            )
        if self.enough_for_finetune():
            lines.append(
                f"\nGlobal totals ({self.law_interpreter_total}/{self.tag_generator_total}) "
                f"meet the ~{_MIN_FINETUNE_EXAMPLES} per-stage minimum — LoRA is a viable stretch path."
            )
        else:
            lines.append(
                f"\nGlobal totals are below ~{_MIN_FINETUNE_EXAMPLES} per stage. "
                "Lean on few-shot/RAG grounding (Phase 2) as the primary path."
            )
        focus_min = min(
            self.focus_jurisdiction_totals.get(j, {}).get("law_interpreter", 0)
            for j in _FOCUS_JURISDICTIONS
        )
        if focus_min < 30:
            lines.append(
                f"Focus jurisdictions (SG/AU/MY) have only {focus_min}–"
                f"{max(self.focus_jurisdiction_totals.get(j, {}).get('law_interpreter', 0) for j in _FOCUS_JURISDICTIONS)} "
                "examples each — too small for jurisdiction-specific fine-tunes; few-shot/RAG is primary for Round 1."
            )
        return "\n".join(lines)


def infer_obligation_type(coverage: str, impact: str) -> str:
    text = f"{coverage} {impact}"
    for name, pattern in _OBLIGATION_PATTERNS:
        if pattern.search(text):
            return name
    return "other"


def extract_triggers(coverage: str) -> tuple[str, ...]:
    if not coverage.strip():
        return ()
    parts = [_clean_fragment(p) for p in _TRIGGER_SPLIT.split(coverage)]
    triggers = tuple(p for p in parts if len(p) >= 8)
    if triggers:
        return triggers[:6]
    cleaned = coverage.strip()
    return (cleaned[:200],) if cleaned else ()


def _clean_fragment(text: str) -> str:
    return " ".join(text.split()).strip(" .")


def _provision_input(
    *,
    act_name: str,
    coverage: str,
    impact: str,
    provisions: str = "",
    article_number: str = "",
    document_title: str = "",
) -> str:
    chunks = []
    if document_title:
        chunks.append(f"Document: {document_title}")
    if act_name:
        chunks.append(f"Act: {act_name}")
    if article_number:
        chunks.append(f"Article: {article_number}")
    if provisions:
        chunks.append(f"Provision: {provisions}")
    elif coverage:
        chunks.append(f"Provision context: {coverage}")
    if impact:
        chunks.append(f"Legal effect: {impact}")
    return "\n".join(chunks)


def _legal_interpretation(*, scope: str, impact: str, provisions: str = "") -> str:
    parts = []
    if scope:
        parts.append(f"Scope: {scope}")
    if provisions:
        parts.append(f"Provision: {provisions}")
    if impact:
        parts.append(f"Impact: {impact}")
    return "\n".join(parts)


def gold_to_law_interpreter(record: GoldRecord) -> LawInterpreterExample:
    return LawInterpreterExample(
        tagged_provision_input=_provision_input(
            act_name=record.act_name,
            coverage=record.coverage,
            impact=record.impact,
        ),
        jurisdiction=record.country,
        pillar=record.pillar_id,
        obligation_type=infer_obligation_type(record.coverage, record.impact),
        scope=record.coverage,
        applicability_triggers=extract_triggers(record.coverage),
        plain_summary=record.impact or record.coverage,
        label="positive",
        source_id=f"gold-{record.country}-{record.indicator_id}",
        source="gold",
    )


def gold_to_tag_generator(record: GoldRecord) -> TagGeneratorExample:
    indicator = to_db(record.indicator_id)
    return TagGeneratorExample(
        legal_interpretation=_legal_interpretation(
            scope=record.coverage,
            impact=record.impact,
        ),
        jurisdiction=record.country,
        pillar=record.pillar_id,
        precedent_tags=(),
        indicator_tags=(indicator,),
        rationale=(
            f"Reviewer-validated mapping to RDTII indicator {indicator} "
            f"({record.act_name}): {record.impact or record.coverage}"
        ),
        label="positive",
        source_id=f"gold-{record.country}-{record.indicator_id}",
        source="gold",
    )


def review_to_law_interpreter(decision: ReviewDecision) -> LawInterpreterExample:
    label = "positive" if decision.review_status == "verified" else "negative"
    return LawInterpreterExample(
        tagged_provision_input=_provision_input(
            act_name=decision.title,
            coverage=decision.scope,
            impact=decision.impact,
            provisions=decision.provisions,
            article_number=decision.article_number,
            document_title=decision.document_title,
        ),
        jurisdiction=decision.jurisdiction,
        pillar=decision.pillar,
        obligation_type=infer_obligation_type(decision.scope, decision.impact),
        scope=decision.scope,
        applicability_triggers=extract_triggers(decision.scope),
        plain_summary=decision.impact or decision.scope,
        label=label,
        source_id=decision.finding_id,
        source="review",
    )


def review_to_tag_generator(decision: ReviewDecision) -> TagGeneratorExample:
    label = "positive" if decision.review_status == "verified" else "negative"
    indicator = to_db(decision.indicator) if decision.indicator else ""
    tags = (indicator,) if indicator and label == "positive" else ()
    return TagGeneratorExample(
        legal_interpretation=_legal_interpretation(
            scope=decision.scope,
            impact=decision.impact,
            provisions=decision.provisions,
        ),
        jurisdiction=decision.jurisdiction,
        pillar=decision.pillar,
        precedent_tags=(),
        indicator_tags=tags,
        rationale=(
            decision.indicator_label
            or f"{'Verified' if label == 'positive' else 'Rejected'} mapping for {decision.indicator}"
        ),
        label=label,
        source_id=decision.finding_id,
        source="review",
    )


def collect_examples(
    *,
    docs_dir: str | None = None,
    review_log: Path | str | None = None,
) -> tuple[list[LawInterpreterExample], list[TagGeneratorExample]]:
    gold = load_gold_records(docs_dir or _DEFAULT_DOCS)
    reviews = load_review_decisions(review_log)

    law_examples = [gold_to_law_interpreter(r) for r in gold]
    tag_examples = [gold_to_tag_generator(r) for r in gold]

    for decision in reviews:
        law_examples.append(review_to_law_interpreter(decision))
        tag_examples.append(review_to_tag_generator(decision))

    return law_examples, tag_examples


def is_real_provision_example(example: LawInterpreterExample | TagGeneratorExample) -> bool:
    """True when the example carries article-level provision text (not spreadsheet proxy)."""
    if example.source != "review":
        return False
    if isinstance(example, LawInterpreterExample):
        return len(example.tagged_provision_input) > _MIN_REAL_PROVISION_CHARS and "Provision:" in example.tagged_provision_input
    return "Provision:" in example.legal_interpretation and len(example.legal_interpretation) > _MIN_REAL_PROVISION_CHARS


def count_real_examples(
    law_examples: Sequence[LawInterpreterExample],
    tag_examples: Sequence[TagGeneratorExample],
) -> dict[str, dict[str, int]]:
    """Per-jurisdiction counts of reviewer-verified examples with real provision text."""
    out: dict[str, dict[str, int]] = {
        j: {"law_interpreter": 0, "tag_generator": 0} for j in _FOCUS_JURISDICTIONS
    }
    for ex in law_examples:
        if is_real_provision_example(ex):
            bucket = out.setdefault(ex.jurisdiction, {"law_interpreter": 0, "tag_generator": 0})
            bucket["law_interpreter"] += 1
    for ex in tag_examples:
        if is_real_provision_example(ex):
            bucket = out.setdefault(ex.jurisdiction, {"law_interpreter": 0, "tag_generator": 0})
            bucket["tag_generator"] += 1
    return out


def count_examples(
    law_examples: Sequence[LawInterpreterExample],
    tag_examples: Sequence[TagGeneratorExample],
) -> DatasetCounts:
    li_j = Counter(ex.jurisdiction for ex in law_examples)
    tg_j = Counter(ex.jurisdiction for ex in tag_examples)
    li_p = Counter(ex.pillar for ex in law_examples)
    tg_p = Counter(ex.pillar for ex in tag_examples)
    li_jp = Counter((ex.jurisdiction, ex.pillar) for ex in law_examples)
    tg_jp = Counter((ex.jurisdiction, ex.pillar) for ex in tag_examples)
    positives = sum(1 for ex in law_examples if ex.label == "positive")
    negatives = sum(1 for ex in law_examples if ex.label == "negative")

    focus: dict[str, dict[str, int]] = {}
    for jurisdiction in _FOCUS_JURISDICTIONS:
        focus[jurisdiction] = {
            "law_interpreter": li_j.get(jurisdiction, 0),
            "tag_generator": tg_j.get(jurisdiction, 0),
        }

    return DatasetCounts(
        law_interpreter_total=len(law_examples),
        tag_generator_total=len(tag_examples),
        law_interpreter_by_jurisdiction=dict(li_j),
        tag_generator_by_jurisdiction=dict(tg_j),
        law_interpreter_by_pillar=dict(li_p),
        tag_generator_by_pillar=dict(tg_p),
        law_interpreter_by_jurisdiction_pillar=dict(li_jp),
        tag_generator_by_jurisdiction_pillar=dict(tg_jp),
        positives=positives,
        negatives=negatives,
        focus_jurisdiction_totals=focus,
    )


def _stratum_key(example: LawInterpreterExample | TagGeneratorExample) -> tuple[str, int]:
    return (example.jurisdiction, example.pillar)


def stratified_split(
    examples: Sequence[T],
    *,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    seed: int = 42,
    key_fn=_stratum_key,
) -> tuple[list[T], list[T], list[T]]:
    """80/10/10 split stratified by (jurisdiction, pillar)."""
    rng = random.Random(seed)
    buckets: dict[tuple[str, int], list[T]] = defaultdict(list)
    for example in examples:
        buckets[key_fn(example)].append(example)

    train: list[T] = []
    val: list[T] = []
    test: list[T] = []

    for bucket in buckets.values():
        items = list(bucket)
        rng.shuffle(items)
        n = len(items)
        if n == 1:
            train.extend(items)
            continue
        if n == 2:
            train.append(items[0])
            test.append(items[1])
            continue

        n_train = max(1, int(round(n * train_ratio)))
        n_val = max(1, int(round(n * val_ratio)))
        if n_train + n_val >= n:
            n_val = 1
            n_train = n - 2
        n_test = n - n_train - n_val
        if n_test < 1:
            n_test = 1
            n_train = max(1, n - n_val - n_test)

        train.extend(items[:n_train])
        val.extend(items[n_train : n_train + n_val])
        test.extend(items[n_train + n_val :])

    rng.shuffle(train)
    rng.shuffle(val)
    rng.shuffle(test)
    return train, val, test


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_datasets(
    *,
    docs_dir: str | None = None,
    review_log: Path | str | None = None,
    out_dir: Path | str | None = None,
    seed: int = 42,
) -> DatasetCounts:
    """Build JSONL datasets + train/val/test splits; return counts report."""
    out = Path(out_dir) if out_dir else _DEFAULT_OUT
    law_examples, tag_examples = collect_examples(docs_dir=docs_dir, review_log=review_log)
    counts = count_examples(law_examples, tag_examples)

    li_train, li_val, li_test = stratified_split(law_examples, seed=seed)
    tg_train, tg_val, tg_test = stratified_split(tag_examples, seed=seed)

    splits = out / "splits"
    _write_jsonl(out / "law_interpreter_train.jsonl", (ex.to_dict() for ex in law_examples))
    _write_jsonl(out / "tag_generator_train.jsonl", (ex.to_dict() for ex in tag_examples))
    _write_jsonl(splits / "law_interpreter_train.jsonl", (ex.to_dict() for ex in li_train))
    _write_jsonl(splits / "law_interpreter_val.jsonl", (ex.to_dict() for ex in li_val))
    _write_jsonl(splits / "law_interpreter_test.jsonl", (ex.to_dict() for ex in li_test))
    _write_jsonl(splits / "tag_generator_train.jsonl", (ex.to_dict() for ex in tg_train))
    _write_jsonl(splits / "tag_generator_val.jsonl", (ex.to_dict() for ex in tg_val))
    _write_jsonl(splits / "tag_generator_test.jsonl", (ex.to_dict() for ex in tg_test))

    report_path = out / "dataset_report.txt"
    report_path.write_text(counts.to_report() + "\n", encoding="utf-8")
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Law Interpreter / Tag Generator training JSONL.")
    parser.add_argument("--docs-dir", default=None, help="Path to repo docs/ with RDTII workbooks")
    parser.add_argument("--review-log", default=str(default_review_log_path()))
    parser.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    counts = build_datasets(
        docs_dir=args.docs_dir,
        review_log=args.review_log,
        out_dir=args.out_dir,
        seed=args.seed,
    )
    print(counts.to_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
