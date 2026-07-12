"""CLI to seed review decisions from mock/UI findings for the feedback loop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from zetarix.pretrain.dataset.review_log import ReviewDecision, append_review_decision, load_review_decisions

_DEFAULT_SEED = Path(__file__).resolve().parents[4] / "frontend" / "src" / "data" / "findings.mock.ts"


def seed_from_json(path: Path) -> int:
    """Load verify/reject rows from a JSON array of finding dicts."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    added = 0
    for row in rows:
        status = row.get("reviewStatus") or row.get("review_status")
        if status not in ("verified", "rejected"):
            continue
        decision = ReviewDecision(
            finding_id=str(row["id"]),
            review_status=status,
            jurisdiction=str(row.get("jurisdiction", "")),
            pillar=int(row["pillar"]),
            title=str(row.get("title", "")),
            scope=str(row.get("scope", "")),
            provisions=str(row.get("provisions", "")),
            impact=str(row.get("impact", "")),
            indicator=str(row.get("indicator", "")),
            indicator_label=str(row.get("indicatorLabel") or row.get("indicator_label", "")),
            document_title=str(row.get("documentTitle") or row.get("document_title", "")),
            article_number=str(row.get("articleNumber") or row.get("article_number", "")),
            language=str(row.get("language", "en")),
        )
        append_review_decision(decision)
        added += 1
    return added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed review_decisions.jsonl from a JSON export.")
    parser.add_argument(
        "--input",
        default=str(Path(__file__).resolve().parents[3] / "data" / "training" / "seed_review_decisions.json"),
        help="JSON file: array of findings with reviewStatus verified|rejected",
    )
    args = parser.parse_args(argv)
    path = Path(args.input)
    if not path.exists():
        print(f"Seed file not found: {path}")
        return 1
    before = len(load_review_decisions())
    added = seed_from_json(path)
    after = len(load_review_decisions())
    print(f"Seeded {added} decisions ({before} -> {after} total in review log)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
