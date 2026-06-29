"""FastAPI reference backend — thin HTTP layer over the framework-agnostic core.

This adapter contains NO domain logic. It maps HTTP <-> core use-cases so the
backend framework stays swappable (R12, R16). Replacing FastAPI with Litestar/Flask
touches only this package, never core/.
"""

from __future__ import annotations

import hashlib
import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Make `from core...` / `from run...` resolve when uvicorn launches `app.main:app`.
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from core.domain.entities import Finding, ReviewStatus  # noqa: E402
from core.domain.indicator_definitions import INDICATOR_TAGS  # noqa: E402
from core.pipeline.golden_dataset import load_gold_records  # noqa: E402
from core.pipeline.scoring import (  # noqa: E402
    ScoreReport,
    match_items_from_json_objects,
    score,
)
from run import build_gold_findings, resolve_country, tag_discovery  # noqa: E402

# Countries inside the current Round-1 scoring scope; used when no country is given.
_SCORING_SCOPE = ("Singapore", "Australia", "Malaysia")
_PILLARS = (6, 7)

# In-memory overlay of human review decisions, keyed by synthetic finding id. The gold
# source is read-only; this lets the reviewer UI persist Accept/Reject within a process
# without a database. Swap for a FindingRepository adapter when storage is wired.
_REVIEW_OVERLAY: dict[str, ReviewStatus] = {}

app = FastAPI(
    title="RDTII Trade Regulatory Analysis Engine",
    version="0.1.0",
    description="Automates ~80% of the ESCAP RDTII workflow: search -> retrieve -> describe.",
)

# Dev-friendly CORS so the Next.js reviewer UI (localhost:3000) can call this API.
# Tighten ZETARIX_CORS_ORIGINS (comma-separated) for any non-local deployment.
_origins = os.environ.get("ZETARIX_CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["GET", "PATCH"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for self-hosted deployments (R16)."""
    return {"status": "ok"}


def _finding_id(f: Finding) -> str:
    """Stable synthetic id for a gold Finding (it has no natural primary key)."""
    raw = f"{f.economy}|{f.pillar.value}|{f.indicator}|{f.article_section}|{f.url}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _to_view(f: Finding) -> dict[str, object]:
    """Map a domain Finding to the frontend `Finding` shape (camelCase). Presentation
    mapping only — no business logic."""
    fid = _finding_id(f)
    status = _REVIEW_OVERLAY.get(fid, f.review_status)
    return {
        "id": fid,
        "title": f.title,
        "lastUpdate": f.last_update.isoformat() if f.last_update else None,
        "url": f.url,
        "scope": f.scope,
        "provisions": f.provisions,
        "impact": f.impact,
        "pillar": f.pillar.value,
        "indicator": f.indicator,
        "indicatorLabel": f.mapping_rationale[:80] if f.mapping_rationale else "",
        "confidence": round(f.confidence, 2),
        "reviewStatus": status.value,
        "jurisdiction": f.economy,
        "documentTitle": f.title,
        "articleNumber": f.article_section,
        "language": "en",
    }


def _collect(country: str | None, pillar: int | None) -> list[Finding]:
    countries = [resolve_country(country)] if country else list(_SCORING_SCOPE)
    if country and countries[0] is None:
        raise HTTPException(status_code=400, detail=f"Unknown country: {country!r}")
    pillars = [pillar] if pillar else list(_PILLARS)
    out: list[Finding] = []
    for c in countries:
        if c is None:
            continue
        for p in pillars:
            out.extend(tag_discovery(build_gold_findings(c, p)))
    return out


@app.get("/findings")
def list_findings(country: str | None = None, pillar: int | None = None) -> list[dict[str, object]]:
    """Reviewer feed: gold findings as the frontend `Finding` shape.

    Optional `country` (alias or full name) and `pillar` (6|7) narrow the set; both
    default to the current Round-1 scoring scope (SG/AU/MY, pillars 6 & 7).
    """
    return [_to_view(f) for f in _collect(country, pillar)]


_GOLD_CACHE: list | None = None


def _gold():
    global _GOLD_CACHE
    if _GOLD_CACHE is None:
        _GOLD_CACHE = list(load_gold_records())
    return _GOLD_CACHE


@app.get("/economies")
def list_economies() -> list[str]:
    """Distinct economies present in the golden dataset (thin read over core)."""
    return sorted({r.country for r in _gold() if r.country})


@app.get("/indicators")
def list_indicators(pillar: int | None = None) -> list[str]:
    """RDTII indicator codes (canonical P6-I1 form), optionally filtered by pillar."""
    codes = sorted(INDICATOR_TAGS.keys())
    if pillar is not None:
        codes = [c for c in codes if c.startswith(f"P{pillar}-")]
    return codes


def _report_to_dict(report: ScoreReport) -> dict[str, object]:
    return {
        "true_positives": report.true_positives,
        "false_positives": report.false_positives,
        "false_negatives": report.false_negatives,
        "precision": round(report.precision, 4),
        "recall": round(report.recall, 4),
        "f1": round(report.f1, 4),
        "per_pillar": {
            str(pid): _report_to_dict(sub) for pid, sub in (report.per_pillar or {}).items()
        }
        if report.per_pillar
        else None,
    }


@app.post("/score")
def score_predictions(payload: list[dict]) -> dict[str, object]:
    """Score predicted findings (live output.json envelope) against gold — real F1 (#7).

    Body: the law-grouped envelope `[{economy, law_name, provisions:[{indicator_id, source_url}]}]`.
    """
    preds = match_items_from_json_objects(payload)
    return _report_to_dict(score(preds, _gold()))


@app.patch("/findings/{finding_id}/review")
def set_review(finding_id: str, status: str) -> dict[str, str]:
    """Persist a human review decision (pending|verified|rejected) in the process overlay."""
    try:
        parsed = ReviewStatus(status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status!r}") from exc
    _REVIEW_OVERLAY[finding_id] = parsed
    return {"id": finding_id, "reviewStatus": parsed.value}
