"""Field-level submission eval — 6 mandatory Round-1 fields vs gold (Priority 6)."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from typing import Sequence
from datetime import date, datetime
from pathlib import Path

from zetarix.domain.entities import Finding
from zetarix.domain.indicator_codes import to_canonical
from zetarix.scoring.golden_dataset import GoldRecord, load_gold_records
from zetarix.scoring.scoring import _YEAR_RE, act_similarity, is_match, normalize_url

from zetarix.pretrain.paths import SUBMISSION_EVAL_REPORT_PATH

_FOCUS = ("Australia", "Singapore", "Malaysia")
_DEFAULT_REPORT = SUBMISSION_EVAL_REPORT_PATH

_WORD_RE = re.compile(r"[a-z0-9]+")
_MIN_PROVISION_CHARS = 20
_PROVISION_SIM_THRESHOLD = 0.15
_SCOPE_SIM_THRESHOLD = 0.5
_IMPACT_SIM_THRESHOLD = 0.4
_TITLE_SIM_THRESHOLD = 0.6


@dataclass(frozen=True)
class FieldScore:
    field: str
    correct: int
    total: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass(frozen=True)
class SubmissionEvalReport:
    country: str
    pillar: int
    findings_count: int
    gold_count: int
    matched_pairs: int
    field_scores: tuple[FieldScore, ...]
    discovery_precision: float
    discovery_recall: float
    discovery_f1: float

    def to_dict(self) -> dict:
        return asdict(self)


def _tokens(text: str) -> frozenset[str]:
    return frozenset(_WORD_RE.findall(text.lower()))


def _field_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _gold_provision_text(gold: GoldRecord) -> str:
    """Best available gold text to compare against predicted verbatim provisions."""
    return gold.impact or gold.coverage or ""


def _pred_provision_text(pred: Finding) -> str:
    return (pred.provisions or pred.verbatim_snippet or "").strip()


def _years_in_text(text: str) -> frozenset[int]:
    return frozenset(int(m.group()) for m in _YEAR_RE.finditer(text or ""))


def _parse_last_update(value: object) -> date | None:
    """Accept date objects, ISO strings, and common textual dates."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    for pattern in (
        r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b",
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
    ):
        match = re.search(pattern, text, re.I)
        if match:
            try:
                return datetime.strptime(match.group(0).replace(",", ""), "%d %B %Y").date()
            except ValueError:
                try:
                    return datetime.strptime(match.group(0).replace(",", ""), "%B %d %Y").date()
                except ValueError:
                    continue
    years = _years_in_text(text)
    if len(years) == 1:
        return date(next(iter(years)), 1, 1)
    return None


def _last_update_matches(pred: Finding, gold: GoldRecord) -> bool:
    """True when the predicted amendment year overlaps any year in the gold timeframe."""
    gold_years = _years_in_text(gold.timeframe or "")
    if not gold_years:
        return False

    pred_date = pred.last_update if isinstance(pred.last_update, date) else _parse_last_update(pred.last_update)
    if pred_date is not None and pred_date.year in gold_years:
        return True

    # Fall back to year mentions in title / URL when structured date is absent.
    pred_years = _years_in_text(f"{pred.title} {pred.url}")
    return bool(pred_years & gold_years)


def _score_fields(pred: Finding, gold: GoldRecord) -> dict[str, bool]:
    pred_indicator = to_canonical(pred.indicator)
    gold_indicator = to_canonical(gold.indicator_id)
    provision_text = _pred_provision_text(pred)
    gold_provision = _gold_provision_text(gold)
    return {
        "title": act_similarity(pred.title, gold.act_name) >= _TITLE_SIM_THRESHOLD,
        "last_update": _last_update_matches(pred, gold),
        "url": bool({normalize_url(pred.url)} & {normalize_url(u) for u in gold.urls if u}),
        "scope": _field_similarity(pred.scope, gold.coverage) >= _SCOPE_SIM_THRESHOLD,
        "provisions": (
            len(provision_text) >= _MIN_PROVISION_CHARS
            and _field_similarity(provision_text, gold_provision) >= _PROVISION_SIM_THRESHOLD
        ),
        "impact": _field_similarity(pred.impact, gold.impact) >= _IMPACT_SIM_THRESHOLD,
        "indicator": pred_indicator == gold_indicator,
    }


