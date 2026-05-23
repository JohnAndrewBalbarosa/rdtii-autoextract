# Architecture — Ports & Adapters (Hexagonal)

The **idea is framework-agnostic; the frameworks are swappable.** The core domain knows
nothing about FastAPI, Next.js, Claude, Tesseract, or Postgres. It depends only on the
**ports** below. Concrete tools are **adapters** wired at the edge.

This directly serves R12 (swappability, 40 pts across stages) and R16 (modular, self-hostable).

```
                ┌─────────────────────────────────────────────┐
   Frontend     │                  apps/web                    │   Next.js (reference)
 (reviewer UI)  │   search box · results · AUDIT/REVIEW view   │   ← swappable
                └───────────────────────┬─────────────────────┘
                                        │ HTTP / OpenAPI
                ┌───────────────────────┴─────────────────────┐
   Backend      │                  apps/api                    │   FastAPI (reference)
  (thin layer)  │   maps HTTP ⇄ core use-cases. No domain logic │   ← swappable
                └───────────────────────┬─────────────────────┘
                                        │ calls
   ┌────────────────────────────────────┴────────────────────────────────────┐
   │                              core/ (AGNOSTIC)                             │
   │                                                                           │
   │   pipeline:  discover → retrieve → ocr → chunk → extract → map → review   │
   │                                                                           │
   │   ports (interfaces only):                                                │
   │     DocumentSource · OCREngine · VectorStore · LLMProvider                │
   │     IndicatorClassifier · FindingRepository                               │
   └────────────────────────────────────┬────────────────────────────────────┘
                                        │ implemented by
   ┌────────────────────────────────────┴────────────────────────────────────┐
   │                               adapters/                                   │
   │  crawler/browser  ·  tesseract/paddle/doctr  ·  pgvector/qdrant/chroma    │
   │  claude/gpt/llama3  ·  encoder-classifier  ·  postgres-repo               │
   └───────────────────────────────────────────────────────────────────────────┘
```

## Ports (the stable contracts)

```text
DocumentSource.discover(jurisdiction, pillars) -> [DocRef]      # R8, R19, R20
DocumentSource.fetch(DocRef)                    -> RawDocument   # handles anti-bot/PDF
OCREngine.extract(RawDocument)                  -> Text(cer<0.05)# R17
Chunker.byArticle(Text)                         -> [ArticleChunk]# R4
VectorStore.upsert/search(...)                  -> [ArticleChunk]# R14 (RAG)
LLMProvider.complete(prompt, schema)            -> StructuredOut # R12 swappable
IndicatorClassifier.classify(ArticleChunk)      -> [Indicator]   # R14 classifier+verify
FindingRepository.save/list(Finding)            -> ...           # audit trail
```

A **swap = changing one factory/config entry.** Nothing in `core/` imports a concrete adapter.

## Domain entities

- **Article** — the atomic unit (R4): document ref, article number, text, language.
- **Finding** — an Article mapped to RDTII indicator(s) with the **6 mandatory fields** (R5)
  plus `confidence`, `pillar (6|7|…)`, and `review_status (pending|verified|rejected)` (R3, R18).
- **Pillar / Indicator** — RDTII taxonomy; Pillars 6 & 7 mandatory (R7).

## The pipeline (the 80%)

`discover → retrieve → ocr → chunk → extract → map → review`

Each stage is a pure use-case taking ports as dependencies — testable in isolation, no
framework needed. The final **review** stage produces the human-facing queue (the 20%, R1/R3).

## Swappability matrix (R12, R13)

| Concern | Dev default | Production / open-weight target |
| ------- | ----------- | ------------------------------- |
| LLM | Claude / GPT API | **Llama 3** (Apache-compatible), optionally fine-tuned (weights in repo) |
| OCR | pluggable | Tesseract / PaddleOCR / docTR — measured against <5% CER |
| Vectors | pgvector | Qdrant / Chroma / FAISS |
| Crawl | HTTP client | headless browser for anti-bot / JS portals |

## Deployment (R15, R16)

- `docker-compose up` → api + web + postgres(pgvector). Self-hostable, no managed cloud lock-in.
- All LLM calls metered → **cost-per-50-page-doc** logged (R21).
- Env-driven adapter selection (`LLM_PROVIDER=llama3`, `OCR_ENGINE=paddle`, …).

## Why these reference frameworks

- **FastAPI** — async I/O for crawl/OCR fan-out, native OpenAPI for the frontend contract,
  trivial to self-host. Pure-Python core stays import-clean.
- **Next.js** — server components for fast first paint of the audit view; one obvious place
  for the non-technical reviewer workflow (R2, R3).
- **Postgres + pgvector** — one engine for both document store and RAG vectors → fewer moving
  parts to self-host. Swap to Qdrant/Chroma via the `VectorStore` port if needed.

> None of these choices leak into `core/`. Replacing FastAPI with Litestar, or Next.js with
> SvelteKit, touches only `apps/` — the contract and domain are untouched.
