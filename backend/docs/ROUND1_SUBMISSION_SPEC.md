# Round 1 Submission Spec — verified from "Hackathon Overview – Dr. Witada A." (deck)

> Source: `docs/Hackathon Overview—Dr.Witada A.pdf`, cross-checked page by page (not paraphrased).
> Round 1 due **20 July 2026 23:59 GMT+7**. Assessed on **Australia, Singapore, Malaysia only**
> (regardless of broader coverage). Pillars 6 & 7, 10 indicators (P6-I1…P6-I5, P7-I1…P7-I5).

## The 5 deliverables (deck p.11 — "All required. No exceptions.")

| # | Deliverable | Key requirement | Format |
| - | ----------- | --------------- | ------ |
| 1 | **Functional Prototype** | Task 1 (crawl/retrieve) + Task 2 (extract/map) end-to-end, **no manual steps**; Quick Start README; *"stress test with the reviewer API / Script"* | code repo |
| 2 | **Structured Output File** | the extraction results | JSON + CSV |
| 3 | **Technical Pitch Deck** | problem–solution fit; Task 1 & Task 2 logic | slides |
| 4 | **Screen-recording Walkthrough** | engine processing a **scanned/image PDF** → correct citations | video ≤10 min |
| 5 | **Live Demo + Interview (3 Aug)** | engine runs and produces output in real time | live event |

Items 1–4 are uploaded by 20 Jul (the email's "4 items"); #5 is the live event.

## Reviewer interface / "runs" contract (deck p.12)

A reviewer hands the engine a **country + topic**; it returns CSV+JSON with verifiable
citations, **no manual steps**, works on text **and** scanned PDFs, handles unanticipated input
(misspelt country, edge cases), with a switchable open-source fallback if a commercial API is used.

**Mandated CLI (README must show):**
```
python run.py --country SG --pillar 6   →   output.csv, output.json, logs/
```
README mandatory sections: name+desc · Setup (3–5 lines) · Run (one command) · Outputs ·
**Pinned versions** (LLM/OCR/libs — no "latest") · Open-source fallback.

> The "reviewer API / Script" that stress-tests submissions is referenced but **no spec is in the
> deck** — it ships with the submission portal. We build to the `run.py --country --pillar` contract.

## Required OUTPUT structure (deck p.14) — the output contract

**CSV (primary).** `Req` = required.

| Column | Purpose | Req |
| ------ | ------- | --- |
| Economy | country analysed | **Yes** |
| Law Name | full official statute name + year | **Yes** |
| Law Number/Ref | official act/law number | opt |
| Last Amended | year of most recent amendment | **Yes** |
| Indicator ID | RDTII code, e.g. **`P6-I1`** | **Yes** |
| Article / Section | exact article + paragraph | **Yes** |
| Discovery Tag | **`NEW`** (independent find) / **`KNOWN`** (sample kit) | **Yes** |
| Location Ref. | PDF: page no. \| HTML: URL anchor/path | opt |
| Verbatim Snippet | exact quoted text — **no paraphrasing** | **Yes** |
| Mapping Rationale | why it maps to this indicator (≤300 chars) | opt |
| Source URL | direct URL to law on official portal | **Yes** |
| Confidence | model certainty 0.00–1.00 | opt |
| Notes | OCR issues, partial doc, bilingual | opt |

**JSON (supplementary)** adds: `source_pdf_path`, `ocr_quality_cer`, `processing_time`,
`model_version`, `provisions[]` (per-row), `raw_context` (surrounding text for human review).

Strong-row example (deck p.15): Thailand PDPA 2019, `P6-I1`, `Section 26(2)`, Discovery Tag
`NEW`, verbatim snippet, Confidence 0.93.

## Scoring (deck p.5 + p.8 sub-points)

- **40% Substantive Accuracy** — framework alignment (provisions→indicators), **discovery of new
  evidence** (major differentiator), **citation fidelity** (exact article+paragraph; paraphrase =
  point deduction).
- **30% Technical Resilience** — **Live Portal Crawling 10 pts** (⚠️ pre-downloaded PDFs = **0 pts**),
  **OCR 10 pts** (<5% error), end-to-end (no manual steps).
- **30% Architecture** — **Modular Backend 15 pts** (swap LLM/OCR by config, not rewrite),
  **Audit Trail 15 pts** (verbatim snippet in **every** row), cost-efficiency.
- Differentiator: handling **HTML sources** (harder than PDF) as well as PDF.

## How our current code maps + gaps

| Rubric item | Our state |
| ----------- | --------- |
| Live crawling 10pts | ✅ scraping + proxy rotation + `ProxyPoolBroker` (`docs/SCRAPING_STRATEGY.md`); PDF fetch+extract verified |
| Modular backend 15pts | ✅ ports/adapters + LLM router (model-agnostic) |
| Substantive accuracy 40% | ✅ F1 harness + golden DB (`docs/SCORING_STRATEGY.md`); ⚠️ needs **indicator format map `P6-I1` ↔ `6.1`** |
| Discovery of new evidence | ✅ `discovery_diff` → emit as **Discovery Tag NEW/KNOWN** |
| Audit trail 15pts | ⚠️ `Finding` lacks a **Verbatim Snippet** field — required in every row |
| OCR <5% CER 10pts | ❌ no CER measurement harness yet |
| Output file (CSV/JSON) | ❌ no emitter mapping `Finding` → the p.14 schema |
| `run.py --country --pillar` CLI | ❌ not built — this is the reviewer contract |

### Concrete Round-1 gaps to close
1. **Output emitter**: `Finding` → exact CSV (p.14) + JSON (p.15) schema, with Discovery Tag + Verbatim Snippet.
2. **`run.py --country XX --pillar N`** CLI (crawl→extract→map→emit, no manual steps) + Quick Start README.
3. **Indicator format mapping** `P6-I1` ↔ `6.1` in scoring/golden_dataset.
4. **OCR CER harness** (<5%).
5. Extend `Finding` with `verbatim_snippet`, `article_section`, `discovery_tag`, `law_number`, `economy`.