def _match_gold(pred: Finding, gold: GoldRecord) -> bool:
    from zetarix.scoring.scoring import gold_to_match_item, finding_to_match_item

    return is_match(finding_to_match_item(pred), gold_to_match_item(gold))


def evaluate_all_submissions(
    findings: list[Finding],
    *,
    docs_dir: str | None = None,
) -> dict:
    """Aggregate submission eval across SG/AU/MY × P6/P7."""
    reports = []
    for country in _FOCUS:
        for pillar in (6, 7):
            reports.append(evaluate_submission(findings, country=country, pillar=pillar, docs_dir=docs_dir))

    matched = sum(r.matched_pairs for r in reports)
    field_totals = {f: 0 for f in ("title", "last_update", "url", "scope", "provisions", "impact", "indicator")}
    for report in reports:
        for fs in report.field_scores:
            field_totals[fs.field] += fs.correct

    all_preds: list[Finding] = []
    all_golds: list[GoldRecord] = []
    for country in _FOCUS:
        for pillar in (6, 7):
            all_preds.extend(
                f for f in findings if (f.economy or "").lower() == country.lower() and f.pillar.value == pillar
            )
            all_golds.extend(
                g for g in load_gold_records(docs_dir) if g.country == country and g.pillar_id == pillar
            )
    tp, fp, fn = _discovery_counts(all_preds, all_golds)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    mandatory = ("title", "last_update", "url", "scope", "provisions", "impact")
    return {
        "matched_pairs": matched,
        "discovery_precision": precision,
        "discovery_recall": recall,
        "discovery_f1": f1,
        "mandatory_field_accuracy": {
            field: (field_totals[field] / matched if matched else 0.0) for field in mandatory
        },
        "mean_mandatory_field_accuracy": (
            sum(field_totals[f] for f in mandatory) / (matched * len(mandatory)) if matched else 0.0
        ),
        "per_jurisdiction": [r.to_dict() for r in reports],
    }


def _best_gold_for_pred(pred: Finding, golds: Sequence[GoldRecord]) -> GoldRecord | None:
    """Return the best gold row for a prediction (many preds may share the same gold act)."""
    matches = [g for g in golds if _match_gold(pred, g)]
    if not matches:
        return None
    return max(matches, key=lambda g: act_similarity(pred.title, g.act_name))


def _discovery_counts(
    preds: Sequence[Finding],
    golds: Sequence[GoldRecord],
) -> tuple[int, int, int]:
    """Many-to-one discovery: multiple section findings per gold act URL are all TPs."""
    true_positives = sum(1 for pred in preds if any(_match_gold(pred, g) for g in golds))
    false_positives = len(preds) - true_positives
    false_negatives = sum(1 for gold in golds if not any(_match_gold(pred, gold) for pred in preds))
    return true_positives, false_positives, false_negatives


def collect_matched_pairs(
    findings: list[Finding],
    *,
    docs_dir: str | None = None,
) -> list[tuple[Finding, GoldRecord, dict[str, bool]]]:
    pairs: list[tuple[Finding, GoldRecord, dict[str, bool]]] = []
    for country in _FOCUS:
        for pillar in (6, 7):
            golds = [
                g
                for g in load_gold_records(docs_dir)
                if g.country == country and g.pillar_id == pillar
            ]
            preds = [f for f in findings if (f.economy or "").lower() == country.lower() and f.pillar.value == pillar]
            for pred in preds:
                gold = _best_gold_for_pred(pred, golds)
                if gold is not None:
                    pairs.append((pred, gold, _score_fields(pred, gold)))
    return pairs


