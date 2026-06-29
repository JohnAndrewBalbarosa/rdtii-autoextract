# Department 03 — Platform & Contracts

**Mission:** Own the **seam every other department plugs into** — the ports (interfaces),
the CLI and FastAPI entry points, the 13-column output contract, and the golden-dataset
ground truth. This department changes least and breaks most when changed; treat it as the
constitution.

**Owner:** lead / shared. A change here ripples into all three other departments, so it
requires review.

---

## File structure (what this department owns)

```text
backend/core/ports/                 # ★ The interface contracts (the seam)
├── __init__.py     # DocumentSource, OCREngine, Chunker, VectorStore,
│                   # DocumentExtractorPort, ProvisionExtractor, HtmlFetcherPort,
│                   # LLMProvider, IndicatorClassifier, FindingRepository
├── extraction.py   # SectionExtractor, DocumentGuideProvider, GuidedSectionTagger, TaggingReconciler
├── clustering.py   # SimilarityScorer, CommunityDetector
└── access.py       # AccessObserver, AccessPolicyEvaluator, RetrievalAuditor

backend/app/                        # FastAPI reference adapter (thin, swappable)
└── main.py         # GET /health; pipeline routes wired per sprint

backend/run.py                      # ★ CLI entry: country/pillar/source → CSV/JSON/clusters
backend/run_validation.py           # Stage-2 honest scorecard
backend/core/pipeline/
├── output_emitter.py  # ★ 13-column CSV contract + law-grouped JSON envelope
├── golden_dataset.py  # ★ loads ESCAP Round 1/2 workbooks + seed CSVs → GoldRecord
└── scraper_orchestrator.py # ScraperOrchestrator: extractor + validator wiring
```

---

## Modularity (functional breakdown)

### Module A — Ports (the contracts)
Plain `typing.Protocol` interfaces — **no implementations, no external libs.** They are the
only thing the agnostic `core/` exposes to adapters. Key contracts:

| Port | Method(s) | Implemented by (dept) |
|---|---|---|
| `HtmlFetcherPort` | `fetch(url) -> str` | 01 |
| `DocumentExtractorPort` | `scrape_url(url) -> ParsedDocument` | 01 |
| `ProvisionExtractor` | `extract(doc, pillar) -> list[Finding]` | 02 |
| `SectionExtractor` / `GuidedSectionTagger` / `TaggingReconciler` / `DocumentGuideProvider` | tagging contracts | 02 |
| `SimilarityScorer` / `CommunityDetector` | graph contracts | 02 |
| `LLMProvider` | `complete(prompt, schema, agent_profile) -> dict` | 02 |
| `DocumentSource` / `OCREngine` / `Chunker` / `VectorStore` / `IndicatorClassifier` / `FindingRepository` | future/extensible | (open) |
| `AccessObserver` / `AccessPolicyEvaluator` / `RetrievalAuditor` | compliance contracts | 02 (compliant_retrieval) |

> **A swap = changing one factory/config entry.** Adding a method to a port is a
> cross-department breaking change — coordinate it.

### Module B — Output contract (`output_emitter.py`)
The single source of truth for the deliverable shape. **`CSV_COLUMNS`** is the immutable
13-column template required by ESCAP:

```
Economy · Law Name · Law Number / Ref · Last Amended · Indicator ID ·
Article / Section · Discovery Tag · Location Reference · Verbatim Snippet ·
Mapping Rationale · Source URL · Confidence · Notes
```

Plus a **law-grouped JSON envelope** (`provisions[]` per law, with model_version,
ocr_quality_cer, processing_time). `write_csv` / `write_json` are the only writers — no
other department formats output.

### Module C — CLI entry (`run.py`)
The orchestrator that wires concrete adapters to the pipeline:
- Args: `--country` (with aliases AU/SG/MY/CN/IN/ID/LA/MN/RU/TH + full names),
  `--pillar` (6|7), `--source` (`gold` offline | `live` crawl), `--out-dir`, `--limit`,
  `--docs-dir`.
- `--source gold`: builds Findings from `golden_dataset`, tags KNOWN.
- `--source live`: BFS-crawls seed URLs via `TransportFactory` (Dept 01) → extracts via
  `FallbackProvisionExtractor(TagMatch → Mock)` (Dept 02) → tags discovery → emits.
- Writes `output.csv`, `output.json`, `clusters.json`, `logs/run.log`.

### Module D — Ground truth (`golden_dataset.py`)
Loads the ESCAP **Round 1 & 2** Excel workbooks (one sheet per economy) into immutable
**`GoldRecord`** tuples (country, pillar, indicator, act, coverage, impact, timeframe,
URLs), filtered to Pillars 6 & 7. Loads seed CSVs into **`ReferenceItem`** for the
discovery baseline (R20). This feeds Dept 02's scoring harness.

### Module E — Reference web adapter (`app/main.py`) + `scraper_orchestrator`
FastAPI is the *reference* HTTP shell (currently `GET /health`; pipeline routes added per
sprint). `ScraperOrchestrator` shows the canonical wiring: `DocumentExtractorPort` +
`DocumentComplianceValidator` → validated `ParsedDocument`s. Swapping FastAPI → Litestar,
or the CLI → a queue worker, touches only this department.

---

## Port seams (this department IS the seam)

```
        Dept 01 (scraper)            Dept 02 (pipeline/eval)         Dept 04 (frontend)
             │ implements                  │ implements                   │ consumes
             ▼                             ▼                              ▼
   HtmlFetcherPort / DocumentExtractorPort │ ProvisionExtractor /     (its own TS port:
                                            │ SimilarityScorer /        FindingsRepository,
                                            │ CommunityDetector /       mirrors this contract
                                            │ LLMProvider               over HTTP later)
             └──────────── all defined in backend/core/ports/ ───────────┘
                          run.py wires concrete adapters → pipeline
                          output_emitter enforces the 13-column deliverable
                          golden_dataset provides ground truth to scoring
```

---

## Verify

```powershell
cd backend
python -m pytest -q tests/test_output_emitter.py tests/test_golden_dataset.py `
  tests/test_run_cli.py tests/test_run_live_offline.py tests/test_entities.py
python run.py --country SG --pillar 6 --source gold --out-dir ./out
```

---

## Reverse-prompting hooks (task seeds for delegation)

1. **Add a FastAPI route** — *"In `backend/app/main.py`, expose `GET /findings` that calls
   the same path as `run.py --source gold`. Keep all domain logic in `core/` — the route is
   a thin mapper only. Add a test under `backend/tests/`."*
2. **Extend the CLI** — *"Add `--format` to `run.py` without changing `output_emitter`'s
   column order. Cover with `tests/test_run_cli.py`."*
3. **New economy data** — *"Wire a new sheet/economy in `golden_dataset.py`. It must return
   immutable `GoldRecord`s filtered to Pillars 6/7 and keep `tests/test_golden_dataset.py`
   green."*
4. **Port change (high-risk)** — *"Proposal to add a method to `<Port>`. First list every
   implementer across Dept 01/02/04, update all of them in one PR, and keep the full suite
   (`python -m pytest -q`) green. This requires lead review."*

**Boundary reminder:** changes here are cross-cutting. **Never** add a concrete
dependency (fastapi/networkx/playwright/vendor SDK) into `core/ports/` or `core/domain/`.
