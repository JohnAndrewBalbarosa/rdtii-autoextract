"""Central paths for pre-training data, splits, and artifacts."""

from __future__ import annotations

import os
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = _BACKEND_ROOT.parent

TRAINING_DATA_DIR = Path(os.environ.get("ZETARIX_TRAINING_DATA", _BACKEND_ROOT / "data" / "training"))
SPLITS_DIR = Path(os.environ.get("ZETARIX_TRAINING_SPLITS", TRAINING_DATA_DIR / "splits"))
REVIEW_LOG_PATH = TRAINING_DATA_DIR / "review_decisions.jsonl"
LIVE_FINDINGS_QUEUE_PATH = TRAINING_DATA_DIR / "live_findings_queue.json"
EVAL_REPORT_PATH = TRAINING_DATA_DIR / "eval_report.json"
SUBMISSION_EVAL_REPORT_PATH = TRAINING_DATA_DIR / "submission_eval_report.json"
DOCS_DIR = Path(os.environ.get("ZETARIX_DOCS_DIR", _REPO_ROOT / "docs"))