def collect_false_positives(
    findings: list[Finding],
    *,
    docs_dir: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Unmatched predictions — discovery false positives for spot-checking."""
    fps: list[dict] = []
    for country in _FOCUS:
        for pillar in (6, 7):
            golds = [
                g
                for g in load_gold_records(docs_dir)
                if g.country == country and g.pillar_id == pillar
            ]
            preds = [f for f in findings if (f.economy or "").lower() == country.lower() and f.pillar.value == pillar]
            unmatched_gold = list(golds)
            for pred in preds:
                matched = any(_match_gold(pred, g) for g in golds)
                if not matched:
                    fps.append(
                        {
                            "country": country,
                            "pillar": pillar,
                            "title": pred.title,
                            "url": pred.url,
                            "indicator": pred.indicator,
                            "provisions_excerpt": _pred_provision_text(pred)[:120],
                        }
                    )
                    if len(fps) >= limit:
                        return fps
    return fps


def evaluate_submission(
    findings: list[Finding],
    *,
    country: str,
    pillar: int,
    docs_dir: str | None = None,
) -> SubmissionEvalReport:
    golds = [
        g
        for g in load_gold_records(docs_dir)
        if g.country == country and g.pillar_id == pillar
    ]
    preds = [f for f in findings if (f.economy or "").lower() == country.lower() and f.pillar.value == pillar]

    field_hits: dict[str, int] = {f: 0 for f in ("title", "last_update", "url", "scope", "provisions", "impact", "indicator")}
    scored = 0
    for pred in preds:
        gold = _best_gold_for_pred(pred, golds)
        if gold is None:
            continue
        scored += 1
        scores = _score_fields(pred, gold)
        for key, ok in scores.items():
            if ok:
                field_hits[key] += 1

    tp, fp, fn = _discovery_counts(preds, golds)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    field_scores = tuple(
        FieldScore(field=k, correct=field_hits[k], total=scored) for k in field_hits
    )

    return SubmissionEvalReport(
        country=country,
        pillar=pillar,
        findings_count=len(preds),
        gold_count=len(golds),
        matched_pairs=scored,
        field_scores=field_scores,
        discovery_precision=precision,
        discovery_recall=recall,
        discovery_f1=f1,
    )


def load_findings_from_queue(raw: list | dict, *, default_country: str = "", default_pillar: int = 6) -> list[Finding]:
    """Load findings from queue JSON (plain array or {provenance, findings} envelope)."""
    from datetime import date as date_type
    from zetarix.domain.entities import Pillar

    if isinstance(raw, dict) and "findings" in raw:
        rows = raw["findings"]
    else:
        rows = raw

    findings: list[Finding] = []
    for row in rows:
        findings.append(
            Finding(
                title=row.get("title", ""),
                last_update=date_type.fromisoformat(row["last_update"]) if row.get("last_update") else None,
                url=row.get("url", ""),
                scope=row.get("scope", ""),
                provisions=row.get("provisions", ""),
                impact=row.get("impact", ""),
                pillar=Pillar(row.get("pillar", default_pillar)),
                indicator=row.get("indicator", ""),
                confidence=float(row.get("confidence", 0.5)),
                economy=row.get("economy", default_country),
                article_section=row.get("article_section", ""),
                verbatim_snippet=row.get("verbatim_snippet", row.get("provisions", "")),
                mapping_rationale=row.get("mapping_rationale", ""),
                notes=row.get("notes", ""),
            )
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate live findings against gold on 6 submission fields.")
    parser.add_argument("--findings-json", required=True, help="JSON array of Finding-like dicts or run output.json envelope")
    parser.add_argument("--country", required=True)
    parser.add_argument("--pillar", type=int, required=True)
    parser.add_argument("--docs-dir", default=None)
    parser.add_argument("--out", default=str(_DEFAULT_REPORT))
    args = parser.parse_args(argv)

    raw = json.loads(Path(args.findings_json).read_text(encoding="utf-8"))
    findings = load_findings_from_queue(raw, default_country=args.country, default_pillar=args.pillar)

    report = evaluate_submission(findings, country=args.country, pillar=args.pillar, docs_dir=args.docs_dir)
    Path(args.out).write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
