"""FastAPI routes for the training feedback loop (Phase 5)."""

from __future__ import annotations

import os
import threading
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from zetarix.pretrain.dataset.build import (
    build_datasets,
    collect_examples,
    count_examples,
    count_real_examples,
)
from zetarix.pretrain.dataset.review_log import append_review_decision, decision_from_finding_payload, load_review_decisions
from zetarix.pretrain.paths import TRAINING_DATA_DIR

router = APIRouter(prefix="/training", tags=["training"])

_DEBOUNCE_SEC = float(os.environ.get("ZETARIX_REBUILD_DEBOUNCE_SEC", "30"))
_last_rebuild_at = 0.0
_rebuild_lock = threading.Lock()
_rebuild_pending = False


def _schedule_rebuild(docs_dir: str | None = None) -> dict:
    """Debounced dataset rebuild — coalesces rapid verify/reject bursts."""
    global _last_rebuild_at, _rebuild_pending

    now = time.monotonic()
    with _rebuild_lock:
        elapsed = now - _last_rebuild_at
        if elapsed < _DEBOUNCE_SEC:
            _rebuild_pending = True
            return {
                "status": "debounced",
                "rebuild_in_sec": round(_DEBOUNCE_SEC - elapsed, 1),
            }
        _last_rebuild_at = now
        _rebuild_pending = False

    counts = build_datasets(docs_dir=docs_dir)
    return {
        "status": "rebuilt",
        "law_interpreter_total": counts.law_interpreter_total,
        "tag_generator_total": counts.tag_generator_total,
        "positives": counts.positives,
        "negatives": counts.negatives,
        "enough_for_finetune": counts.enough_for_finetune(),
        "report": str(TRAINING_DATA_DIR / "dataset_report.txt"),
    }


class ReviewDecisionRequest(BaseModel):
    id: str
    review_status: str = Field(pattern="^(verified|rejected)$")
    jurisdiction: str
    pillar: int
    title: str = ""
    scope: str = ""
    provisions: str = ""
    impact: str = ""
    indicator: str = ""
    indicator_label: str = ""
    document_title: str = ""
    article_number: str = ""
    language: str = "en"


@router.get("/stats")
def get_training_stats() -> dict:
    """Dataset and review-log counts for the training feedback loop."""
    reviews = load_review_decisions()
    law, tag = collect_examples()
    counts = count_examples(law, tag)
    real = count_real_examples(law, tag)
    return {
        "review_decisions": len(reviews),
        "verified": sum(1 for r in reviews if r.review_status == "verified"),
        "rejected": sum(1 for r in reviews if r.review_status == "rejected"),
        "law_interpreter_total": counts.law_interpreter_total,
        "tag_generator_total": counts.tag_generator_total,
        "enough_for_finetune": counts.enough_for_finetune(),
        "focus_jurisdictions": counts.focus_jurisdiction_totals,
        "real_provision_examples": real,
        "real_provision_total": {
            "law_interpreter": sum(v["law_interpreter"] for v in real.values()),
            "tag_generator": sum(v["tag_generator"] for v in real.values()),
        },
    }


@router.post("/review-decision")
def post_review_decision(body: ReviewDecisionRequest) -> dict[str, str]:
    """Append a verify/reject action to the training review log."""
    try:
        decision = decision_from_finding_payload(body.model_dump())
        append_review_decision(decision)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rebuild = _schedule_rebuild()
    return {"status": "appended", "finding_id": body.id, "rebuild": rebuild["status"]}


@router.post("/rebuild-dataset")
def post_rebuild_dataset(docs_dir: str | None = None) -> dict:
    """Rebuild training JSONL + splits after new review decisions (Phases 1 + 5)."""
    return _schedule_rebuild(docs_dir=docs_dir)
