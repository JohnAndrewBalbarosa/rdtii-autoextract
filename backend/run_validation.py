"""RDTII Stage-2 validation CLI - honest scorecard against the golden databases.

Prints *real* numbers only:
  * the ground-truth coverage parsed from the Round 1 / Round 2 workbooks,
  * the known-evidence baseline from the seed CSVs,
  * a harness self-check (scoring gold against itself must yield F1 = 1.0).

It deliberately does NOT print accuracy for the extraction pipeline yet: the pipeline
does not emit ``Finding`` rows in this entry point. Once it does, pass them to
``score(predictions, gold)`` and this file reports the true F1 - no placeholders.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from zetarix.scoring.golden_dataset import load_gold_records, load_reference_items
from zetarix.scoring.scoring import discovery_diff, gold_to_match_item, score

_DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
_RULE = "=" * 78


def main() -> None:
    print(_RULE)
    print(" RDTII STAGE-2 VALIDATION - GOLDEN DATASET SCORECARD")
    print(_RULE)

    gold = load_gold_records(_DOCS)
    refs = load_reference_items(_DOCS)
    if not gold:
        print("No golden records found. Are the RDTII .xlsx files in docs/ ?")
        return

    print(f"Ground-truth mappings (Pillars 6 & 7): {len(gold)}")
    print(f"Known-evidence baseline (seed CSVs):   {len(refs)}\n")

    stats: dict[str, dict[int, int]] = defaultdict(lambda: {6: 0, 7: 0})
    acts: dict[str, set[str]] = defaultdict(set)
    urls: dict[str, set[str]] = defaultdict(set)
    for record in gold:
        stats[record.country][record.pillar_id] += 1
        if record.act_name:
            acts[record.country].add(record.act_name.strip().lower())
        urls[record.country].update(record.urls)

    print(f"  {'Country':<22} | {'P6':>4} | {'P7':>4} | {'Acts':>5} | {'URLs':>5}")
    print(f"  {'-' * 22}-+-{'-' * 4}-+-{'-' * 4}-+-{'-' * 5}-+-{'-' * 5}")
    for country in sorted(stats):
        s = stats[country]
        print(f"  {country:<22} | {s[6]:>4} | {s[7]:>4} | {len(acts[country]):>5} | {len(urls[country]):>5}")
    tot6 = sum(s[6] for s in stats.values())
    tot7 = sum(s[7] for s in stats.values())
    all_acts = set().union(*acts.values()) if acts else set()
    all_urls = set().union(*urls.values()) if urls else set()
    print(f"  {'-' * 22}-+-{'-' * 4}-+-{'-' * 4}-+-{'-' * 5}-+-{'-' * 5}")
    print(f"  {'TOTAL':<22} | {tot6:>4} | {tot7:>4} | {len(all_acts):>5} | {len(all_urls):>5}")

    # Harness self-check: scoring the ground truth against itself proves the matcher
    # is sound (perfect F1) before we trust it on real predictions.
    print("\n" + _RULE)
    print(" HARNESS SELF-CHECK (gold vs gold - must be 1.000)")
    print(_RULE)
    self_report = score([gold_to_match_item(r) for r in gold], list(gold))
    print(f"  precision={self_report.precision:.3f}  recall={self_report.recall:.3f}  f1={self_report.f1:.3f}")
    print(f"  novel-vs-itself (must be 0): {len(discovery_diff([gold_to_match_item(r) for r in gold], list(gold), refs))}")

    print("\n" + _RULE)
    print(" PIPELINE ACCURACY: not wired yet - feed Findings to score(preds, gold).")
    print(_RULE)


if __name__ == "__main__":
    main()
