"""Append-only review decision log for the training feedback loop."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from zetarix.pretrain.dataset.schemas import ReviewDecision
from zetarix.pretrain.paths import REVIEW_LOG_PATH

_DEFAULT_LOG = REVIEW_LOG_PATH


def default_review_log_path() -> Path:
    return _DEFAULT_LOG


def append_review_decision(decision: ReviewDecision, log_path: Path | str | None = None) -> None:
    """Append one verify/reject decision to the training review log."""
    path = Path(log_path) if log_path else default_review_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = decision.to_dict()
    if not payload.get("timestamp"):
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_review_decisions(log_path: Path | str | None = None) -> tuple[ReviewDecision, ...]:
    """Load all review decisions from the JSONL log (missing file → empty)."""
    path = Path(log_path) if log_path else default_review_log_path()
    if not path.exists():
        return ()
    decisions: list[ReviewDecision] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            decisions.append(ReviewDecision.from_dict(json.loads(line)))
    return tuple(decisions)


def decision_from_finding_payload(payload: dict) -> ReviewDecision:
    """Build a ReviewDecision from a review-UI finding dict (camelCase or snake_case)."""

    def _get(*keys: str, default: str = "") -> str:
        for key in keys:
            if key in payload and payload[key] is not None:
                return str(payload[key])
        return default

    status = _get("reviewStatus", "review_status")
    if status not in ("verified", "rejected"):
        raise ValueError(f"review decision must be verified or rejected, got {status!r}")

    return ReviewDecision(
        finding_id=_get("id", "finding_id"),
        review_status=status,  # type: ignore[arg-type]
        jurisdiction=_get("jurisdiction"),
        pillar=int(payload.get("pillar") or payload.get("Pillar") or 0),
        title=_get("title"),
        scope=_get("scope"),
        provisions=_get("provisions"),
        impact=_get("impact"),
        indicator=_get("indicator"),
        indicator_label=_get("indicatorLabel", "indicator_label"),
        document_title=_get("documentTitle", "document_title"),
        article_number=_get("articleNumber", "article_number"),
        language=_get("language", default="en"),
    )
