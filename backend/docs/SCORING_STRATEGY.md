# Scoring Strategy — how every point is earned

> Traces the published rubric (Q&A 3.1–3.2, 2.3, 5.1) to concrete, measurable
> deliverables. The principle: **never claim a number we cannot reproduce on demand.**
> Each bucket below names the artifact that proves it.

## The pointing system (from the Q&A)

| Stage | Buckets (weights) | Bonus |
| ----- | ----------------- | ----- |
| **1 — Application** | Team expertise 40% · Methodology 30% · Sustainability 30% | +20 pts swappability design |
| **2 — Round 1** (20 Jul) | **Substantive accuracy 40%** · Technical resilience 30% · Architecture 30% | **+20 pts Discovery of new evidence** |
| **3 — Finale** | ~70% = deployment · interface · generalisation · live stress test | +20 pts swappability (live) |

Practicality dominates over novelty (Q&A 2.3): optimise for *"works, cheaply,
repeatably, on unseen jurisdictions."*

---

## The keystone: a real measurement substrate

Everything in Stage 2 — and the calibration that lifts Stage 3 — rests on being able to
score predicted findings against ground truth. That substrate is now in place:

| Module | Role |
| ------ | ---- |
| `core/pipeline/golden_dataset.py` | Parses Round 1/2 `.xlsx` → 225 `GoldRecord`s (Pillars 6 & 7), and the seed CSVs → 477 `ReferenceItem`s (known-evidence baseline). |
| `core/pipeline/scoring.py` | `score(preds, gold)` → precision/recall/F1 (overall + per pillar); `discovery_diff()` → candidate new evidence. |
| `run_validation.py` | Honest CLI scorecard + harness self-check (gold vs gold = F1 1.000). |

Ground truth loaded: **225 mappings · 130 unique acts · 255 reference URLs · 10 countries.**

---

## Stage 2 — point-by-point plan

### Substantive accuracy (40%) — the heaviest bucket
- **Done:** record-matching rule (same pillar + act-name Jaccard ≥ θ *or* shared URL,
  year-insensitive, country-aware), one-to-one F1, per-pillar split. Self-check passes.
- **Next:** wire the extraction pipeline to emit `Finding` rows for the 3 Round-1 countries,
  then `score(findings, gold)` reports the true F1. **No number is published until this runs.**
- **Calibration:** sweep θ (edge threshold) and α (tag-overlap weight) to **maximise F1 on the
  gold set** (GRAPH_PIPELINE Stage 3 — "never hardcode 0.8"). This is a measurable lift, not a guess.

### Technical resilience (30%)
- OCR **< 5% CER** (R17): build a CER harness over a handful of hand-transcribed pages.
- Messy / anti-bot / non-English portals (R19): exercise the `adapters/botting/` compliant-access
  scaffold against a real government portal; record success/failure honestly.
- **Determinism:** fixed seeds + sorted tie-breaks → byte-reproducible graph (already covered by
  `test_pipeline_reproducible.py`); extend the same guarantee to the scorecard.

### Architecture (30%)
- **Swappability demo (also +20 pts):** run the same ports with remote (Claude) and local
  (Ollama Llama 3.1) providers via `adapters/llm/router.py`; show comparable F1 — proof nothing
  breaks on swap (R12).
- **License audit:** every adapter Apache-2.0-compatible. ⚠️ `igraph`/`leidenalg` are GPL —
  keep to NetworkX (BSD) / `python-louvain` (BSD), already flagged in GRAPH_PIPELINE.

### Discovery of new evidence (+20 pts)
- **Done:** `discovery_diff()` flags predicted acts/URLs absent from *both* the gold DB and the
  seed CSVs.
- **Next:** crawl the seed portals → extract findings → diff → a human-verifiable "new evidence"
  list. The +20 is awarded for evidence the provided database does not contain (R20).

---

## Stage 1 & Stage 3 (the "general" coverage)

- **Stage 1 Sustainability/Methodology:** the audit trail (every edge stores its score + basis,
  R6), the Apache-2.0 license posture, and the cost-per-50-page estimate (R21) are the artifacts.
- **Stage 3 generalisation/live stress test:** the calibrated θ/α and the swap demo are exactly
  what a live run on *unseen* countries exercises. Same substrate, no new framework.

---

## Honest status (no fabricated metrics)

| Item | State |
| ---- | ----- |
| Golden dataset + scoring harness | **Done, tested** (19 dedicated tests, 77 suite green) |
| Discovery diff | **Done, tested** |
| Pipeline → `Finding` predictions | **Not wired** — required before any F1 is real |
| θ/α calibration sweep | **Pending** (needs predictions) |
| OCR CER harness | **Not started** |
| Llama swap benchmark | **Not started** |

The previous `run_validation.py` printed placeholder accuracy (`98.4%`, `θ=0.74`). Those were
removed — publishing un-reproducible numbers to UN judges is a credibility risk, not an asset.
