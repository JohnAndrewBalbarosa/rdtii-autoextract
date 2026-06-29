# Zetarix — Delegation Backlog

The single to-do list for delegating work, grouped by [department](README.md). Each open
task names a suggested owner and flags whether a **human-in-the-loop (HITL)** checkpoint is
required before the result can be trusted (model accuracy, legal mapping, live-site
behaviour — never auto-merged on the model's say-so).

Legend: ✅ done · 🔄 in progress / partial · ⬜ not started · 🧑‍⚖️ HITL gate required.

---

## ✅ Done (shipped & validated)

- ✅ Ports & adapters core; nothing in `core/` imports a concrete adapter.
- ✅ Scraper stack: L4 transport (HTTP + Playwright + factory + proxies), L6 DOM cleaning
  with anchors/breadcrumbs, L7 `PipelineAdapter`, lazy-load scroll-settle.
- ✅ Site scaffolds for the scoring scope: `sso.agc.gov.sg`, `pdpc.gov.sg`, `pdp.gov.my`,
  `homeaffairs.gov.au`, `legislation.gov.au`.
- ✅ Golden dataset loader (ESCAP Round 1 & 2 workbooks, 225 Pillar 6/7 records, 10 economies).
- ✅ **F1 scoring harness** (deterministic precision/recall/F1 vs gold; per-pillar; discovery diff).
- ✅ 13-column output contract (CSV) + law-grouped JSON envelope.
- ✅ Deterministic extraction: tagmatch (Set-Trie) + structural + mock + fallback; real snippets.
- ✅ Concept graph: IDF-weighted Jaccard edges + seed-fixed Louvain communities + JSON artifact.
- ✅ CLI `run.py` (gold + live paths, country aliases, cluster artifact).
- ✅ Reviewer UI console (Next.js): findings table, filters, summary stats, accept/reject (mock data).
- ✅ Backend test suite green (303 passing at last doc update).
- ✅ Docs: department handbook + per-folder READMEs with diagrams.
- ✅ `GET /findings` + `PATCH /findings/{id}/review` REST endpoint + frontend REST adapter.

---

## ⬜ Open — Department 01: Scraper (`zx-scraper`)

- ⬜ **Fix sectioning-collapse bug** — HTML pages collapse to 1 section (grouping splits only
  on h1–h4); breaks Location Reference. 🧑‍⚖️ verify on real SG/AU/MY pages.
- ⬜ **Live-site validation** of all 5 scaffolds against current production HTML (selectors drift). 🧑‍⚖️
- ⬜ **OCR adapter** — wire a real `OCREngine` (Tesseract/PaddleOCR) behind the port; meet <5% CER
  via `ocr_cer.py`. 🧑‍⚖️ spot-check OCR output vs source.
- ⬜ **Translation step** — non-English → English routing for non-EN jurisdictions.
- ⬜ Proxy hardening for rate-limited portals under live stress.

## ⬜ Open — Department 02: Pipeline & Eval (`zx-pipeline`)

- 🔄 **Live extraction accuracy not wired** — `run_validation.py` notes pipeline accuracy is not
  yet measured end-to-end; only gold-vs-gold self-check (F1=1.0) runs today. Wire predictions →
  scoring on live crawl output. 🧑‍⚖️ reviewer confirms sampled rows.
- ⬜ **MODEL TRAINING** — fine-tune the Pillar 6/7 sub-indicator classifier on the RDTII taxonomy;
  publish weights in-repo. 🧑‍⚖️ accuracy gate + legal-mapping review before adoption.
- ⬜ **LLM providers** — implement `remote_provider` (Claude/GPT) and `local_provider` (Llama via
  Ollama); `LLMRouter.from_env()` swap. 🧑‍⚖️ validate structured output vs schema.
- ⬜ **Guided tagging with a real LLM tagger** (currently deterministic only). 🧑‍⚖️
- ⬜ **RAG / vector store** adapter (pgvector/Chroma) behind `VectorStore` port.
- ⬜ **Captioning** (SigLIP-style) for scanned / visually-laid-out sections.
- ⬜ Raise F1 per under-recalled indicator by tuning `indicator_definitions.py`. 🧑‍⚖️

## ⬜ Open — Department 03: Platform & Contracts (lead-owned)

- 🔄 **FastAPI pipeline routes** beyond `/findings` (discover → retrieve → ocr → extract → review).
- ⬜ **Persist review decisions** — replace the in-memory overlay with a real `FindingRepository`
  (DB) so HITL verdicts survive restarts. 🧑‍⚖️ this IS the human-in-the-loop record of truth.
- ⬜ **Docker / docker-compose** (api + web + postgres/pgvector) for self-hosting.
- ⬜ Cost metering per 50-page doc (R21) once LLM is wired.
- ⬜ More economies in `golden_dataset` beyond SG/AU/MY for finale readiness.

## ⬜ Open — Department 04: Frontend / Reviewer (`zx-frontend`)

- ⬜ **F1 / coverage panel** in `SummaryStats` fed by backend scoring.
- ⬜ **Edit action** on `FindingRow` (currently Accept/Reject only) + re-queue flagged rows. 🧑‍⚖️
- ⬜ **Audit deep-link** — jump to the exact article anchor / highlighted span in source.
- ⬜ CSV/Excel export from the UI.
- ⬜ E2E tests (Playwright) for the review flow.

---

## How to pick up a task

1. Find the task here and its owning department README (component diagram + boundaries).
2. Use that department's **Reverse-Prompting Hooks** as the prompt seed.
3. Respect the boundary: edit only files the department owns; never change a `core/ports/`
   signature without lead review.
4. For 🧑‍⚖️ tasks, the result is **proposed**, not done, until a human reviews accuracy /
   legal mapping / live behaviour and signs off in the reviewer UI.
