"""Per-record accuracy scoring + discovery diff for Stage 2 (Substantive accuracy 40%).

This is the measurement substrate the whole Stage-2 score rests on:

* ``score()``  — precision / recall / F1 of predicted ``Finding`` rows against the
  ``GoldRecord`` ground truth, with a defensible record-matching rule. This is the 40%
  bucket *and* the objective the graph threshold θ / weight α are calibrated against.
* ``discovery_diff()`` — predicted findings that match *no* known act in the gold DB or
  the seed CSVs: candidate "new evidence beyond the provided database" (R20, +20 pts).

Dependency-free on purpose (no rapidfuzz): matching uses token-set Jaccard so the result
is reproducible byte-for-byte and easy to defend to judges. No web/LLM imports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.domain.entities import Finding
from core.domain.indicator_codes import to_canonical
from core.pipeline.golden_dataset import GoldRecord, ReferenceItem

# Tuned defaults; calibrate against the gold data rather than trusting these blindly.
DEFAULT_ACT_THRESHOLD = 0.6

_WORD_RE = re.compile(r"[a-z0-9]+")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


@dataclass(frozen=True)
class MatchItem:
    """The minimal shape scoring needs — both gold and predicted rows reduce to this."""

    country: str
    pillar_id: int
    indicator_id: str
    act_name: str
    urls: tuple[str, ...]


@dataclass(frozen=True)
class ScoreReport:
    """Precision / recall / F1 with the raw counts behind them, plus a per-pillar split."""

    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    per_pillar: dict[int, "ScoreReport"] = None  # type: ignore[assignment]


def _tokens(text: str) -> frozenset[str]:
    return frozenset(_WORD_RE.findall(text.lower()))


def normalize_act(name: str) -> str:
    """Lowercase, collapse whitespace, drop punctuation — stable act key."""
    return " ".join(_WORD_RE.findall(name.lower()))


def normalize_url(url: str) -> str:
    """Scheme/case/trailing-slash-insensitive host+path key for URL overlap."""
    cleaned = url.strip().lower()
    cleaned = re.sub(r"^https?://", "", cleaned)
    cleaned = re.sub(r"^www\.", "", cleaned)
    cleaned = cleaned.split("?", 1)[0].split("#", 1)[0]
    return cleaned.rstrip("/")


def act_similarity(a: str, b: str) -> float:
    """Token-set Jaccard over act names, year-insensitive. 0.0–1.0."""
    ta = _tokens(_YEAR_RE.sub("", a))
    tb = _tokens(_YEAR_RE.sub("", b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _url_overlap(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    na = {normalize_url(u) for u in a if u}
    nb = {normalize_url(u) for u in b if u}
    return bool(na & nb)


def _canonical_indicator(code: str) -> str:
    """Best-effort canonicalisation (``6.1`` / ``P6-I1`` → ``P6-I1``).

    Indicator format must not gate matching, so a malformed code degrades to its raw
    (whitespace-stripped) value rather than raising — the pillar/act/url rule still applies.
    """
    try:
        return to_canonical(code)
    except ValueError:
        return code.strip() if isinstance(code, str) else ""


def finding_to_match_item(finding: Finding) -> MatchItem:
    return MatchItem(
        country=_economy_of(finding),
        pillar_id=finding.pillar.value,
        indicator_id=_canonical_indicator(finding.indicator),
        act_name=finding.title,
        urls=(finding.url,) if finding.url else (),
    )


def _economy_of(finding: Finding) -> str:
    """Prefer the Round-1 ``economy`` field; fall back to a legacy ``country`` attr."""
    economy = getattr(finding, "economy", "") or ""
    if economy:
        return economy
    return getattr(finding, "country", "") or ""


def _pillar_from_indicator(code: str) -> int:
    """'P6-I1' / '6.1' -> 6. 0 when it cannot be determined (won't match any gold pillar)."""
    canonical = _canonical_indicator(code)
    match = re.match(r"P(\d+)", canonical)
    return int(match.group(1)) if match else 0


def match_items_from_json_objects(objects: list[dict]) -> list[MatchItem]:
    """Convert a live ``output.json`` law-grouped envelope into scorable ``MatchItem`` rows.

    Bridges the pipeline's emitted predictions to the scorer so live extraction accuracy can
    be measured against gold (Issue #7). Envelope shape: a list of laws, each with
    ``economy`` / ``law_name`` and a ``provisions`` list of ``{indicator_id, source_url, …}``.
    """
    items: list[MatchItem] = []
    for law in objects or []:
        economy = (law.get("economy") or "").strip()
        name = (law.get("law_name") or "").strip()
        for provision in law.get("provisions", []) or []:
            indicator = provision.get("indicator_id") or ""
            url = provision.get("source_url") or ""
            items.append(
                MatchItem(
                    country=economy,
                    pillar_id=_pillar_from_indicator(indicator),
                    indicator_id=_canonical_indicator(indicator),
                    act_name=name,
                    urls=(url,) if url else (),
                )
            )
    return items


def gold_to_match_item(record: GoldRecord) -> MatchItem:
    return MatchItem(
        country=record.country,
        pillar_id=record.pillar_id,
        indicator_id=_canonical_indicator(record.indicator_id),
        act_name=record.act_name,
        urls=record.urls,
    )


def is_match(pred: MatchItem, gold: MatchItem, act_threshold: float = DEFAULT_ACT_THRESHOLD) -> bool:
    """A predicted row matches gold only when the indicator label is also correct.

    Within the same country/pillar/indicator, either close act names or a shared URL can
    establish evidence identity. Requiring the indicator prevents a model from scoring
    correct for finding the right law but assigning the wrong RDTII label.
    """
    if pred.pillar_id != gold.pillar_id:
        return False
    if _canonical_indicator(pred.indicator_id) != _canonical_indicator(gold.indicator_id):
        return False
    if pred.country and gold.country and pred.country.lower() != gold.country.lower():
        return False
    if _url_overlap(pred.urls, gold.urls):
        return True
    return act_similarity(pred.act_name, gold.act_name) >= act_threshold


def _score_pairs(
    preds: list[MatchItem], golds: list[MatchItem], act_threshold: float
) -> tuple[int, int, int]:
    """Greedy one-to-one matching → (true_pos, false_pos, false_neg)."""
    unmatched_gold = list(golds)
    true_positives = 0
    for pred in preds:
        for i, gold in enumerate(unmatched_gold):
            if is_match(pred, gold, act_threshold):
                true_positives += 1
                unmatched_gold.pop(i)
                break
    false_positives = len(preds) - true_positives
    false_negatives = len(unmatched_gold)
    return true_positives, false_positives, false_negatives


def _report(tp: int, fp: int, fn: int, per_pillar: dict[int, ScoreReport] | None = None) -> ScoreReport:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return ScoreReport(tp, fp, fn, precision, recall, f1, per_pillar)


def score(
    predictions: list[Finding] | list[MatchItem],
    gold: list[GoldRecord] | list[MatchItem],
    act_threshold: float = DEFAULT_ACT_THRESHOLD,
) -> ScoreReport:
    """Precision / recall / F1 of predictions against gold, overall and per pillar."""
    preds = [p if isinstance(p, MatchItem) else finding_to_match_item(p) for p in predictions]
    golds = [g if isinstance(g, MatchItem) else gold_to_match_item(g) for g in gold]

    per_pillar: dict[int, ScoreReport] = {}
    for pillar_id in sorted({g.pillar_id for g in golds} | {p.pillar_id for p in preds}):
        counts = _score_pairs(
            [p for p in preds if p.pillar_id == pillar_id],
            [g for g in golds if g.pillar_id == pillar_id],
            act_threshold,
        )
        per_pillar[pillar_id] = _report(*counts)

    overall = _score_pairs(preds, golds, act_threshold)
    return _report(*overall, per_pillar=per_pillar)


def discovery_diff(
    predictions: list[Finding] | list[MatchItem],
    gold: list[GoldRecord] | list[MatchItem],
    references: tuple[ReferenceItem, ...] = (),
    act_threshold: float = DEFAULT_ACT_THRESHOLD,
) -> list[MatchItem]:
    """Return predicted rows that match no known act in the gold DB or the seed CSVs.

    These are candidate *new evidence* (R20). A prediction is "known" if it matches a
    gold record, or shares a normalised URL / close act name with a reference item.
    """
    preds = [p if isinstance(p, MatchItem) else finding_to_match_item(p) for p in predictions]
    golds = [g if isinstance(g, MatchItem) else gold_to_match_item(g) for g in gold]

    ref_urls = {normalize_url(item.url) for item in references if item.url}
    ref_acts = [normalize_act(item.act_name) for item in references if item.act_name]

    novel: list[MatchItem] = []
    for pred in preds:
        if any(is_match(pred, gold_item, act_threshold) for gold_item in golds):
            continue
        if {normalize_url(u) for u in pred.urls if u} & ref_urls:
            continue
        pred_act = normalize_act(pred.act_name)
        if any(act_similarity(pred.act_name, ref) >= act_threshold for ref in ref_acts):
            continue
        if pred_act and pred_act in ref_acts:
            continue
        novel.append(pred)
    return novel
